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


def generate_timeline(project, sub_chunks: Optional[list] = None) -> list[ImageSlot]:
    """
    Generate image slots synchronized 1:1 with subtitle chunks.
    Each subtitle chunk i gets its corresponding image (e.g. 1.png, 2.png, ...)
    displayed for that chunk's exact timestamp duration.
    Transitions are dynamically varied across boundaries based on the preset's allowed_transitions.
    Falls back to even distribution if no subtitle chunks exist.
    """
    profile   = project.profile
    images    = project.image_paths
    audio_dur = project.audio_duration or 0.0

    if not images:
        return []

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

    # Allowed transitions pool from profile
    raw_allowed = getattr(profile, "allowed_transitions", None)
    if raw_allowed:
        allowed_trans = [t.lower() for t in raw_allowed if t and t.lower() != "none"]
    else:
        allowed_trans = []
    if not allowed_trans:
        def_t = profile.transition_type.value if hasattr(profile.transition_type, "value") else str(profile.transition_type)
        allowed_trans = [def_t] if def_t.lower() != "none" else ["fade"]

    def _get_transition_type(name: str) -> TransitionType:
        try:
            return TransitionType(name.lower())
        except Exception:
            return TransitionType.FADE

    td_base = max(0.05, getattr(profile, "transition_duration", 0.5))

    # ── Scene Script Chunk to Image Synchronization Mode (Primary for automation) ──
    # Images in automated video production correspond 1:1 with scene chunks from prompts.txt.
    # Each image must remain on screen while its script chunk is narrated.
    scene_chunks = getattr(project, "scene_chunks", None)
    if not scene_chunks:
        prompts_file = getattr(project, "prompts_path", None)
        if not prompts_file and getattr(project, "folder", None):
            cand = Path(project.folder) / "prompts.txt"
            if cand.exists():
                prompts_file = cand
        if prompts_file and Path(prompts_file).exists():
            try:
                from app.utils.file_utils import parse_prompts_file
                scene_chunks = parse_prompts_file(prompts_file)
            except Exception as e:
                log.warning(f"Could not parse prompts file for timeline: {e}")
                scene_chunks = None

    if scene_chunks and images:
        import re
        from app.utils.file_utils import align_scenes_with_timed_segments, parse_srt_segments

        timed_segs = None
        if sub_chunks:
            timed_segs = sub_chunks
        elif getattr(project, "transcript_path", None) and str(project.transcript_path).lower().endswith(".srt") and Path(project.transcript_path).exists():
            try:
                timed_segs = parse_srt_segments(project.transcript_path)
            except Exception:
                timed_segs = None
        elif getattr(project, "folder", None):
            for cand_name in ("transcript.srt", "audio.srt"):
                cand_p = Path(project.folder) / cand_name
                if cand_p.exists():
                    try:
                        timed_segs = parse_srt_segments(cand_p)
                        if timed_segs:
                            break
                    except Exception:
                        pass

        if not timed_segs and getattr(project, "transcript_segments", None):
            timed_segs = project.transcript_segments

        aligned_scenes = align_scenes_with_timed_segments(
            scenes=scene_chunks,
            timed_segments=timed_segs or [],
            audio_duration=audio_dur,
        )

        img_map: dict[int, Path] = {}
        for img in images:
            m = re.search(r"(\d+)", img.stem)
            if m:
                num = int(m.group(1))
                if num not in img_map:
                    img_map[num] = img

        num_scenes = len(aligned_scenes)
        slots = []

        for i, sc in enumerate(aligned_scenes):
            sc_num = sc.get("scene_number", i + 1)
            if sc_num in img_map:
                img_path = img_map[sc_num]
            elif i < len(images):
                img_path = images[i]
            else:
                img_path = images[-1]

            c_start = max(0.0, float(sc.get("start", 0.0)))
            disp_dur = max(0.1, float(sc.get("display_duration", 2.5)))

            # Cycle transition across adjacent slots
            out_trans_name = allowed_trans[i % len(allowed_trans)]
            trans_out = _get_transition_type(out_trans_name)
            trans_in = slots[i - 1].transition_out if i > 0 else _get_transition_type(allowed_trans[0])

            clamped_td = max(0.05, min(td_base, 0.3 * disp_dur))
            seg_dur = disp_dur + clamped_td if i < num_scenes - 1 else disp_dur

            slots.append(ImageSlot(
                image_path=img_path,
                index=i,
                display_duration=disp_dur,
                segment_duration=seg_dur,
                start_time=c_start,
                motion=_resolve_motion(i),
                transition_in=trans_in,
                transition_out=trans_out,
            ))

        log.info(
            f"Timeline (scene script chunk mode): {len(slots)} slots, "
            f"audio={audio_dur:.2f}s, transitions={len(allowed_trans)} variants"
        )
        return slots

    # Resolve chunks if not passed directly
    chunks = sub_chunks or getattr(project, "sub_chunks", None)
    if not chunks and project.transcript_path and str(project.transcript_path).lower().endswith(".srt") and project.transcript_path.exists():
        try:
            from app.utils.file_utils import parse_srt_segments
            from app.subtitles.segmenter import create_chunks_from_srt_segments
            timed_segs = parse_srt_segments(project.transcript_path)
            if timed_segs:
                chunks = create_chunks_from_srt_segments(timed_segs, audio_duration=audio_dur)
        except Exception:
            chunks = None

    # ── 1:1 Subtitle Chunk to Image Synchronization Mode ──────────────────────
    # Only synchronize 1:1 if image count matches subtitle chunk count, or if explicitly configured.
    # Otherwise, distribute images evenly across the audio timeline and overlay subtitles independently.
    if chunks and (len(chunks) == len(images) or getattr(project, "sync_mode_1_to_1", False)):
        import re
        img_map: dict[int, Path] = {}
        for img in images:
            m = re.match(r"^(\d+)\b", img.stem)
            if m:
                img_map[int(m.group(1))] = img

        num_chunks = len(chunks)
        slots = []

        for i, chunk in enumerate(chunks):
            chunk_num = i + 1
            if chunk_num in img_map:
                img_path = img_map[chunk_num]
            elif i < len(images):
                img_path = images[i]
            else:
                img_path = images[-1]

            c_start = max(0.0, float(chunk.start or 0.0))
            c_end = float(chunk.end or (c_start + 1.0))
            if i == num_chunks - 1 and audio_dur > c_end and (audio_dur - c_end) <= 10.0:
                c_end = audio_dur

            disp_dur = max(0.1, c_end - c_start)

            # Cycle transition across adjacent slots
            out_trans_name = allowed_trans[i % len(allowed_trans)]
            trans_out = _get_transition_type(out_trans_name)
            trans_in = slots[i - 1].transition_out if i > 0 else _get_transition_type(allowed_trans[0])

            clamped_td = max(0.05, min(td_base, 0.3 * disp_dur))
            seg_dur = disp_dur + clamped_td if i < num_chunks - 1 else disp_dur

            slots.append(ImageSlot(
                image_path=img_path,
                index=i,
                display_duration=disp_dur,
                segment_duration=seg_dur,
                start_time=c_start,
                motion=_resolve_motion(i),
                transition_in=trans_in,
                transition_out=trans_out,
            ))

        log.debug(
            f"Timeline (1:1 chunk mode): {len(slots)} slots, "
            f"audio={audio_dur:.2f}s, transitions={len(allowed_trans)} variants"
        )
        return slots

    # ── Fallback: Evenly distribute images across audio ────────────────────────
    n = len(images)
    if n == 1:
        return [ImageSlot(
            image_path=images[0], index=0,
            display_duration=audio_dur,
            segment_duration=audio_dur,
            start_time=0.0,
            motion=_resolve_motion(0),
        )]

    max_td = audio_dur / (n * 2)
    td = min(td_base, max_td)
    seg_dur = (audio_dur + (n - 1) * td) / n
    disp_dur = seg_dur - td
    seg_dur = max(seg_dur, 0.5)
    disp_dur = max(disp_dur, 0.1)

    slots = []
    t = 0.0
    for i, img in enumerate(images):
        out_trans_name = allowed_trans[i % len(allowed_trans)]
        trans_out = _get_transition_type(out_trans_name)
        trans_in = slots[i - 1].transition_out if i > 0 else _get_transition_type(allowed_trans[0])

        slots.append(ImageSlot(
            image_path=img, index=i,
            display_duration=disp_dur,
            segment_duration=seg_dur,
            start_time=t,
            motion=_resolve_motion(i),
            transition_in=trans_in,
            transition_out=trans_out,
        ))
        t += disp_dur

    log.debug(
        f"Timeline (even fallback): {n} images, audio={audio_dur:.2f}s, "
        f"seg={seg_dur:.3f}s, disp={disp_dur:.3f}s, td={td:.2f}s, "
        f"transitions={len(allowed_trans)} variants"
    )
    return slots


def build_zoompan_filter(motion: MotionParams, seg_frames: int,
                          output_w: int, output_h: int, fps: int = 30) -> str:
    """
    Build FFmpeg zoompan filter string for motion animations.
    Uses 2x prescaling and continuous coordinate formulas for silky smooth movement without shaking.
    """
    d = max(1, seg_frames)
    intensity = max(0.2, min(2.0, float(getattr(motion, "intensity", 1.0) or 1.0)))
    mtype = getattr(motion, "motion_type", MotionType.NONE)

    if mtype == MotionType.NONE or intensity <= 0:
        return (
            f"scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
            f"crop={output_w}:{output_h},setsar=1"
        )

    max_zoom = round(1.0 + (0.15 * intensity), 4)
    z_pan = round(1.0 + (0.12 * intensity), 4)
    zoom_step = (max_zoom - 1.0) / d

    if mtype == MotionType.ZOOM_IN:
        z_expr = f"min(zoom+{zoom_step:.6f},{max_zoom:.4f})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    elif mtype == MotionType.ZOOM_OUT:
        z_expr = f"if(eq(on,1),{max_zoom:.4f},max(zoom-{zoom_step:.6f},1.0))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    elif mtype == MotionType.PAN_LEFT:
        z_expr = f"{z_pan:.4f}"
        x_expr = f"(iw-iw/zoom)*(1.0-on/{d})"
        y_expr = "(ih-ih/zoom)/2"

    elif mtype == MotionType.PAN_RIGHT:
        z_expr = f"{z_pan:.4f}"
        x_expr = f"(iw-iw/zoom)*(on/{d})"
        y_expr = "(ih-ih/zoom)/2"

    elif mtype == MotionType.PAN_UP:
        z_expr = f"{z_pan:.4f}"
        x_expr = "(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)*(1.0-on/{d})"

    elif mtype == MotionType.PAN_DOWN:
        z_expr = f"{z_pan:.4f}"
        x_expr = "(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)*(on/{d})"

    else:
        return (
            f"scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
            f"crop={output_w}:{output_h},setsar=1"
        )

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

