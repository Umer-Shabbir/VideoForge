"""
Timeline generator.
Calculates how long each image should be displayed.
No motion/animation — images are static. Transitions are handled by xfade.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.project import RenderProfile, MotionType, TransitionType

log = logging.getLogger("videoforge.timeline")


@dataclass
class MotionParams:
    """Kept for API compatibility — motion is disabled, values unused."""
    motion_type:  MotionType = MotionType.NONE
    zoom_start:   float = 1.0
    zoom_end:     float = 1.0
    pan_x_start:  float = 0.5
    pan_x_end:    float = 0.5
    pan_y_start:  float = 0.5
    pan_y_end:    float = 0.5


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
    Returns a list of ImageSlots with correct durations.

    Timing maths
    ────────────
    Let:
      n         = number of images
      T         = total audio duration
      td        = transition duration
      seg_dur   = duration of each input clip (what -t feeds to FFmpeg)
      disp_dur  = visible time per image

    xfade formula: total_output = n*seg_dur - (n-1)*td
    We want total_output = T, so:
      seg_dur = (T + (n-1)*td) / n

    The display_duration (used for computing xfade offsets) is:
      disp_dur = seg_dur - td
    """
    profile   = project.profile
    images    = project.image_paths
    audio_dur = project.audio_duration or 0.0

    if not images:
        return []

    n = len(images)
    td = profile.transition_duration

    if n == 1:
        return [ImageSlot(
            image_path=images[0], index=0,
            display_duration=audio_dur,
            segment_duration=audio_dur,
            start_time=0.0,
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
            transition_in=profile.transition_type,
            transition_out=profile.transition_type,
        ))
        t += disp_dur

    log.debug(
        f"Timeline: {n} images, audio={audio_dur:.2f}s, "
        f"seg={seg_dur:.3f}s, disp={disp_dur:.3f}s, td={td:.2f}s"
    )
    return slots


def build_zoompan_filter(motion: MotionParams, seg_frames: int,
                          output_w: int, output_h: int, fps: int = 30) -> str:
    """Kept for API compatibility — returns simple static filter."""
    return (
        f"scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
        f"crop={output_w}:{output_h},setsar=1"
    )


def calculate_total_duration(slots: list[ImageSlot], trans_dur: float) -> float:
    if not slots:
        return 0.0
    return sum(s.display_duration for s in slots) + trans_dur
