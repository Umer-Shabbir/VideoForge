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
    speaker: Optional[str] = None    # identified speaker for this chunk

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


def create_chunks_from_srt_segments(
    timed_segments: list[dict],
    audio_duration: float = 0.0,
    transcript_segments: Optional[list[dict]] = None
) -> list[SubtitleChunk]:
    """
    Directly converts pre-timed SRT segments into SubtitleChunk objects.
    Preserves strict 1:1 chunk mapping so that Chunk i corresponds to Image i.
    Populates word_starts and word_ends per chunk for frame-accurate karaoke highlight.
    """
    if not timed_segments:
        return []

    chunks = []
    spk_map = {}
    if transcript_segments:
        for seg in transcript_segments:
            txt = clean_transcript(seg.get("text", "")).lower()
            spk = seg.get("speaker")
            if txt and spk:
                spk_map[txt[:40]] = spk

    for i, seg in enumerate(timed_segments):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.0))
        text = clean_transcript(seg.get("text", ""))
        if not text:
            continue

        words = text.split()
        n_words = len(words)
        dur = max(0.05, end - start)

        # Proportional word timing: long words receive proportionally more active time
        # than short words (e.g. "a", "in" vs "cryptanalyst", "decentralized")
        raw_lens = [max(1, len(re.sub(r'[^\w]', '', w))) for w in words]
        total_len = sum(raw_lens) or 1

        w_starts = []
        w_ends = []
        cur_w_start = start
        for w_len in raw_lens:
            w_span = (w_len / total_len) * dur
            w_starts.append(cur_w_start)
            cur_w_start += w_span
            w_ends.append(cur_w_start)
        if w_ends:
            w_ends[-1] = max(w_starts[-1] + 0.04, end)

        speaker = None
        clean_prefix = text.lower()[:40]
        for k, spk in spk_map.items():
            if k in clean_prefix or clean_prefix in k:
                speaker = spk
                break

        chunks.append(SubtitleChunk(
            text=text,
            start=max(0.0, start),
            end=max(start + 0.05, end),
            words=words,
            word_starts=w_starts,
            word_ends=w_ends,
            speaker=speaker,
        ))

    # Clamp or stretch the last chunk to audio_duration if near the end
    if chunks and audio_duration > 0 and chunks[-1].end < audio_duration:
        gap = audio_duration - chunks[-1].end
        if gap <= 10.0:
            chunks[-1].end = audio_duration
            if chunks[-1].word_ends:
                chunks[-1].word_ends[-1] = audio_duration

    return chunks


def align_whisper_segments(
    whisper_segments: list[dict],
    mode: SubtitleMode,
    max_chars: int = 42,
    max_lines: int = 2,
    transcript_segments: Optional[list[dict]] = None,
    audio_duration: float = 0.0,
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
        elif "word" in seg:
            word = seg.get("word", "").strip()
            if word:
                timed_words.append({
                    "word":  word,
                    "start": seg.get("start", seg_start),
                    "end":   seg.get("end",   seg_end),
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

    # Assign speakers to timed words if transcript segments exist
    if transcript_segments:
        # Flatten transcript into a list of (word, speaker)
        ts_words = []
        for seg in transcript_segments:
            spk = seg.get("speaker")
            wds = seg.get("text", "").split()
            for w in wds:
                ts_words.append((w, spk))

        # Simple parallel walk to assign speakers to timed_words
        ts_idx = 0
        ts_len = len(ts_words)
        for tw in timed_words:
            w_clean = re.sub(r'[^\w]', '', tw["word"].lower())
            assigned_spk = None
            for offset in range(min(5, ts_len - ts_idx)):
                ts_w, ts_spk = ts_words[ts_idx + offset]
                ts_w_clean = re.sub(r'[^\w]', '', ts_w.lower())
                if (w_clean == ts_w_clean) or (len(w_clean) > 2 and (w_clean in ts_w_clean or ts_w_clean in w_clean)):
                    assigned_spk = ts_spk
                    ts_idx += offset + 1
                    break

            if not assigned_spk and ts_idx < ts_len:
                assigned_spk = ts_words[ts_idx][1]
                ts_idx += 1

            tw["speaker"] = assigned_spk

    # Pre-compute cleaned lowercase alphanumeric strings for timed_words
    timed_words_clean = [re.sub(r'[^\w]', '', w["word"].lower()) for w in timed_words]
    full_text = " ".join(w["word"] for w in timed_words)

    from app.core.project import SubtitleMode as _SM
    actual_mode = mode
    if mode == _SM.KARAOKE:
        actual_mode = _SM.VIRAL

    display_chunks = []
    if transcript_segments:
        for seg in transcript_segments:
            seg_chunks = segment_text(seg["text"], actual_mode, max_chars, max_lines)
            for chunk_text in seg_chunks:
                display_chunks.append({"text": chunk_text, "speaker": seg.get("speaker")})
    else:
        seg_chunks = segment_text(full_text, actual_mode, max_chars, max_lines)
        for chunk_text in seg_chunks:
            display_chunks.append({"text": chunk_text, "speaker": None})

    if not display_chunks:
        return []

    result: list[SubtitleChunk] = []
    word_idx = 0
    total_timed = len(timed_words)

    for chunk_dict in display_chunks:
        chunk_text = chunk_dict["text"]
        chunk_speaker = chunk_dict["speaker"]
        chunk_words = chunk_text.split()
        if not chunk_words:
            continue
        if word_idx >= total_timed:
            # Do not break - extrapolate remaining chunks below
            break

        n_words = len(chunk_words)
        chunk_words_clean = [re.sub(r'[^\w]', '', w.lower()) for w in chunk_words]

        # Search window in timed_words
        search_limit = min(word_idx + max(n_words * 2, n_words + 15), total_timed)

        # Monotonically match words in chunk_words against timed_words
        matched_map: dict[int, int] = {}  # chunk_pos -> tw_index
        scan_pos = word_idx
        for c_pos, cw in enumerate(chunk_words_clean):
            if not cw:
                continue
            for tw_i in range(scan_pos, search_limit):
                tw = timed_words_clean[tw_i]
                if not tw:
                    continue
                if tw == cw or tw.startswith(cw) or cw.startswith(tw):
                    matched_map[c_pos] = tw_i
                    scan_pos = tw_i + 1
                    break

        w_starts: list[float] = [0.0] * n_words
        w_ends: list[float] = [0.0] * n_words

        prev_chunk_end = result[-1].end if result else (timed_words[0]["start"] if timed_words else 0.0)

        if matched_map:
            # Advance word_idx to strictly after the last matched word
            last_matched_tw_idx = max(matched_map.values())
            word_idx = last_matched_tw_idx + 1

            # Populate matched words first
            for c_pos, tw_idx in matched_map.items():
                w_starts[c_pos] = timed_words[tw_idx]["start"]
                w_ends[c_pos] = timed_words[tw_idx]["end"]

            # Interpolate leading unmatched words
            first_matched_pos = min(matched_map.keys())
            if first_matched_pos > 0:
                first_start = w_starts[first_matched_pos]
                span_start = max(prev_chunk_end, first_start - (first_matched_pos * 0.3))
                step = (first_start - span_start) / first_matched_pos
                for j in range(first_matched_pos):
                    w_starts[j] = span_start + j * step
                    w_ends[j] = span_start + (j + 1) * step

            # Interpolate internal gaps
            prev_pos = first_matched_pos
            for c_pos in sorted(matched_map.keys()):
                if c_pos > prev_pos + 1:
                    gap_count = c_pos - prev_pos - 1
                    gap_start = w_ends[prev_pos]
                    gap_end = w_starts[c_pos]
                    if gap_end <= gap_start:
                        gap_end = gap_start + (gap_count * 0.2)
                    step = (gap_end - gap_start) / (gap_count + 1)
                    for k in range(gap_count):
                        idx = prev_pos + 1 + k
                        w_starts[idx] = gap_start + k * step
                        w_ends[idx] = gap_start + (k + 1) * step
                prev_pos = c_pos

            # Interpolate trailing unmatched words
            last_matched_pos = max(matched_map.keys())
            if last_matched_pos < n_words - 1:
                tail_count = n_words - 1 - last_matched_pos
                tail_start = w_ends[last_matched_pos]
                for k in range(tail_count):
                    idx = last_matched_pos + 1 + k
                    w_starts[idx] = tail_start + k * 0.25
                    w_ends[idx] = tail_start + (k + 1) * 0.25
        else:
            # No words matched in this chunk: estimate smoothly from current audio position
            c_start = max(prev_chunk_end, timed_words[word_idx]["start"] if word_idx < total_timed else prev_chunk_end)
            c_dur = max(0.4, n_words * 0.35)
            step = c_dur / n_words
            for j in range(n_words):
                w_starts[j] = c_start + j * step
                w_ends[j] = c_start + (j + 1) * step

        # Ensure strict monotonicity and minimum duration per word
        cur_t = max(0.0, w_starts[0])
        for j in range(n_words):
            w_starts[j] = max(cur_t, w_starts[j])
            w_ends[j] = max(w_starts[j] + 0.05, w_ends[j])
            cur_t = w_ends[j]

        chunk_start = w_starts[0]
        chunk_end = max(chunk_start + 0.1, w_ends[-1])

        chunk = SubtitleChunk(
            text=chunk_text,
            start=chunk_start,
            end=chunk_end,
            words=chunk_words,
            word_starts=w_starts,
            word_ends=w_ends,
            speaker=chunk_speaker,
        )
        result.append(chunk)

    # ── Extrapolate remaining display chunks across remaining audio duration ──
    if len(result) < len(display_chunks):
        rem_chunks = display_chunks[len(result):]
        last_t = result[-1].end if result else 0.0
        target_end = max(last_t + 1.0, audio_duration if audio_duration > last_t else (timed_words[-1]["end"] if timed_words else last_t + len(rem_chunks) * 2.0))
        rem_dur = max(0.5, target_end - last_t)
        total_w = sum(max(1, len(c["text"].split())) for c in rem_chunks)
        cur_t = last_t
        for c_dict in rem_chunks:
            c_text = c_dict["text"]
            c_spk = c_dict["speaker"]
            words = c_text.split()
            w_count = max(1, len(words))
            dur = (w_count / float(total_w)) * rem_dur
            c_start = cur_t
            c_end = cur_t + dur
            w_dur = dur / w_count
            w_starts = [c_start + j * w_dur for j in range(w_count)]
            w_ends = [c_start + (j + 1) * w_dur for j in range(w_count)]
            result.append(SubtitleChunk(
                text=c_text,
                start=max(0.0, c_start),
                end=max(c_start + 0.05, c_end),
                words=words,
                word_starts=w_starts,
                word_ends=w_ends,
                speaker=c_spk,
            ))
            cur_t = c_end

    return result
