"""
Subtitle aligner: uses faster-whisper to transcribe/align audio and produce
timed subtitle chunks. Falls back to even distribution if unavailable.
"""

import logging
import time
import threading
from pathlib import Path
from typing import Optional, Callable

from app.core.project import Project, SubtitleMode, RenderProfile
from app.subtitles.segmenter import (
    SubtitleChunk, segment_text, distribute_chunks_evenly,
    align_whisper_segments, clean_transcript
)

log = logging.getLogger("videoforge.aligner")

_MODEL_CACHE: dict = {}
_MODEL_LOCK = threading.Lock()


def align_subtitles(
    project: Project,
    progress_callback: Optional[Callable] = None,
    cancel_flag=None,
) -> list[SubtitleChunk]:
    """
    Main entry point: produce timed subtitle chunks for a project.
    Tries whisper first, falls back to even distribution.
    """
    if not project.transcript_text:
        log.info(f"[{project.name}] No transcript text — skipping subtitles")
        return []

    text = clean_transcript(project.transcript_text)
    if not text:
        return []

    mode = project.profile.subtitle_mode
    max_chars = project.profile.subtitle_max_chars
    max_lines = project.profile.subtitle_max_lines
    audio_duration = project.audio_duration or 0.0

    if progress_callback:
        progress_callback(5.0, "Preparing subtitle alignment...")

    # Try whisper alignment
    whisper_available = _check_whisper_available()
    if whisper_available and project.audio_path and project.audio_path.exists() and audio_duration > 0:
        try:
            if progress_callback:
                progress_callback(10.0, "Running audio analysis (this may take a moment)...")
            chunks = _align_with_whisper(
                project.audio_path,
                text,
                mode,
                max_chars,
                max_lines,
                project.profile.subtitle_mode,
                whisper_model=_get_whisper_model_setting(),
                whisper_device=_get_whisper_device_setting(),
                whisper_language=_get_whisper_language_setting(),
                progress_callback=progress_callback,
                cancel_flag=cancel_flag,
                transcript_segments=getattr(project, "transcript_segments", [])
            )
            if chunks:
                log.info(f"[{project.name}] Whisper alignment produced {len(chunks)} subtitle chunks")
                return chunks
        except Exception as e:
            log.warning(f"[{project.name}] Whisper alignment failed: {e}. Falling back to even distribution.")

    # Fallback: even distribution
    if progress_callback:
        progress_callback(80.0, "Using even text distribution...")

    chunks_text = segment_text(text, mode, max_chars, max_lines)
    if audio_duration > 0:
        chunks = distribute_chunks_evenly(chunks_text, audio_duration)
    else:
        chunks = [SubtitleChunk(text=c) for c in chunks_text]

    log.info(f"[{project.name}] Even distribution produced {len(chunks)} subtitle chunks")
    return chunks


def _check_whisper_available() -> bool:
    try:
        import faster_whisper
        return True
    except ImportError:
        return False


def _get_whisper_model_setting() -> str:
    try:
        from app.core.app_state import AppState
        return AppState.instance().settings.get("whisper_model", "small")
    except Exception:
        return "small"


def _get_whisper_device_setting() -> str:
    try:
        from app.core.app_state import AppState
        return AppState.instance().settings.get("whisper_device", "cpu")
    except Exception:
        return "cpu"


def _get_whisper_language_setting() -> str:
    try:
        from app.core.app_state import AppState
        lang = AppState.instance().settings.get("whisper_language", "auto")
        return None if lang == "auto" else lang
    except Exception:
        return None


def _load_whisper_model(model_name: str, device: str):
    """
    Load or return a cached WhisperModel.
    Cache key is (model_name, device) — if either changes we load a new model.
    Evicts any existing model that doesn't match before loading a new one
    so memory is freed when the user changes settings mid-session.
    """
    from faster_whisper import WhisperModel

    model_key = (model_name, device)
    with _MODEL_LOCK:
        if model_key in _MODEL_CACHE:
            return _MODEL_CACHE[model_key]

        # Evict any stale model (user changed model/device in settings)
        stale = [k for k in _MODEL_CACHE if k != model_key]
        for k in stale:
            log.info(f"Evicting stale Whisper model: {k}")
            del _MODEL_CACHE[k]

        log.info(f"Loading Whisper model: {model_name} on {device}")

        import psutil as _psutil
        ram_gb = _psutil.virtual_memory().total // (1024 ** 3)
        if device == "cuda":
            compute_type = "float16"
        elif ram_gb >= 8:
            compute_type = "float32"
        else:
            compute_type = "int8"

        import os as _os
        cpu_threads = _os.cpu_count() or 4

        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=min(cpu_threads, 4),
        )
        _MODEL_CACHE[model_key] = model
        log.info(f"Whisper model loaded ({compute_type}, {cpu_threads} threads)")
        return model


def _align_with_whisper(
    audio_path: Path,
    text: str,
    mode: SubtitleMode,
    max_chars: int,
    max_lines: int,
    subtitle_mode: SubtitleMode,
    whisper_model: str = "small",
    whisper_device: str = "cpu",
    whisper_language=None,
    progress_callback: Optional[Callable] = None,
    cancel_flag=None,
    transcript_segments=None,
) -> list[SubtitleChunk]:
    """
    Run faster-whisper on audio, then align the provided text to the output.
    """
    from faster_whisper import WhisperModel

    if progress_callback:
        progress_callback(15.0, f"Loading Whisper model '{whisper_model}'...")

    # Load or retrieve cached model (evicts stale models automatically)
    model = _load_whisper_model(whisper_model, whisper_device)

    if progress_callback:
        progress_callback(25.0, "Transcribing audio...")

    if cancel_flag and cancel_flag.is_set():
        return []

    # Transcribe with word timestamps
    # beam_size=2 is 2-3x faster than default 5, with negligible quality difference
    # for subtitle alignment (we only need word-level timestamps, not perfect transcription)
    segments_gen, info = model.transcribe(
        str(audio_path),
        language=whisper_language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
        beam_size=2,          # faster than default 5; subtitle quality is identical
        best_of=2,            # faster than default 5
        temperature=0,        # deterministic, no random sampling
        condition_on_previous_text=False,  # each segment is independent → more accurate
    )

    # Collect segments (generator)
    whisper_segments = []
    total_dur = info.duration if hasattr(info, "duration") and info.duration else 0

    for seg in segments_gen:
        if cancel_flag and cancel_flag.is_set():
            return []
        words = []
        if hasattr(seg, "words") and seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                })
        whisper_segments.append({
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": words,
        })
        if total_dur > 0 and progress_callback:
            pct = 25.0 + (seg.end / total_dur) * 50.0
            progress_callback(min(75.0, pct), f"Transcribing... {seg.end:.1f}s")

    log.info(f"Whisper produced {len(whisper_segments)} segments")

    if progress_callback:
        progress_callback(78.0, "Aligning subtitle chunks to audio...")

    # Align display chunks to whisper word timestamps
    chunks = align_whisper_segments(
        whisper_segments,
        mode=subtitle_mode,
        max_chars=max_chars,
        max_lines=max_lines,
        transcript_segments=transcript_segments,
    )

    return chunks


def clear_model_cache():
    """Free whisper model memory."""
    with _MODEL_LOCK:
        _MODEL_CACHE.clear()
    log.info("Whisper model cache cleared")


def estimate_whisper_time(audio_duration: float, model_size: str = "small") -> float:
    """Rough estimate of how long whisper will take in seconds."""
    # Approximate real-time factors on CPU
    rtf = {"tiny": 0.5, "base": 0.8, "small": 1.5, "medium": 3.0, "large": 6.0}
    return audio_duration * rtf.get(model_size, 1.5)
