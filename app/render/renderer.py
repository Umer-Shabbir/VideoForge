"""
VideoForge Render Pipeline
==========================
Approach: single-pass FFmpeg with filter_complex.
- No zoompan / motion animation (removed — caused wrong clip durations)
- Each image is displayed as a static frame for its exact duration
- xfade transitions between images (fade, dissolve, wipe, etc.)
- Subtitles burned in via ASS filter
- Audio muxed + normalized

This is reliable, fast, and produces correct output lengths.
"""

import time
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable

from app.core.project import Project, RenderMetrics
from app.render.timeline import generate_timeline
from app.subtitles.aligner import align_subtitles
from app.subtitles.styler import write_ass_file, write_srt_file
from app.utils.ffmpeg_utils import run_ffmpeg, find_ffmpeg
from app.utils.file_utils import ensure_dir, unique_output_path

log = logging.getLogger("videoforge.renderer")


class RenderError(Exception):
    pass


class RenderResult:
    def __init__(self, success: bool, output_path: Optional[Path] = None,
                 error: str = "", metrics: Optional[RenderMetrics] = None):
        self.success     = success
        self.output_path = output_path
        self.error       = error
        self.metrics     = metrics or RenderMetrics()


def render_project(
    project: Project,
    output_path: Optional[Path] = None,
    progress_callback: Optional[Callable] = None,
    log_callback: Optional[Callable] = None,
    cancel_flag=None,
    ffmpeg_bin: Optional[str] = None,
    ffmpeg_threads: int = 0,
    overwrite: bool = False,
    save_srt: bool = True,
) -> RenderResult:
    metrics = RenderMetrics()
    metrics.started_at = time.time()

    def _prog(pct: float, msg: str = ""):
        if progress_callback:
            progress_callback(pct, msg)
        metrics.progress_pct = pct

    def _cancelled():
        return cancel_flag is not None and cancel_flag.is_set()

    try:
        _prog(0.0, "Starting…")

        # ── Validate ─────────────────────────────────────────────────────────
        ffmpeg = ffmpeg_bin or find_ffmpeg()
        if not ffmpeg:
            raise RenderError("FFmpeg not found. Set the path in Settings → FFmpeg & Tools.")

        if not project.audio_path or not project.audio_path.exists():
            raise RenderError(f"Audio file not found: {project.audio_path}")
        if not project.image_paths:
            raise RenderError("No images in project")

        final_out = Path(output_path or project.output_path)
        if final_out.exists() and not overwrite:
            final_out = unique_output_path(final_out)
        ensure_dir(final_out.parent)

        temp_dir = final_out.parent / "_vf_temp"
        ensure_dir(temp_dir)
        temp_out = temp_dir / f"_tmp_{final_out.stem}.mp4"

        # ── Subtitles ─────────────────────────────────────────────────────────
        _prog(2.0, "Aligning subtitles…")
        subtitle_path = None
        sub_chunks = []

        if project.profile.subtitle_enabled and project.transcript_text:
            try:
                def _sp(pct, msg=""):
                    _prog(2.0 + pct * 0.28, msg)

                sub_chunks = align_subtitles(
                    project, progress_callback=_sp, cancel_flag=cancel_flag
                )
                metrics.subtitle_count = len(sub_chunks)
                log.info(f"[{project.name}] {len(sub_chunks)} subtitle chunks")

                if sub_chunks:
                    subtitle_path = temp_dir / "_subs.ass"  # short safe name avoids apostrophe-in-path issues
                    write_ass_file(sub_chunks, subtitle_path, project.profile,
                                   project.audio_duration or 0.0)
                    if save_srt:
                        srt = final_out.with_name("audio.srt")
                        write_srt_file(sub_chunks, srt)
                        log.info(f"SRT saved: {srt}")
            except Exception as e:
                log.warning(f"[{project.name}] Subtitle error: {e} — continuing without")
                subtitle_path = None

        if _cancelled():
            return RenderResult(False, error="Cancelled", metrics=metrics)

        # ── Timeline ──────────────────────────────────────────────────────────
        _prog(32.0, "Building timeline…")
        slots = generate_timeline(project)
        if not slots:
            raise RenderError("No timeline slots generated")
        log.info(f"[{project.name}] {len(slots)} image slots, "
                 f"audio={project.audio_duration:.1f}s")

        # ── Build command ─────────────────────────────────────────────────────
        _prog(35.0, "Building FFmpeg command…")
        cmd = _build_command(
            project=project,
            slots=slots,
            subtitle_path=subtitle_path,
            output_path=temp_out,
            ffmpeg_bin=ffmpeg,
            ffmpeg_threads=ffmpeg_threads,
        )
        metrics.ffmpeg_command = " ".join(str(a) for a in cmd)
        log.info(f"[{project.name}] {len(slots)} images → {final_out.name} "
                 f"({project.profile.width}×{project.profile.height}@{project.profile.fps}fps)")

        if _cancelled():
            return RenderResult(False, error="Cancelled", metrics=metrics)

        # ── Execute ───────────────────────────────────────────────────────────
        _prog(38.0, "Rendering…")

        def _fp(pct):
            _prog(38.0 + pct * 0.58, f"Encoding {pct:.0f}%")

        rc, _, stderr = run_ffmpeg(cmd, progress_callback=_fp, log_callback=log_callback)

        if _cancelled():
            _cleanup(temp_out, subtitle_path, temp_dir)
            return RenderResult(False, error="Cancelled", metrics=metrics)

        if rc != 0:
            err = _best_error(stderr)
            _cleanup(temp_out, subtitle_path, temp_dir)
            raise RenderError(f"FFmpeg failed: {err}")

        # ── Verify ────────────────────────────────────────────────────────────
        _prog(97.0, "Verifying…")
        if not temp_out.exists() or temp_out.stat().st_size < 1024:
            _cleanup(temp_out, subtitle_path, temp_dir)
            raise RenderError("Output file missing or empty")

        move_success = False
        last_move_err = None
        for attempt in range(5):
            try:
                if final_out.exists():
                    final_out.unlink()
                shutil.move(str(temp_out), str(final_out))
                move_success = True
                break
            except (PermissionError, OSError) as e:
                last_move_err = e
                time.sleep(0.1)

        if not move_success:
            _cleanup(temp_out, subtitle_path, temp_dir)
            raise RenderError(f"Failed to finalize output file: {last_move_err}")

        _cleanup(None, subtitle_path, temp_dir)

        metrics.finished_at      = time.time()
        metrics.render_time_seconds = metrics.finished_at - metrics.started_at
        metrics.output_size_bytes   = final_out.stat().st_size
        metrics.progress_pct        = 100.0

        _prog(100.0, f"Done — {_sz(metrics.output_size_bytes)} in {metrics.render_time_seconds:.0f}s")
        log.info(f"[{project.name}] Complete: {final_out.name} "
                 f"({_sz(metrics.output_size_bytes)}, {metrics.render_time_seconds:.0f}s)")
        return RenderResult(True, final_out, metrics=metrics)

    except RenderError as e:
        metrics.finished_at = time.time()
        log.error(f"[{project.name}] {e}")
        return RenderResult(False, error=str(e), metrics=metrics)
    except Exception as e:
        metrics.finished_at = time.time()
        import traceback
        log.error(f"[{project.name}] Unexpected error:\n{traceback.format_exc()}")
        return RenderResult(False, error=str(e), metrics=metrics)


# ─────────────────────────────────────────────────────────────────────────────
# Command builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_command(project, slots, subtitle_path, output_path, ffmpeg_bin, ffmpeg_threads=0):
    """
    Build the complete single-pass FFmpeg command.
    Static images + xfade transitions + audio + subtitle burn-in.
    No zoompan / motion — each image is a static frame for its exact duration.
    """
    pr  = project.profile
    n   = len(slots)
    w, h, fps = pr.width, pr.height, pr.fps
    trans      = pr.transition_type.value if pr.transition_type.value != "none" else "fade"
    trans_dur  = pr.transition_duration
    audio_dur  = project.audio_duration or 0.0

    # ── Performance: detect CPU count for FFmpeg threading ───────────────────
    import os as _os
    auto_threads = _os.cpu_count() or 4

    cmd = [ffmpeg_bin, "-y"]

    # Set thread count explicitly: FFmpeg defaults can be conservative
    # Using all threads for decoding/scaling gives a measurable speedup
    if ffmpeg_threads and ffmpeg_threads > 0:
        cmd += ["-threads", str(ffmpeg_threads)]
    else:
        cmd += ["-threads", str(auto_threads)]  # use all cores

    # Faster input probing (avoids 5-second analysis on large audio files)
    cmd += ["-probesize", "32M", "-analyzeduration", "0"]

    # ── Inputs: one per image ─────────────────────────────────────────────────
    for slot in slots:
        cmd += [
            "-loop", "1",
            "-framerate", str(fps),
            "-t", f"{slot.segment_duration:.6f}",   # exact duration
            "-i", str(slot.image_path),
        ]

    # ── Input: audio ─────────────────────────────────────────────────────────
    audio_idx = n
    cmd += ["-i", str(project.audio_path)]

    # ── Input: bgm (optional) ────────────────────────────────────────────────
    bgm_idx = None
    if getattr(project, "bgm_path", None) and project.bgm_path.exists():
        bgm_idx = audio_idx + 1
        cmd += ["-stream_loop", "-1", "-i", str(project.bgm_path)]

    # ── filter_complex ────────────────────────────────────────────────────────
    fc_parts = []

    # Scale every image to exact output size
    fit = pr.fit_mode.value if hasattr(pr.fit_mode, "value") else str(pr.fit_mode)
    for i in range(n):
        fc_parts.append(f"[{i}:v]{_fit_filter(fit, w, h)},fps={fps}[v{i}]")

    # xfade chain
    if n == 1:
        final_video = "v0"
    else:
        final_video = _xfade_chain(fc_parts, n, slots, trans, trans_dur)

    # Audio filter
    af = _audio_filter(audio_idx, audio_dur, pr, bgm_idx=bgm_idx)
    fc_parts.append(af)

    # ── Subtitle burn-in: MUST be inside filter_complex, not -vf ─────────────
    # Using -vf together with -filter_complex + -map causes EINVAL (FFmpeg exits
    # immediately with no error output). The ass filter must be the final step
    # in the filter_complex graph.
    if subtitle_path and subtitle_path.exists() and pr.subtitle_enabled:
        ass = _esc_ass_path(subtitle_path)
        # Apply ass as the last filter in the graph
        fc_parts.append(f"[{final_video}]ass={ass}[vfinal]")
        final_video = "vfinal"

    fc = ";\n".join(fc_parts)
    cmd += ["-filter_complex", fc]
    cmd += ["-map", f"[{final_video}]", "-map", "[aout]"]

    # ── Codec + quality ───────────────────────────────────────────────────────
    cmd += [
        "-c:v", "libx264",
        "-preset", pr.preset_name,
        "-crf", str(pr.crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", pr.audio_bitrate,
        "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        "-t", f"{audio_dur:.3f}",   # hard trim to audio length
    ]
    cmd.append(str(output_path))
    return cmd


def _fit_filter(fit: str, w: int, h: int) -> str:
    """Scale + crop/pad to exact output dimensions."""
    if fit in ("cover", ""):
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1")
    elif fit == "contain":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    elif fit == "blur_bg":
        # blurred background fill
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1")
    else:
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1")


def _xfade_chain(fc_parts: list, n: int, slots, trans: str, trans_dur: float) -> str:
    """
    Build xfade chain connecting v0…v(n-1).
    Returns the label of the final output stream.
    """
    prev_label = "v0"
    cumulative = 0.0

    for i in range(1, n):
        cumulative += slots[i - 1].display_duration
        offset     = max(0.01, cumulative - trans_dur)
        out_label  = f"xf{i}" if i < n - 1 else "vout"

        fc_parts.append(
            f"[{prev_label}][v{i}]"
            f"xfade=transition={trans}:duration={trans_dur:.3f}:offset={offset:.3f}"
            f"[{out_label}]"
        )
        prev_label = out_label

    return prev_label


def _audio_filter(audio_idx: int, audio_dur: float, pr, bgm_idx: int = None) -> str:
    parts = []
    if pr.normalize_audio:
        parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    if pr.audio_fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={pr.audio_fade_in:.2f}")
    if pr.audio_fade_out > 0 and audio_dur > pr.audio_fade_out:
        parts.append(f"afade=t=out:st={audio_dur - pr.audio_fade_out:.3f}:d={pr.audio_fade_out:.2f}")
    inner = ",".join(parts) if parts else "anull"

    if bgm_idx is not None:
        bgm_vol = getattr(pr, "bgm_volume", 0.1)
        bgm_fi = getattr(pr, "bgm_fade_in", 2.0)
        bgm_fo = getattr(pr, "bgm_fade_out", 3.0)

        bgm_parts = [f"volume={bgm_vol}"]
        if bgm_fi > 0:
            bgm_parts.append(f"afade=t=in:st=0:d={bgm_fi:.2f}")
        if bgm_fo > 0 and audio_dur > bgm_fo:
            bgm_parts.append(f"afade=t=out:st={audio_dur - bgm_fo:.3f}:d={bgm_fo:.2f}")
        bgm_inner = ",".join(bgm_parts)

        return (
            f"[{audio_idx}:a]{inner},asplit=2[main_a][main_side]; "
            f"[{bgm_idx}:a]{bgm_inner}[bgm_a]; "
            f"[bgm_a][main_side]sidechaincompress=threshold=0.08:ratio=4:attack=5:release=50[bgm_ducked]; "
            f"[main_a][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

    return f"[{audio_idx}:a]{inner}[aout]"


def _esc_ass_path(path: Path) -> str:
    """
    Escape a subtitle path for the ass= filter inside filter_complex.
    Strategy: write the ASS file to a path with NO special characters
    (we already use '_subs.ass'), then just do the drive-letter colon escape.
    
    In FFmpeg filter syntax, colons in paths must be escaped as BACKSLASH-COLON because
    colon is the option-separator inside filter arguments.
    Single quotes around the path delimit the value to FFmpeg's filter parser.
    Apostrophes in the path itself will break this — so the file must be named
    without apostrophes (the caller ensures this by using '_subs.ass').
    """
    p = str(path).replace("\\", "/")
    # Escape drive-letter colon: C:/... → C\:/...
    if len(p) >= 2 and p[1] == ":":
        p = p[0] + r"\:" + p[2:]
    # Escape any remaining apostrophes in the path (safety net)
    p = p.replace("'", "")
    return f"'{p}'"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cleanup(out, sub, tmpdir):
    """Remove temp files. Logs warnings on failure (e.g. file still locked on Windows)."""
    for p in [out, sub]:
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception as e:
                log.warning(f"Could not remove temp file {p}: {e}")
    if tmpdir:
        try:
            td = Path(tmpdir)
            if td.exists():
                import shutil as _shutil
                _shutil.rmtree(td, ignore_errors=True)
        except Exception as e:
            log.warning(f"Could not remove temp dir {tmpdir}: {e}")


def _best_error(stderr: str) -> str:
    if not stderr or not stderr.strip():
        return "No error output from FFmpeg. Check the Logs tab for the full command."
    lines = [l for l in stderr.splitlines() if l.strip()]
    errors = [l for l in lines if any(
        w in l.lower() for w in ("error", "invalid", "failed", "no such", "unable")
    )]
    tail = " | ".join(lines[-4:])
    return f"{errors[-1]} [{tail}]"[:500] if errors else tail[:500]


def _sz(b: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024: return f"{b:.1f} {u}"
        b //= 1024
    return f"{b:.1f} GB"
