"""
VideoForge Chapter Generator Service
====================================
Generates accurate YouTube-compatible video chapters with timestamps
and saves them to `chapters.txt` in the project directory for YouTube descriptions.

YouTube Chapter Specifications:
- The first chapter MUST start at 00:00.
- Each chapter must be at least 10 seconds long.
- Chapters must be listed in chronological ascending order.
- Format: MM:SS - Chapter Title (or HH:MM:SS - Chapter Title for videos >= 1 hour).
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any

log = logging.getLogger("videoforge.chapter_generator")


def format_timestamp(seconds: float, use_hours: bool = False) -> str:
    """Formats seconds into MM:SS or HH:MM:SS for YouTube description timestamps."""
    seconds = max(0.0, seconds)
    total_secs = int(round(seconds))
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    secs = total_secs % 60

    if use_hours or hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def normalize_match_words(text: str) -> List[str]:
    """Tokenizes text into normalized lowercase alphanumeric words for fuzzy matching."""
    if not text:
        return []
    # Replace common number spellings or punctuation
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return [w for w in cleaned.split() if w]


def parse_chapters_from_script(script: str) -> List[Dict[str, str]]:
    """
    Extracts structured chapters from a script string.
    Supports formats:
      [Chapter: <Title>]
      [Chapter 1: <Title>]
      Chapter 1: <Title>
      # Chapter 1: <Title>
    """
    if not script or not isinstance(script, str):
        return []

    chapter_pattern = re.compile(
        r'(?:^|\n)\s*(?:\[\s*(?:Chapter|CHAPTER)(?:\s*\d+)?:\s*([^\]]+)\]|#*\s*(?:Chapter|CHAPTER)\s+\d+[:\-]\s*([^\n]+))\s*(?:\n|\Z)',
        re.IGNORECASE
    )

    matches = list(chapter_pattern.finditer(script))
    if not matches:
        return []

    chapters = []
    for i, match in enumerate(matches):
        raw_title = match.group(1) or match.group(2) or f"Chapter {i+1}"
        title = raw_title.strip()

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(script)
        body = script[start_pos:end_pos].strip()

        # Find the first meaningful sentence of the chapter body
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', body) if s.strip()]
        first_sentence = sentences[0] if sentences else body[:100]

        chapters.append({
            "title": title,
            "first_sentence": first_sentence,
            "text": body
        })

    return chapters


def _fallback_chapter_segmentation(script_text: str, total_duration: float) -> List[Dict[str, str]]:
    """
    Generates balanced narrative chapters if no explicit chapter tags are found in the script.
    Splits the narrative into 5-6 logical sections based on paragraph breaks.
    """
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n+', script_text) if p.strip()]
    if not paragraphs:
        return [{"title": "Introduction", "first_sentence": script_text[:80], "text": script_text}]

    num_chapters = min(6, max(3, len(paragraphs) // 3))
    default_names = [
        "Introduction",
        "The Background",
        "The Turning Point",
        "The Escalation",
        "The Climax",
        "Conclusion & Impact"
    ]

    paras_per_chapter = max(1, len(paragraphs) // num_chapters)
    chapters = []

    for i in range(num_chapters):
        start_idx = i * paras_per_chapter
        end_idx = (i + 1) * paras_per_chapter if i < num_chapters - 1 else len(paragraphs)
        chapter_paras = paragraphs[start_idx:end_idx]
        if not chapter_paras:
            continue

        body = "\n\n".join(chapter_paras)
        first_sent = re.split(r'(?<=[.!?])\s+', chapter_paras[0])[0].strip()
        title = default_names[i] if i < len(default_names) else f"Chapter {i+1}"

        chapters.append({
            "title": title,
            "first_sentence": first_sent,
            "text": body
        })

    return chapters


def _match_opening_timestamp(
    first_sentence: str,
    segments: List[Dict[str, Any]],
    min_time: float = 0.0
) -> Optional[float]:
    """
    Finds the start timestamp of a chapter by matching its first sentence
    against timed subtitle segments.
    """
    if not first_sentence or not segments:
        return None

    target_words = normalize_match_words(first_sentence)[:10]
    if not target_words:
        return None

    best_time = None
    best_score = 0

    # Search only segments after min_time
    valid_segments = [s for s in segments if s.get("start", 0.0) >= min_time - 1.0]

    for s_idx, seg in enumerate(valid_segments):
        seg_text = seg.get("text", "")
        seg_words = normalize_match_words(seg_text)
        if not seg_words:
            continue

        # Look at a sliding window of up to 4 consecutive segments to handle multi-chunk sentences
        window_words = []
        for offset in range(min(5, len(valid_segments) - s_idx)):
            window_words.extend(normalize_match_words(valid_segments[s_idx + offset].get("text", "")))
            if len(window_words) >= len(target_words) + 5:
                break

        # Check prefix match or word overlap
        matched_count = 0
        w_set = set(window_words)
        for tw in target_words:
            if tw in w_set:
                matched_count += 1

        score = matched_count / float(len(target_words))
        if score > 0.6 and score > best_score:
            best_score = score
            best_time = seg.get("start", 0.0)
            if score >= 0.85:
                break

    return best_time


def generate_chapters_for_project(
    project_folder: Path,
    output_file: Optional[Path] = None,
    sub_chunks: Optional[List[Any]] = None,
    final_duration: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Generates YouTube-compliant video chapters with accurate timestamps
    and writes them to `chapters.txt` in the project directory.

    Returns list of dicts:
      [
        {"title": "The Midnight Break-In", "timestamp": "00:00", "seconds": 0.0},
        {"title": "The Cultural Fortress", "timestamp": "00:52", "seconds": 52.0},
        ...
      ]
    """
    project_folder = Path(project_folder).resolve()
    if not project_folder.exists() or not project_folder.is_dir():
        log.warning(f"Invalid project folder for chapter generation: {project_folder}")
        return []

    # 1. Read script and metadata
    script_path = project_folder / "script.txt"
    script_text = script_path.read_text(encoding="utf-8", errors="replace") if script_path.exists() else ""

    meta_path = project_folder / "project.json"
    if not meta_path.exists():
        meta_path = project_folder / "metadata.json"

    meta_data = {}
    if meta_path.exists():
        try:
            meta_data = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass

    # 2. Extract chapters
    raw_chapters = parse_chapters_from_script(script_text)

    # If no markers in script, check if project.json contains pre-extracted chapters
    if not raw_chapters and meta_data.get("chapters"):
        for ch in meta_data["chapters"]:
            if isinstance(ch, dict):
                raw_chapters.append({
                    "title": ch.get("title", "Chapter"),
                    "first_sentence": ch.get("first_sentence", ""),
                    "text": ""
                })
            elif isinstance(ch, str):
                raw_chapters.append({
                    "title": ch,
                    "first_sentence": "",
                    "text": ""
                })

    # Total duration resolution
    total_dur = final_duration or meta_data.get("duration") or meta_data.get("estimated_duration_sec") or 0.0
    if total_dur <= 0.0 and (project_folder / "audio.wav").exists():
        try:
            from app.utils.ffmpeg_utils import get_audio_duration
            total_dur = get_audio_duration(project_folder / "audio.wav")
        except Exception:
            pass

    # Fallback to narrative segmentation if no chapters found
    if not raw_chapters:
        raw_chapters = _fallback_chapter_segmentation(script_text, total_dur)

    if not raw_chapters:
        return []

    # 3. Load timed segments from sub_chunks, audio.srt, or transcript.srt
    timed_segments: List[Dict[str, Any]] = []

    if sub_chunks:
        for chunk in sub_chunks:
            t = getattr(chunk, "text", "")
            s = getattr(chunk, "start_time", 0.0)
            e = getattr(chunk, "end_time", 0.0)
            timed_segments.append({"start": float(s), "end": float(e), "text": str(t)})

    if not timed_segments:
        for srt_candidate in ["audio.srt", "transcript.srt"]:
            p = project_folder / srt_candidate
            if p.exists():
                try:
                    from app.utils.file_utils import parse_srt_segments
                    timed_segments = parse_srt_segments(p)
                    if timed_segments:
                        break
                except Exception:
                    pass

    # Determine if hours format is needed
    max_duration = total_dur
    if timed_segments:
        max_duration = max(max_duration, timed_segments[-1].get("end", 0.0))
    use_hours = (max_duration >= 3600.0)

    # 4. Calculate accurate timestamps
    final_chapters: List[Dict[str, Any]] = []
    prev_time = 0.0

    for idx, ch in enumerate(raw_chapters):
        title = ch.get("title", f"Chapter {idx+1}").strip()
        first_sent = ch.get("first_sentence", "").strip()

        if idx == 0:
            # YouTube Rule #1: First timestamp MUST be 00:00
            chap_seconds = 0.0
        else:
            # Match timestamp against timed segments
            min_allowed = prev_time + 10.0  # YouTube requires >= 10s between chapters
            matched_t = _match_opening_timestamp(first_sent, timed_segments, min_time=min_allowed)

            if matched_t is not None and matched_t >= min_allowed:
                chap_seconds = matched_t
            else:
                # Proportional fallback if segment matching was inconclusive
                if total_dur > 0 and len(raw_chapters) > 1:
                    prop = (idx / float(len(raw_chapters))) * total_dur
                    chap_seconds = max(min_allowed, round(prop, 1))
                else:
                    chap_seconds = min_allowed

        # Guard against exceeding total duration
        if total_dur > 0 and chap_seconds >= total_dur and idx > 0:
            chap_seconds = max(prev_time + 10.0, total_dur - 1.0)

        prev_time = chap_seconds
        ts_str = format_timestamp(chap_seconds, use_hours=use_hours)

        final_chapters.append({
            "title": title,
            "timestamp": ts_str,
            "seconds": chap_seconds
        })

    # 5. Format YouTube chapters text
    chapter_lines = [f"{ch['timestamp']} - {ch['title']}" for ch in final_chapters]
    chapters_content = "\n".join(chapter_lines) + "\n"

    # Write chapters.txt
    target_out = output_file or (project_folder / "chapters.txt")
    target_out.write_text(chapters_content, encoding="utf-8")
    log.info(f"[{project_folder.name}] YouTube chapters successfully written: {target_out}")

    # 6. Update project.json if exists
    if meta_path.exists():
        try:
            meta_data["chapters"] = final_chapters
            cur_desc = meta_data.get("seo_description", "")
            if cur_desc and "00:00" not in cur_desc and chapter_lines:
                meta_data["seo_description"] = cur_desc.rstrip() + "\n\nTimestamps:\n" + "\n".join(chapter_lines)
            meta_path.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning(f"Could not update project.json with chapters: {e}")

    return final_chapters
