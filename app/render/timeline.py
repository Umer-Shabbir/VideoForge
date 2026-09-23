"""
Timeline generator.
Calculates how long each image should be displayed and computes motion parameters
(zoom in, zoom out, panning, Ken Burns).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.project import RenderProfile, MotionType, TransitionType

log = logging.getLogger("videoforge.timeline")


@dataclass
class MotionParams:
    """Parameters defining motion for a single clip slot."""
    motion_type: MotionType = MotionType.NONE
    intensity: float = 1.0


@dataclass
class ImageSlot:
    """One image in the rendered timeline."""
    image_path:       Path
    index:            int
    display_duration: float   # visible time on screen (seconds)
    segment_duration: float   # input clip duration (includes transition overlap)
    start_time:       float   # position in final video
    motion:           MotionParams = field(default_factory=MotionParams)
    transition_in:    TransitionType = TransitionType.FADE
    transition_out:   TransitionType = TransitionType.FADE


def generate_timeline(project) -> list[ImageSlot]:
    """
    Distribute images evenly across the audio duration.
    Assigns motion parameters (Ken Burns / Pan / Zoom) per slot.
    """
    profile   = project.profile
    images    = project.image_paths
    audio_dur = project.audio_duration or 0.0

    if not images:
        return []

    n = len(images)
    td = profile.transition_duration

    # Sequence of motion patterns for Ken Burns mode
    ken_burns_pattern = [
        MotionType.ZOOM_IN,
        MotionType.PAN_RIGHT,
        MotionType.ZOOM_OUT,
        MotionType.PAN_LEFT,
        MotionType.PAN_UP,
        MotionType.PAN_DOWN,
    ]

    def _resolve_motion(idx: int) -> MotionParams:
        mt = profile.motion_type
        if mt == MotionType.KEN_BURNS:
            chosen = ken_burns_pattern[idx % len(ken_burns_pattern)]
            return MotionParams(motion_type=chosen, intensity=profile.motion_intensity)
        return MotionParams(motion_type=mt, intensity=profile.motion_intensity)

    if n == 1:
        return [ImageSlot(
            image_path=images[0], index=0,
            display_duration=audio_dur,
            segment_duration=audio_dur,
            start_time=0.0,
            motion=_resolve_motion(0),
        )]

    # Clamp transition duration so we never get negative display time
    max_td    = audio_dur / (n * 2)
    td        = min(td, max_td)

    seg_dur   = (audio_dur + (n - 1) * td) / n
    disp_dur  = seg_dur - td

    # Ensure minimum sensible values
    seg_dur  = max(seg_dur,  0.5)
    disp_dur = max(disp_dur, 0.1)

    slots = []
    t = 0.0
    for i, img in enumerate(images):
        slots.append(ImageSlot(
            image_path=img, index=i,
            display_duration=disp_dur,
            segment_duration=seg_dur,
            start_time=t,
            motion=_resolve_motion(i),
            transition_in=profile.transition_type,
            transition_out=profile.transition_type,
        ))
        t += disp_dur

    log.debug(
        f"Timeline: {n} images, audio={audio_dur:.2f}s, "
        f"seg={seg_dur:.3f}s, disp={disp_dur:.3f}s, td={td:.2f}s, "
        f"motion={profile.motion_type.value}"
    )
    return slots


def build_zoompan_filter(motion: MotionParams, seg_frames: int,
                          output_w: int, output_h: int, fps: int = 30) -> str:
    """
    Build FFmpeg zoompan filter string for motion animations.

    Inputs to zoompan filter are assumed to be pre-scaled to 2*w x 2*h
    (or similar HD headroom) so zooming in won't reveal pixelation.
    """
    d = max(1, seg_frames)
    intensity = max(0.1, min(2.0, motion.intensity))
    mtype = motion.motion_type

    if mtype == MotionType.NONE or intensity <= 0:
        return (
            f"scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
            f"crop={output_w}:{output_h},setsar=1"
        )

    # Max zoom depth based on intensity
    max_zoom = 1.0 + (0.35 * intensity)
    # Zoom increment per frame for smooth zoom_in / zoom_out
    zoom_step = (max_zoom - 1.0) / d

    if mtype == MotionType.ZOOM_IN:
        # Smooth zoom in toward center
        z_expr = f"min(zoom+{zoom_step:.6f},{max_zoom:.4f})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    elif mtype == MotionType.ZOOM_OUT:
        # Smooth zoom out from max_zoom to 1.0
        z_expr = f"if(eq(on,1),{max_zoom:.4f},max(zoom-{zoom_step:.6f},1.0))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    elif mtype == MotionType.PAN_LEFT:
        # Pan camera from right to left with constant slight zoom
        z_level = 1.15 + (0.15 * (intensity - 1.0))
        z_expr = f"{z_level:.4f}"
        x_expr = f"(iw-iw/zoom)*(1.0-on/{d})"
        y_expr = "(ih-ih/zoom)/2"

    elif mtype == MotionType.PAN_RIGHT:
        # Pan camera from left to right with constant slight zoom
        z_level = 1.15 + (0.15 * (intensity - 1.0))
        z_expr = f"{z_level:.4f}"
        x_expr = f"(iw-iw/zoom)*(on/{d})"
        y_expr = "(ih-ih/zoom)/2"

    elif mtype == MotionType.PAN_UP:
        # Pan camera from bottom to top
        z_level = 1.15 + (0.15 * (intensity - 1.0))
        z_expr = f"{z_level:.4f}"
        x_expr = "(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)*(1.0-on/{d})"

    elif mtype == MotionType.PAN_DOWN:
        # Pan camera from top to bottom
        z_level = 1.15 + (0.15 * (intensity - 1.0))
        z_expr = f"{z_level:.4f}"
        x_expr = "(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)*(on/{d})"

    else:
        # Fallback to static frame fit
        return (
            f"scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
            f"crop={output_w}:{output_h},setsar=1"
        )

    # Pre-scale image to 2x output resolution before zoompan to ensure crisp quality
    # zoompan outputs at s=w x h
    prescale_w = output_w * 2
    prescale_h = output_h * 2

    filter_str = (
        f"scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=increase,"
        f"crop={prescale_w}:{prescale_h},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={d}:s={output_w}x{output_h}:fps={fps},"
        f"setsar=1"
    )
    return filter_str


def calculate_total_duration(slots: list[ImageSlot], trans_dur: float) -> float:
    if not slots:
        return 0.0
    return sum(s.display_duration for s in slots) + trans_dur

