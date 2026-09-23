"""
Subtitle segmenter: splits a text transcript into subtitle chunks
appropriate for different display modes (classic, phrase, viral, word).
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from app.core.project import SubtitleMode

log = logging.getLogger("videoforge.segmenter")


@dataclass
class SubtitleChunk:
    """A single subtitle segment with text and optional timing."""
    text: str
    start: Optional[float] = None    # seconds
    end: Optional[float] = None      # seconds
    words: list[str] = field(default_factory=list)
    word_starts: list[float] = field(default_factory=list)
    word_ends: list[float] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        if self.start is not None and self.end is not None:
            return self.end - self.start
        return None

    def ass_start(self) -> str:
        return _seconds_to_ass(self.start or 0)

    def ass_end(self) -> str:
        return _seconds_to_ass(self.end or 0)

    def srt_start(self) -> str:
        return _seconds_to_srt(self.start or 0)

    def srt_end(self) -> str:
        return _seconds_to_srt(self.end or 0)


def _seconds_to_ass(s: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cs"""
    s = max(0.0, s)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    cs = int((sec % 1) * 100)
    return f"{h}:{m:02d}:{int(sec):02d}.{cs:02d}"


def _seconds_to_srt(s: float) -> str:
    """Convert seconds to SRT time format HH:MM:SS,mmm"""
    s = max(0.0, s)
    ms = int((s % 1) * 1000)
    s = int(s)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def clean_transcript(text: str) -> str:
    """Normalize whitespace and remove problematic characters from transcript."""
    if not text:
        return ""
    # Normalize line endings
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    text = text.strip()
    # Remove control characters
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return text


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using punctuation heuristics."""
    text = clean_transcript(text)
    if not text:
        return []
    # Split on sentence-ending punctuation followed by space + uppercase
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z\'""])', text)
    return [s.strip() for s in sentences if s.strip()]


def split_into_phrases(text: str, max_words: int = 8, max_chars: int = 42) -> list[str]:
    """
    Split text into short, natural-sounding phrases.
    Respects punctuation boundaries first, then word limits.
    """
    text = clean_transcript(text)
    if not text:
        return []

    # First split on natural phrase boundaries (commas, semicolons, dashes, sentence ends)
    raw_parts = re.split(r'(?<=[,;:!?.…])\s+|(?<=—)\s*', text)
    raw_parts = [p.strip() for p in raw_parts if p.strip()]

    result = []
    for part in raw_parts:
        words = part.split()
        if not words:
            continue
        # If part fits within limits, keep as-is
        if len(words) <= max_words and len(part) <= max_chars:
            result.append(part)
            continue
        # Otherwise, split by word count
        current = []
        for word in words:
            current.append(word)
            phrase = " ".join(current)
            if len(current) >= max_words or len(phrase) >= max_chars:
                result.append(" ".join(current))
                current = []
        if current:
            result.append(" ".join(current))

    return result


def split_viral_style(text: str, max_words: int = 5, max_chars: int = 25) -> list[str]:
    """
    Split for viral/short-form social media captions.
    Very short chunks, maximum impact.
    """
    return split_into_phrases(text, max_words=max_words, max_chars=max_chars)


def split_word_by_word(text: str) -> list[str]:
    """Split text into individual words for word-highlight mode."""
    text = clean_transcript(text)
    return text.split()


def segment_text(text: str, mode: SubtitleMode, max_chars: int = 42, max_lines: int = 2) -> list[str]:
    """
    Main entry point: split text into display chunks according to subtitle mode.
    """
    if not text:
        return []
    text = clean_transcript(text)
    effective_max = max_chars * max_lines

    if mode == SubtitleMode.CLASSIC:
        # Sentence-level, then split long ones
        sentences = split_into_sentences(text)
        result = []
        for sent in sentences:
            if len(sent) <= effective_max:
                result.append(sent)
            else:
                result.extend(split_into_phrases(sent, max_chars=effective_max))
        return result or [text]

    elif mode == SubtitleMode.PHRASE:
        return split_into_phrases(text, max_words=8, max_chars=max_chars)

    elif mode == SubtitleMode.VIRAL:
        return split_viral_style(text, max_words=5, max_chars=25)

    elif mode == SubtitleMode.WORD:
        return split_word_by_word(text)

    return split_into_phrases(text)


def distribute_chunks_evenly(
    chunks: list[str],
    total_duration: float,
    min_duration: float = 0.8,
    padding: float = 0.1,
) -> list[SubtitleChunk]:
    """
    Distribute subtitle chunks evenly across total_duration.
    Used as fallback when whisper alignment is unavailable.
    """
    if not chunks or total_duration <= 0:
        return []

    n = len(chunks)
    # Weight each chunk by word count so longer chunks get more time
    weights = [max(1, len(c.split())) for c in chunks]
    total_weight = sum(weights)

    result = []
    current_time = 0.0

    for i, (chunk_text, weight) in enumerate(zip(chunks, weights)):
        duration = (weight / total_weight) * total_duration
        duration = max(min_duration, duration)

        # Don't let the last chunk exceed total duration
        if current_time + duration > total_duration:
            duration = max(0.1, total_duration - current_time)

        chunk = SubtitleChunk(
            text=chunk_text,
            start=current_time + padding,
            end=current_time + duration - padding,
        )
        result.append(chunk)
        current_time += duration

    # Clamp all times
    for chunk in result:
        chunk.start = max(0.0, chunk.start)
        chunk.end = min(total_duration, chunk.end)
        if chunk.end <= chunk.start:
            chunk.end = chunk.start + 0.5

    return result


def align_whisper_segments(
    whisper_segments: list[dict],
    mode: SubtitleMode,
    max_chars: int = 42,
    max_lines: int = 2,
) -> list[SubtitleChunk]:
    """
    Convert whisper segments (with word-level timestamps) into subtitle chunks.
    Each whisper segment has: 'text', 'start', 'end', optionally 'words'.

    Crucially: word_starts / word_ends are populated on every chunk so that
    the karaoke styler can generate per-word highlight events.
    """
    # ── Collect all timed words ───────────────────────────────────────────────
    timed_words: list[dict] = []
    for seg in whisper_segments:
        seg_start = seg.get("start", 0.0)
        seg_end   = seg.get("end",   0.0)
        if "words" in seg and seg["words"]:
            for w in seg["words"]:
                word = w.get("word", "").strip()
                if word:
                    timed_words.append({
                        "word":  word,
                        "start": w.get("start", seg_start),
                        "end":   w.get("end",   seg_end),
                    })
        else:
            words = seg.get("text", "").split()
            if not words:
                continue
            dur_per = (seg_end - seg_start) / len(words)
            for j, word in enumerate(words):
                timed_words.append({
                    "word":  word,
                    "start": seg_start + j * dur_per,
                    "end":   seg_start + (j + 1) * dur_per,
                })

    if not timed_words:
        return []

    # Pre-compute cleaned lowercase alphanumeric strings for timed_words
    timed_words_clean = [re.sub(r'[^\w]', '', w["word"].lower()) for w in timed_words]

    full_text = " ".join(w["word"] for w in timed_words)

    # ── Decide chunk size for karaoke / viral mode ────────────────────────────
    from app.core.project import SubtitleMode as _SM
    actual_mode = mode
    if mode == _SM.KARAOKE:
        # Karaoke uses viral-sized chunks (3-5 words) so each chunk is
        # short enough to read while the highlight moves through it
        actual_mode = _SM.VIRAL

    display_chunks = segment_text(full_text, actual_mode, max_chars, max_lines)
    if not display_chunks:
        return []

    # ── Align each chunk to word timestamps ───────────────────────────────────
    # Strategy:
    #   Walk through timed_words sequentially. For each display chunk, try to
    #   match its words in order against the next timed_words entries.
    #   Whisper often merges punctuation into tokens ("world," vs "world") so
    #   we strip non-word characters before comparing.
    #   If a chunk can't be matched we fall back to consuming the next N words
    #   directly to avoid the word_idx pointer drifting off track.
    result: list[SubtitleChunk] = []
    word_idx = 0
    total_timed = len(timed_words)

    for chunk_text in display_chunks:
        chunk_words = chunk_text.split()
        if not chunk_words:
            continue
        if word_idx >= total_timed:
            break  # exhausted timed words — remaining chunks get no timing

        chunk_words_clean = [re.sub(r'[^\w]', '', w.lower()) for w in chunk_words]

        start_time      = None
        end_time        = None
        matched         = 0
        chunk_word_data: list[dict] = []

        # Search window: don't let it go too far past current position
        search_limit = min(word_idx + len(chunk_words) + 8, total_timed)

        for i in range(word_idx, search_limit):
            tw       = timed_words[i]
            tw_clean = timed_words_clean[i]
            ck_clean = chunk_words_clean[matched] if matched < len(chunk_words_clean) else ""

            is_match = bool(
                tw_clean and ck_clean and (
                    tw_clean == ck_clean
                    or tw_clean.startswith(ck_clean)
                    or ck_clean.startswith(tw_clean)
                )
            )

            if is_match:
                if matched == 0:
                    start_time = tw["start"]
                    word_idx   = i       # anchor the pointer at first match
                chunk_word_data.append(tw)
                matched += 1
                end_time = tw["end"]
                if matched >= len(chunk_words):
                    word_idx = i + 1    # advance past last matched word
                    break
            elif matched > 0:
                # Partial match — accept if we got at least half the words
                if matched >= max(1, len(chunk_words) // 2):
                    word_idx = i        # don't advance past the unmatched word
                    break
                # Otherwise reset and keep looking from current position
                # (handles cases where a spurious near-match fires early)
                matched = 0
                chunk_word_data = []
                start_time = None
                end_time = None

        # Fallback: consume the next N timed words directly
        if start_time is None and word_idx < total_timed:
            n          = len(chunk_words)
            end_idx    = min(word_idx + n, total_timed)
            start_time = timed_words[word_idx]["start"]
            end_time   = timed_words[end_idx - 1]["end"]
            chunk_word_data = timed_words[word_idx:end_idx]
            word_idx   = end_idx
            log.debug(
                f"align_whisper: fallback consumed {n} words for chunk '{chunk_text[:30]}'"
            )

        if start_time is None or end_time is None:
            continue

        # Pad end_time if it equals start (Whisper can give zero-duration words)
        if end_time <= start_time:
            end_time = start_time + max(
                0.1, (chunk_word_data[-1]["end"] - chunk_word_data[0]["start"])
            )

        chunk = SubtitleChunk(
            text=chunk_text,
            start=max(0.0, start_time),
            end=max(start_time + 0.05, end_time),
            words=[w["word"] for w in chunk_word_data],
            word_starts=[w["start"] for w in chunk_word_data],
            word_ends=[w["end"]   for w in chunk_word_data],
        )
        result.append(chunk)

    return result
