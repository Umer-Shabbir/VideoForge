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
from app.render.effects import (
    build_xfade_chain,
    build_fit_filter,
    build_motion_filter,
    clamp_transition_duration,
    sanitize_transition_name
)
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
        try:
            from app.services.project_scanner import sync_project_preset_styling
            settings_mgr = None
            try:
                from app.core.app_state import AppState
                settings_mgr = AppState.instance().settings
            except Exception:
                pass
            if not settings_mgr:
                try:
                    from app.storage.settings_manager import SettingsManager, get_app_data_dir
                    repo_root = Path(__file__).resolve().parents[2]
                    candidates = [
                        Path(os.environ["VIDEOFORGE_SETTINGS_PATH"]) if os.environ.get("VIDEOFORGE_SETTINGS_PATH") else None,
                        get_app_data_dir() / "settings.json",
                        repo_root / "settings.json",
                        Path.cwd() / "settings.json",
                    ]
                    for cand_p in candidates:
                        if cand_p and cand_p.is_file():
                            settings_mgr = SettingsManager(cand_p)
                            break
                except Exception:
                    pass
            sync_project_preset_styling(project, settings_mgr)
        except Exception as e:
            log.debug(f"[{project.name}] Could not sync preset styling in renderer: {e}")

        _prog(2.0, "Aligning subtitles…")
        subtitle_path = None
        sub_chunks = None
        from app.core.project import SubtitleMode
        is_sub_enabled = bool(project.profile.subtitle_enabled or project.profile.subtitle_mode)
        if is_sub_enabled and not project.transcript_text and project.transcript_path and project.transcript_path.exists():
            try:
                from app.utils.file_utils import read_transcript_segments
                text, segs = read_transcript_segments(project.transcript_path)
                project.transcript_text = text
                if segs and not project.transcript_segments:
                    project.transcript_segments = segs
            except Exception as e:
                log.warning(f"[{project.name}] Could not reload transcript: {e}")

        if is_sub_enabled and project.transcript_text:
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
        slots = generate_timeline(project, sub_chunks=sub_chunks)
        if not slots:
            raise RenderError("No timeline slots generated")
        log.info(f"[{project.name}] {len(slots)} image slots, "
                 f"audio={project.audio_duration:.1f}s")

        # ── Build & Execute ───────────────────────────────────────────────────
        MAX_CHUNK_SLOTS = 20

        if len(slots) <= MAX_CHUNK_SLOTS:
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

            _prog(38.0, "Rendering…")

            def _fp(pct):
                _prog(38.0 + pct * 0.58, f"Encoding {pct:.0f}%")

            rc, _, stderr = run_ffmpeg(
                cmd,
                progress_callback=_fp,
                log_callback=log_callback,
                expected_duration=project.audio_duration,
            )

            if _cancelled():
                _cleanup(temp_out, subtitle_path, temp_dir)
                return RenderResult(False, error="Cancelled", metrics=metrics)

            if rc != 0:
                err = _best_error(stderr)
                _cleanup(temp_out, subtitle_path, temp_dir)
                raise RenderError(f"FFmpeg failed: {err}")

        else:
            # ── Chunked execution for large project (>20 images) ──────────────
            pr = project.profile
            fps = pr.fps
            w, h = pr.width, pr.height
            fit = pr.fit_mode.value if hasattr(pr.fit_mode, "value") else str(pr.fit_mode)
            trans_str = pr.transition_type.value if hasattr(pr.transition_type, "value") else str(pr.transition_type)
            trans_dur = float(getattr(pr, "transition_duration", 0.0) or 0.0)
            if trans_dur <= 0 and trans_str.lower() != "none":
                trans_dur = 0.6
            has_transitions = (trans_str.lower() != "none" and trans_dur > 0)
            trans = trans_str if trans_str.lower() != "none" else "fade"
            disp_dur = slots[0].display_duration
            seg_dur = slots[0].segment_duration
            audio_dur = project.audio_duration or 0.0

            chunks = _get_non_overlapping_chunks(len(slots), chunk_size=MAX_CHUNK_SLOTS)
            num_chunks = len(chunks)
            chunk_files = []

            import os as _os
            auto_threads = _os.cpu_count() or 4
            effective_threads = ffmpeg_threads if (ffmpeg_threads and ffmpeg_threads > 0) else auto_threads

            has_subtitles = bool(subtitle_path and subtitle_path.exists())
            chunk_preset = pr.get_x264_preset(default="fast")
            chunk_crf = min(pr.crf, 17) if has_subtitles else pr.crf

            log.info(
                f"[{project.name}] {len(slots)} images exceeds command length limit — "
                f"rendering in {num_chunks} chunks ({w}×{h}@{fps}fps, transitions={'yes (' + str(trans_dur) + 's)' if has_transitions else 'none'})"
            )

            for c_idx, (start_idx, end_idx) in enumerate(chunks):
                if _cancelled():
                    _cleanup(temp_out, subtitle_path, temp_dir)
                    return RenderResult(False, error="Cancelled", metrics=metrics)

                chunk_slots = slots[start_idx : end_idx + 1]
                n_c = len(chunk_slots)

                chunk_out = temp_dir / f"_chunk_{c_idx:03d}.mp4"
                chunk_files.append(chunk_out)

                cmd_chunk = [
                    ffmpeg, "-y",
                    "-threads", str(effective_threads),
                    "-probesize", "32M", "-analyzeduration", "0",
                ]

                if has_transitions and n_c > 1:
                    chunk_durs = []
                    for i, slot in enumerate(chunk_slots):
                        if i < n_c - 1:
                            t_dur = clamp_transition_duration(
                                slot.display_duration,
                                chunk_slots[i + 1].display_duration,
                                base_duration=trans_dur
                            )
                            dur = slot.display_duration + t_dur
                        else:
                            dur = slot.display_duration
                        chunk_durs.append(dur)

                        cmd_chunk += [
                            "-loop", "1",
                            "-framerate", str(fps),
                            "-t", f"{max(0.05, dur):.6f}",
                            "-i", str(slot.image_path),
                        ]

                    fc_chunk = []
                    for i in range(n_c):
                        slot = chunk_slots[i]
                        filt = build_motion_filter(slot.motion, fit, w, h, chunk_durs[i], fps=fps, hold_duration=trans_dur)
                        fc_chunk.append(f"[{i}:v]{filt},fps={fps}[v{i}]")

                    final_chunk_stream, chunk_expected_dur = build_xfade_chain(
                        fc_chunk, n_c, chunk_slots, default_trans=trans, base_trans_dur=trans_dur
                    )
                else:
                    # No transitions or single-slot chunk: exact duration per slot
                    for slot in chunk_slots:
                        cmd_chunk += [
                            "-loop", "1",
                            "-framerate", str(fps),
                            "-t", f"{slot.display_duration:.6f}",
                            "-i", str(slot.image_path),
                        ]

                    fc_chunk = []
                    for i in range(n_c):
                        slot = chunk_slots[i]
                        filt = build_motion_filter(slot.motion, fit, w, h, slot.display_duration, fps=fps)
                        fc_chunk.append(f"[{i}:v]{filt},fps={fps}[v{i}]")

                    if n_c > 1:
                        inputs = "".join(f"[v{i}]" for i in range(n_c))
                        fc_chunk.append(f"{inputs}concat=n={n_c}:v=1:a=0[vout]")
                        final_chunk_stream = "vout"
                    else:
                        final_chunk_stream = "v0"
                    chunk_expected_dur = sum(s.display_duration for s in chunk_slots)

                cmd_chunk += [
                    "-filter_complex", ";\n".join(fc_chunk),
                    "-map", f"[{final_chunk_stream}]",
                    "-c:v", "libx264",
                    "-preset", chunk_preset,
                    "-crf", str(chunk_crf),
                    "-pix_fmt", "yuv420p",
                    "-color_range", "tv",
                    "-colorspace", "bt709",
                    "-color_primaries", "bt709",
                    "-color_trc", "bt709",
                    str(chunk_out),
                ]

                chunk_pct_base = 38.0 + (c_idx / num_chunks) * 48.0
                chunk_pct_span = (1.0 / num_chunks) * 48.0

                def _chunk_fp(pct, c_base=chunk_pct_base, c_span=chunk_pct_span, c_num=c_idx + 1):
                    _prog(c_base + pct * 0.01 * c_span, f"Rendering chunk {c_num}/{num_chunks} ({pct:.0f}%)")

                _prog(chunk_pct_base, f"Rendering chunk {c_idx + 1}/{num_chunks}…")
                rc, _, stderr = run_ffmpeg(
                    cmd_chunk,
                    progress_callback=_chunk_fp,
                    log_callback=log_callback,
                    expected_duration=chunk_expected_dur,
                )
                if rc != 0:
                    err = _best_error(stderr)
                    _cleanup(temp_out, subtitle_path, temp_dir)
                    raise RenderError(f"FFmpeg chunk {c_idx + 1}/{num_chunks} failed: {err}")

            if _cancelled():
                _cleanup(temp_out, subtitle_path, temp_dir)
                return RenderResult(False, error="Cancelled", metrics=metrics)

            # ── Concat chunks ─────────────────────────────────────────────────
            _prog(87.0, "Concatenating chunks…")
            concat_list_file = temp_dir / "_concat_list.txt"
            with open(concat_list_file, "w", encoding="utf-8") as f:
                for cf in chunk_files:
                    f.write(f"file '{cf.resolve().as_posix()}'\n")

            temp_video_combined = temp_dir / "_video_combined.mp4"
            cmd_concat = [
                ffmpeg, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_file),
                "-c", "copy",
                str(temp_video_combined),
            ]
            rc, _, stderr = run_ffmpeg(cmd_concat, log_callback=log_callback)
            if rc != 0:
                err = _best_error(stderr)
                _cleanup(temp_out, subtitle_path, temp_dir)
                raise RenderError(f"FFmpeg concat failed: {err}")

            if _cancelled():
                _cleanup(temp_out, subtitle_path, temp_dir)
                return RenderResult(False, error="Cancelled", metrics=metrics)

            # ── Final Mux Pass (Audio & Subtitles) ─────────────────────────────
            _prog(89.0, "Finalizing audio & subtitles…")
            bgm_path = getattr(project, "bgm_path", None)
            has_bgm = bool(bgm_path and Path(bgm_path).exists())

            cmd_mux = [
                ffmpeg, "-y",
                "-threads", str(effective_threads),
                "-i", str(temp_video_combined),
                "-i", str(project.audio_path),
            ]
            if has_bgm:
                cmd_mux += ["-stream_loop", "-1", "-i", str(bgm_path)]

            fc_mux = []
            if has_subtitles:
                ass = _esc_ass_path(subtitle_path)
                fc_mux.append(f"[0:v]ass={ass},format=yuv420p[vout]")
                v_map = "[vout]"
            else:
                v_map = "0:v"

            af = _audio_filter(1, audio_dur, pr, bgm_idx=2 if has_bgm else None)
            fc_mux.append(af)

            cmd_mux += [
                "-filter_complex", ";\n".join(fc_mux),
                "-map", v_map,
                "-map", "[aout]",
            ]
            if has_subtitles:
                cmd_mux += [
                    "-c:v", "libx264",
                    "-preset", pr.get_x264_preset(default="fast"),
                    "-crf", str(pr.crf),
                    "-pix_fmt", "yuv420p",
                    "-color_range", "tv",
                    "-colorspace", "bt709",
                    "-color_primaries", "bt709",
                    "-color_trc", "bt709",
                ]
            else:
                cmd_mux += ["-c:v", "copy"]

            cmd_mux += [
                "-c:a", "aac",
                "-b:a", pr.audio_bitrate,
                "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart",
                "-t", f"{audio_dur:.3f}",
                str(temp_out),
            ]

            metrics.ffmpeg_command = f"Chunked ({num_chunks} chunks): " + " ".join(str(a) for a in cmd_mux)

            def _mux_fp(pct):
                _prog(89.0 + pct * 0.07, f"Finalizing {pct:.0f}%")

            rc, _, stderr = run_ffmpeg(
                cmd_mux,
                progress_callback=_mux_fp,
                log_callback=log_callback,
                expected_duration=audio_dur,
            )
            if rc != 0:
                err = _best_error(stderr)
                _cleanup(temp_out, subtitle_path, temp_dir)
                raise RenderError(f"FFmpeg mux failed: {err}")

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

        # ── Generate YouTube Chapters ──────────────────────────────────────────
        try:
            from app.services.chapter_generator import generate_chapters_for_project
            chapters = generate_chapters_for_project(
                project_folder=final_out.parent,
                sub_chunks=sub_chunks,
                final_duration=project.audio_duration or 0.0
            )
            if chapters:
                log.info(f"[{project.name}] YouTube chapters saved to {final_out.parent / 'chapters.txt'} ({len(chapters)} chapters)")
        except Exception as chap_err:
            log.warning(f"[{project.name}] Could not generate chapters.txt: {chap_err}")

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
# Command builder & Chunk helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_slot_chunks(n: int, chunk_size: int = 20) -> list[tuple[int, int]]:
    """
    Divide n slots into overlapping chunk index ranges: [(start_0, end_0), (start_1, end_1), ...].
    Each pair of adjacent chunks shares one boundary image for seamless xfade transitions.
    """
    if n <= chunk_size:
        return [(0, n - 1)]
    chunks = []
    start = 0
    while start < n - 1:
        end = min(start + chunk_size, n - 1)
        if n - 1 - end == 1:
            end = n - 1
        chunks.append((start, end))
        start = end
    return chunks


def _get_non_overlapping_chunks(n: int, chunk_size: int = 20) -> list[tuple[int, int]]:
    """
    Divide n slots into non-overlapping chunk index ranges: [(0, 19), (20, 39), ...].
    Used when there are no transitions between images.
    """
    if n <= chunk_size:
        return [(0, n - 1)]
    chunks = []
    start = 0
    while start < n:
        end = min(start + chunk_size - 1, n - 1)
        if n - 1 - end == 1:
            end = n - 1
        chunks.append((start, end))
        start = end + 1
    return chunks


def _build_command(project, slots, subtitle_path, output_path, ffmpeg_bin, ffmpeg_threads=0):
    """
    Build the complete single-pass FFmpeg command.
    Static images + xfade transitions + audio + subtitle burn-in.
    No zoompan / motion — each image is a static frame for its exact duration.
    """
    pr  = project.profile
    n   = len(slots)
    w, h, fps = pr.width, pr.height, pr.fps
    trans_str  = pr.transition_type.value if hasattr(pr.transition_type, "value") else str(pr.transition_type)
    trans_dur  = float(getattr(pr, "transition_duration", 0.0) or 0.0)
    if trans_dur <= 0 and trans_str.lower() != "none":
        trans_dur = 0.6
    has_transitions = (trans_str.lower() != "none" and trans_dur > 0)
    trans      = trans_str if trans_str.lower() != "none" else "fade"
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
        slot = slots[i]
        filt = build_motion_filter(
            slot.motion, fit, w, h, slot.segment_duration, fps=fps,
            hold_duration=trans_dur if has_transitions else 0.5
        )
        fc_parts.append(f"[{i}:v]{filt},fps={fps}[v{i}]")

    # Video composition: single image, concat (no transitions), or xfade
    if n == 1:
        final_video = "v0"
    elif not has_transitions:
        inputs = "".join(f"[v{i}]" for i in range(n))
        fc_parts.append(f"{inputs}concat=n={n}:v=1:a=0[vout]")
        final_video = "vout"
    else:
        final_video, _ = build_xfade_chain(fc_parts, n, slots, default_trans=trans, base_trans_dur=trans_dur)

    # Audio filter
    af = _audio_filter(audio_idx, audio_dur, pr, bgm_idx=bgm_idx)
    fc_parts.append(af)

    # ── Subtitle burn-in: MUST be inside filter_complex, not -vf ─────────────
    # Using -vf together with -filter_complex + -map causes EINVAL (FFmpeg exits
    # immediately with no error output). The ass filter must be the final step
    # in the filter_complex graph.
    if subtitle_path and subtitle_path.exists():
        ass = _esc_ass_path(subtitle_path)
        # Apply ass as the last filter in the graph
        fc_parts.append(f"[{final_video}]ass={ass},format=yuv420p[vfinal]")
        final_video = "vfinal"

    fc = ";\n".join(fc_parts)
    cmd += ["-filter_complex", fc]
    cmd += ["-map", f"[{final_video}]", "-map", "[aout]"]

    # ── Codec + quality ───────────────────────────────────────────────────────
    cmd += [
        "-c:v", "libx264",
        "-preset", pr.get_x264_preset(default="fast"),
        "-crf", str(pr.crf),
        "-pix_fmt", "yuv420p",
        "-color_range", "tv",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "aac",
        "-b:a", pr.audio_bitrate,
        "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        "-t", f"{audio_dur:.3f}",   # hard trim to audio length
    ]
    cmd.append(str(output_path))
    return cmd


def _fit_filter(fit: str, w: int, h: int) -> str:
    """Scale + crop/pad to exact output dimensions using unified effects engine."""
    return build_fit_filter(fit, w, h)


def _xfade_chain(fc_parts: list, n: int, slots, trans: str, trans_dur: float) -> str:
    """Build xfade chain connecting v0…v(n-1) using unified effects engine."""
    final_video, _ = build_xfade_chain(fc_parts, n, slots, default_trans=trans, base_trans_dur=trans_dur)
    return final_video


def _audio_filter(audio_idx: int, audio_dur: float, pr, bgm_idx: int = None) -> str:
    parts = []
    if pr.normalize_audio:
        parts.append("loudnorm=I=-14.0:TP=-1.0:LRA=9.0")
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
