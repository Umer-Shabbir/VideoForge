"""
FFmpeg command builder: constructs the complete FFmpeg command for video generation.
Handles image fitting, Ken Burns motion, transitions, audio, and subtitle burn-in.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from app.core.project import Project, RenderProfile, FitMode, TransitionType, MotionType
from app.render.timeline import ImageSlot, build_zoompan_filter

log = logging.getLogger("videoforge.ffmpeg_builder")


def build_render_command(
    project: Project,
    slots: list[ImageSlot],
    subtitle_path: Optional[Path],
    output_path: Path,
    temp_dir: Path,
    ffmpeg_bin: str = "ffmpeg",
    threads: int = 0,
) -> tuple[list[str], str]:
    """
    Build the complete FFmpeg command list.
    Returns (cmd_list, description_string).
    """
    profile = project.profile
    n = len(slots)
    fps = profile.fps
    w = profile.width
    h = profile.height
    trans_dur = profile.transition_duration
    trans_type = profile.transition_type.value

    cmd = [ffmpeg_bin, "-y"]  # -y = overwrite output

    # ── Input: Images ─────────────────────────────────────────────────────────
    for slot in slots:
        # -loop 1: loop static image
        # -t: duration of this input clip
        cmd.extend([
            "-loop", "1",
            "-framerate", str(fps),
            "-t", f"{slot.segment_duration:.6f}",
            "-i", _fp(slot.image_path),
        ])

    # ── Input: Intro/Outro images (optional) ──────────────────────────────────
    intro_idx = None
    outro_idx = None
    extra_inputs = []

    if profile.intro_enabled and profile.intro_image and Path(profile.intro_image).exists():
        intro_idx = n
        cmd.extend(["-loop", "1", "-framerate", str(fps),
                    "-t", f"{profile.intro_duration:.2f}",
                    "-i", _fp(Path(profile.intro_image))])
        extra_inputs.append("intro")

    if profile.outro_enabled and profile.outro_image and Path(profile.outro_image).exists():
        outro_idx = n + (1 if intro_idx is not None else 0)
        cmd.extend(["-loop", "1", "-framerate", str(fps),
                    "-t", f"{profile.outro_duration:.2f}",
                    "-i", _fp(Path(profile.outro_image))])
        extra_inputs.append("outro")

    # ── Input: Audio ──────────────────────────────────────────────────────────
    audio_idx = n + len(extra_inputs)
    cmd.extend(["-i", _fp(project.audio_path)])

    # ── Input: BGM (optional) ─────────────────────────────────────────────────
    bgm_idx = None
    if getattr(project, "bgm_path", None) and project.bgm_path.exists():
        bgm_idx = audio_idx + 1
        cmd.extend(["-stream_loop", "-1", "-i", _fp(project.bgm_path)])

    # ── Input: Watermark (optional) ───────────────────────────────────────────
    watermark_idx = None
    if profile.watermark_enabled and profile.watermark_path and Path(profile.watermark_path).exists():
        watermark_idx = audio_idx + 1 if bgm_idx is None else bgm_idx + 1
        cmd.extend(["-i", _fp(Path(profile.watermark_path))])

    # ── Filter Complex ────────────────────────────────────────────────────────
    filter_parts = []
    video_labels = []

    # Process each image slot
    for i, slot in enumerate(slots):
        seg_frames = max(1, int(slot.segment_duration * fps))
        motion_filter = build_zoompan_filter(slot.motion, seg_frames, w, h, fps)

        if profile.fit_mode == FitMode.BLUR_BG:
            # Blur-bg needs a multi-stage filter with unique label suffixes per slot
            # Here we first blur the background, then overlay the sharp foreground,
            # and finally apply the motion (zoompan) on the combined padded result.
            uid = f"s{i}"
            full_filter = (
                f"[{i}:v]split=2[bg{uid}][fg{uid}];"
                f"[bg{uid}]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},gblur=sigma=25[blurred{uid}];"
                f"[fg{uid}]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0[sharp{uid}];"
                f"[blurred{uid}][sharp{uid}]overlay=(W-w)/2:(H-h)/2[combined{uid}];"
            )
            if slot.motion.motion_type == MotionType.NONE or slot.motion.intensity <= 0:
                full_filter += f"[combined{uid}]setsar=1,fps={fps}[v{i}]"
            else:
                # To apply motion without destroying the blur composition, we apply zoompan
                # Rebuild zoompan filter exactly for this stream
                zm_filter = build_zoompan_filter(slot.motion, seg_frames, w, h, fps)
                full_filter += f"[combined{uid}]{zm_filter},fps={fps}[v{i}]"
        elif slot.motion.motion_type == MotionType.NONE:
            # Static: just fit + setsar
            fit_filter = _build_fit_filter(profile.fit_mode, w, h)
            full_filter = f"[{i}:v]{fit_filter},fps={fps}[v{i}]"
        else:
            # Motion: zoompan already starts with scale×2 + crop, then zoom
            # No pre-fit needed — zoompan handles source scaling internally
            # For Contain, we pad to maintain ratio before scaling up for zoompan
            fit_pad = ""
            if profile.fit_mode == FitMode.CONTAIN:
                fit_pad = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            full_filter = f"[{i}:v]{fit_pad}{motion_filter},fps={fps}[v{i}]"

        filter_parts.append(full_filter)
        video_labels.append(f"[v{i}]")

    # Process intro/outro
    if intro_idx is not None:
        fit_filter = _build_fit_filter(profile.fit_mode, w, h)
        filter_parts.append(f"[{intro_idx}:v]{fit_filter},fps={fps}[vintro]")

    if outro_idx is not None:
        fit_filter = _build_fit_filter(profile.fit_mode, w, h)
        filter_parts.append(f"[{outro_idx}:v]{fit_filter},fps={fps}[voutro]")

    # Chain transitions (xfade)
    if n == 1 and intro_idx is None and outro_idx is None:
        # Single image: just reference it directly
        final_video_label = "v0"
    else:
        # Build ordered list of all video streams
        all_labels = []
        if intro_idx is not None:
            all_labels.append("vintro")
        all_labels.extend(f"v{i}" for i in range(n))
        if outro_idx is not None:
            all_labels.append("voutro")

        final_video_label = _build_xfade_chain(
            filter_parts, all_labels, trans_type, trans_dur, fps, slots
        )

    # Audio processing
    audio_filter = _build_audio_filter(
        audio_idx, project.audio_duration or 0.0, profile, bgm_idx
    )
    filter_parts.append(audio_filter)
    audio_out_label = "aout"

    # Watermark overlay
    if watermark_idx is not None:
        wm_filter = _build_watermark_filter(
            final_video_label, watermark_idx, profile, w, h
        )
        filter_parts.append(wm_filter)
        final_video_label = "vwm"

    # Build complete filter_complex string
    filter_complex = ";\n".join(filter_parts)

    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", f"[{final_video_label}]"])
    cmd.extend(["-map", f"[{audio_out_label}]"])

    # ── Subtitle burn-in ──────────────────────────────────────────────────────
    if subtitle_path and subtitle_path.exists() and profile.subtitle_enabled:
        # ASS subtitles are burned in as a video filter
        # We need to add it AFTER the main filter_complex via -vf
        # FFmpeg requires ASS path with forward slashes and escaped colons on Windows
        ass_path = _escape_filter_path(subtitle_path)
        cmd.extend(["-vf", f"ass={ass_path}"])

    # ── Output codec & quality ─────────────────────────────────────────────────
    cmd.extend([
        "-c:v", profile.video_codec,
        "-crf", str(profile.crf),
        "-preset", profile.preset_name,
        "-b:v", profile.video_bitrate,
        "-maxrate", _scale_bitrate(profile.video_bitrate, 1.5),
        "-bufsize", _scale_bitrate(profile.video_bitrate, 2),
        "-c:a", profile.audio_codec,
        "-b:a", profile.audio_bitrate,
        "-ar", "44100",
        "-ac", "2",
    ])

    # Threads
    if threads > 0:
        cmd.extend(["-threads", str(threads)])

    # Pixel format (important for compatibility)
    cmd.extend(["-pix_fmt", "yuv420p"])

    # Move atom to beginning (for web streaming)
    cmd.extend(["-movflags", "+faststart"])

    # Duration safety: trim to audio duration
    if project.audio_duration:
        cmd.extend(["-t", f"{project.audio_duration:.3f}"])

    cmd.append(_fp(output_path))

    desc = (
        f"Render: {n} images, {project.audio_duration:.1f}s, "
        f"{w}x{h}@{fps}fps, {profile.video_codec}, "
        f"trans={trans_type}({trans_dur}s)"
    )
    log.debug(f"FFmpeg command: {' '.join(str(c) for c in cmd[:12])}...")
    return cmd, desc


def _build_fit_filter(fit_mode: FitMode, w: int, h: int) -> str:
    """
    Build the scale/pad/crop filter for image fitting.
    NOTE: BLUR_BG requires a per-input split approach handled at the slot level.
    For simplicity in the main pipeline it falls back to CONTAIN with black padding.
    A future enhancement could use lavfi overlay per-input.
    """
    if fit_mode == FitMode.COVER:
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1"
        )
    elif fit_mode == FitMode.CONTAIN:
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )
    elif fit_mode == FitMode.BLUR_BG:
        # Blur background fill using a two-pass approach that works in filter_complex
        # Scale up for background (blurred), scale down for foreground, overlay
        # We use a single-input approach: scale to fill, blur, then overlay sharp contained version
        return (
            f"split=2[bg{w}][fg{w}];"
            f"[bg{w}]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=25[blurred{w}];"
            f"[fg{w}]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0[sharp{w}];"
            f"[blurred{w}][sharp{w}]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    elif fit_mode == FitMode.STRETCH:
        return f"scale={w}:{h},setsar=1"
    else:
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1"
        )


def _build_xfade_chain(
    filter_parts: list[str],
    labels: list[str],
    trans_type: str,
    trans_dur: float,
    fps: int,
    slots: list[ImageSlot],
) -> str:
    """
    Build a chain of xfade filters connecting all video streams.
    Returns the label of the final output stream.
    """
    if len(labels) == 1:
        return labels[0]

    # Calculate xfade offsets
    # The offset is the time in the concatenated stream when the transition starts
    cumulative = 0.0
    prev_label = labels[0]

    for i in range(1, len(labels)):
        # Get the display duration of the previous slot
        if i - 1 < len(slots):
            prev_display = slots[i - 1].display_duration
        else:
            # Intro/outro: use profile transition duration
            prev_display = trans_dur * 2

        cumulative += prev_display
        offset = max(0.01, cumulative - trans_dur)

        out_label = f"xf{i}" if i < len(labels) - 1 else "vfinal"

        # Clamp transition type for safety
        safe_trans = trans_type if trans_type != "none" else "fade"

        xfade = (
            f"[{prev_label}][{labels[i]}]"
            f"xfade=transition={safe_trans}:"
            f"duration={trans_dur:.3f}:"
            f"offset={offset:.3f}"
            f"[{out_label}]"
        )
        filter_parts.append(xfade)
        prev_label = out_label

    return "vfinal"


def _build_audio_filter(
    audio_idx: int,
    audio_duration: float,
    profile: RenderProfile,
    bgm_idx: Optional[int] = None,
) -> str:
    """Build audio processing filter (normalize, fade in/out)."""
    parts = []
    if profile.normalize_audio:
        parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    fade_in = profile.audio_fade_in
    fade_out = profile.audio_fade_out
    if fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={fade_in:.2f}")
    if fade_out > 0 and audio_duration > fade_out:
        parts.append(f"afade=t=out:st={audio_duration - fade_out:.3f}:d={fade_out:.2f}")

    inner = ",".join(parts) if parts else "anull"

    if bgm_idx is not None:
        bgm_vol = getattr(profile, "bgm_volume", 0.1)
        bgm_fi = getattr(profile, "bgm_fade_in", 2.0)
        bgm_fo = getattr(profile, "bgm_fade_out", 3.0)

        bgm_parts = [f"volume={bgm_vol}"]
        if bgm_fi > 0:
            bgm_parts.append(f"afade=t=in:st=0:d={bgm_fi:.2f}")
        if bgm_fo > 0 and audio_duration > bgm_fo:
            bgm_parts.append(f"afade=t=out:st={audio_duration - bgm_fo:.3f}:d={bgm_fo:.2f}")
        bgm_inner = ",".join(bgm_parts)

        # Audio ducking using sidechaincompress mapping
        return (
            f"[{audio_idx}:a]{inner},asplit=2[main_a][main_side]; "
            f"[{bgm_idx}:a]{bgm_inner}[bgm_a]; "
            f"[bgm_a][main_side]sidechaincompress=threshold=0.08:ratio=4:attack=5:release=50[bgm_ducked]; "
            f"[main_a][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

    return f"[{audio_idx}:a]{inner}[aout]"


def _build_watermark_filter(
    video_label: str,
    wm_idx: int,
    profile: RenderProfile,
    w: int,
    h: int,
) -> str:
    """Build watermark overlay filter."""
    scale_w = int(w * profile.watermark_scale)
    alpha = profile.watermark_opacity
    pos = profile.watermark_position
    margin = 20

    positions = {
        "top_left": f"x={margin}:y={margin}",
        "top_right": f"x=W-w-{margin}:y={margin}",
        "bottom_left": f"x={margin}:y=H-h-{margin}",
        "bottom_right": f"x=W-w-{margin}:y=H-h-{margin}",
        "center": "x=(W-w)/2:y=(H-h)/2",
    }
    overlay_pos = positions.get(pos, positions["top_right"])

    return (
        f"[{wm_idx}:v]scale={scale_w}:-1,format=rgba,colorchannelmixer=aa={alpha:.2f}[wm];"
        f"[{video_label}][wm]overlay={overlay_pos}[vwm]"
    )


def _fp(path: Path) -> str:
    """Convert path to forward-slash string for FFmpeg."""
    return str(path).replace("\\", "/")


def _escape_filter_path(path: Path) -> str:
    """
    Escape a file path for use in FFmpeg -vf filter string.
    On Windows, colons in drive letters must be escaped.
    """
    p = str(path).replace("\\", "/")
    # Escape colons (except drive letter) and other special chars
    # Format: ass='C\:/path/to/file.ass'
    if len(p) >= 2 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    p = p.replace("'", "\\'")
    return f"'{p}'"


def _scale_bitrate(bitrate_str: str, factor: float) -> str:
    """Scale a bitrate string (e.g., '4M') by a factor."""
    try:
        if bitrate_str.upper().endswith("M"):
            val = float(bitrate_str[:-1]) * factor
            return f"{val:.1f}M"
        elif bitrate_str.upper().endswith("K"):
            val = float(bitrate_str[:-1]) * factor
            return f"{int(val)}k"
        return bitrate_str
    except Exception:
        return bitrate_str


def build_preview_frame_command(
    image_path: Path,
    output_path: Path,
    w: int = 640,
    h: int = 360,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    """Build FFmpeg command to extract a preview thumbnail from an image."""
    return [
        ffmpeg_bin, "-y",
        "-i", _fp(image_path),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
        "-frames:v", "1",
        _fp(output_path),
    ]


def build_sample_render_command(
    project: Project,
    slots: list[ImageSlot],
    output_path: Path,
    ffmpeg_bin: str,
    sample_duration: float = 10.0,
) -> list[str]:
    """Build a short sample render command (first N seconds only)."""
    # Take only first few slots that fit within sample_duration
    sample_slots = []
    total = 0.0
    for slot in slots:
        if total + slot.segment_duration > sample_duration + project.profile.transition_duration:
            break
        sample_slots.append(slot)
        total += slot.display_duration

    if not sample_slots:
        sample_slots = slots[:1]

    cmd, _ = build_render_command(
        project=project,
        slots=sample_slots,
        subtitle_path=None,
        output_path=output_path,
        temp_dir=output_path.parent,
        ffmpeg_bin=ffmpeg_bin,
    )
    # Override duration
    cmd.extend(["-t", str(sample_duration)])
    return cmd
