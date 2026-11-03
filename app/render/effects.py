"""
VideoForge Visual Effects & Transitions Engine.
Provides clean, smooth, and reliable implementations for:
- FFmpeg xfade transition chains with dynamic variation and duration smoothing
- Ken Burns motion effects (pan, zoom, tilt)
- High-fidelity image scaling and aspect-ratio fit modes (cover, contain, blur_bg)
"""

from typing import List, Tuple, Any, Optional
from app.core.project import TransitionType, MotionType
from app.render.timeline import MotionParams


VALID_XFADE_TRANSITIONS = {
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite",
    "radial", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "vertopen", "vertclose", "horzopen", "horzclose",
    "dissolve", "pixelize", "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice", "squeezev", "squeezeh",
}


def sanitize_transition_name(name: Any, default: str = "fade") -> str:
    """Returns a valid FFmpeg xfade transition name."""
    if hasattr(name, "value"):
        raw = str(name.value).lower()
    else:
        raw = str(name).lower() if name else ""

    # Strip prefixes or symbols if any
    raw = raw.replace("-", "").replace("_", "")
    for candidate in VALID_XFADE_TRANSITIONS:
        if raw == candidate or raw == candidate.replace("_", ""):
            return candidate

    return default if default in VALID_XFADE_TRANSITIONS else "fade"


def clamp_transition_duration(prev_display: float, cur_display: float, base_duration: float = 0.6) -> float:
    """
    Computes a smooth, safe transition duration between two clips.
    Never exceeds 30% of either clip's display duration to avoid clipping or jitter.
    """
    base = max(0.04, float(base_duration or 0.6))
    max_prev = max(0.04, 0.30 * prev_display)
    max_cur = max(0.04, 0.30 * cur_display)
    return max(0.04, min(base, max_prev, max_cur))


def build_fit_filter(fit_mode: str, width: int, height: int) -> str:
    """
    Constructs the scaling and framing filter string for an image.
    Supports cover, contain, and blur_bg.
    """
    fit = fit_mode.lower() if fit_mode else "cover"
    w, h = width, height

    if fit in ("cover", ""):
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    elif fit == "contain":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    elif fit == "blur_bg":
        return (
            f"split=2[bg_fit][fg_fit];"
            f"[bg_fit]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=25[bg_b];"
            f"[fg_fit]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg_s];"
            f"[bg_b][fg_s]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    else:
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def build_motion_filter(
    motion: Any,
    fit_mode: str,
    width: int,
    height: int,
    duration: float,
    fps: int = 30,
    hold_duration: Optional[float] = None
) -> str:
    """
    Constructs an FFmpeg Ken Burns pan/zoom/tilt camera motion filter chain.
    - Prescales input image to 2x resolution (e.g. 3840x2160 for 1080p) to provide
      high-precision coordinate headroom and eliminate 1-pixel integer truncation shaking.
    - Uses continuous mathematical curves for x, y, and zoom without discontinuous jumps.
    - Strictly locks the output frame count to max(1, round(duration * fps)) using trim and setpts.
    """
    m_type = getattr(motion, "motion_type", MotionType.NONE) if motion else MotionType.NONE
    if hasattr(m_type, "value"):
        m_val = m_type.value
    else:
        m_val = str(m_type).lower() if m_type else "none"

    intensity = getattr(motion, "intensity", 1.0) if motion else 1.0
    intensity = max(0.2, min(2.0, float(intensity)))

    # If no motion, return static framing
    if not m_val or m_val in ("none", "static"):
        return build_fit_filter(fit_mode, width, height)

    w, h = width, height
    frames = max(1, int(round(duration * fps)))
    if frames <= 1:
        return build_fit_filter(fit_mode, width, height)

    d = frames

    # 2x prescaling for crisp downsampling and jitter elimination
    prescale_w = w * 2
    prescale_h = h * 2

    fit = str(fit_mode).lower() if fit_mode else "cover"
    if fit == "contain":
        pre_filter = f"scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=decrease,pad={prescale_w}:{prescale_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    elif fit == "blur_bg":
        pre_filter = (
            f"split=2[bg_fit][fg_fit];"
            f"[bg_fit]scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=increase,crop={prescale_w}:{prescale_h},gblur=sigma=25[bg_b];"
            f"[fg_fit]scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=decrease,pad={prescale_w}:{prescale_h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg_s];"
            f"[bg_b][fg_s]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    else:
        pre_filter = f"scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=increase,crop={prescale_w}:{prescale_h},setsar=1"

    # Zoom depth and step
    max_zoom = round(1.0 + (0.15 * intensity), 4)
    z_pan = round(1.0 + (0.12 * intensity), 4)
    zoom_step = (max_zoom - 1.0) / d

    if m_val in ("zoom_in", "ken_burns"):
        z_expr = f"min(zoom+{zoom_step:.6f},{max_zoom:.4f})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_val == "zoom_out":
        z_expr = f"if(eq(on,1),{max_zoom:.4f},max(zoom-{zoom_step:.6f},1.0))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_val == "pan_right":
        z_expr = f"{z_pan:.4f}"
        x_expr = f"(iw-iw/zoom)*(on/{d})"
        y_expr = "(ih-ih/zoom)/2"
    elif m_val == "pan_left":
        z_expr = f"{z_pan:.4f}"
        x_expr = f"(iw-iw/zoom)*(1.0-on/{d})"
        y_expr = "(ih-ih/zoom)/2"
    elif m_val == "pan_down":
        z_expr = f"{z_pan:.4f}"
        x_expr = "(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)*(on/{d})"
    elif m_val == "pan_up":
        z_expr = f"{z_pan:.4f}"
        x_expr = "(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)*(1.0-on/{d})"
    else:
        return build_fit_filter(fit_mode, width, height)

    zp = (
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s={w}x{h}:fps={fps}"
    )
    trim = f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS,fps={fps}"
    return f"{pre_filter},{zp},{trim}"


def build_xfade_chain(
    fc_parts: List[str],
    n: int,
    slots: List[Any],
    default_trans: str = "fade",
    base_trans_dur: float = 0.6
) -> Tuple[str, float]:
    """
    Builds an FFmpeg xfade filter chain connecting streams [v0]..[v{n-1}].
    Each slot i < n-1 has segment duration = slot.display_duration + t_dur.
    The transition i -> i+1 starts at cumulative offset = sum(slots[0..i-1].display_duration).
    Returns (final_stream_label, total_rendered_duration).
    """
    if n <= 1:
        return "v0", (slots[0].display_duration if slots else 0.0)

    prev_label = "v0"
    cumulative = 0.0

    for i in range(1, n):
        prev_slot = slots[i - 1]
        cur_slot = slots[i]

        raw_trans = getattr(prev_slot, "transition_out", default_trans)
        trans_name = sanitize_transition_name(raw_trans, default=default_trans)

        t_dur = clamp_transition_duration(
            prev_slot.display_duration,
            cur_slot.display_duration,
            base_duration=base_trans_dur
        )

        cumulative += prev_slot.display_duration
        offset = max(0.01, cumulative)
        out_label = f"xf{i}" if i < n - 1 else "vout"

        fc_parts.append(
            f"[{prev_label}][v{i}]"
            f"xfade=transition={trans_name}:duration={t_dur:.3f}:offset={offset:.3f}"
            f"[{out_label}]"
        )
        prev_label = out_label

    total_dur = cumulative + slots[-1].display_duration
    return prev_label, total_dur
