"""
File and path utilities for VideoForge.
Handles Windows paths, format detection, and folder scanning.
"""

import os
import re
import hashlib
import shutil
from pathlib import Path
from typing import Optional, Any, cast
import logging

log = logging.getLogger("videoforge.file_utils")

# ─── Supported Format Sets ────────────────────────────────────────────────────

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
TRANSCRIPT_EXTS = {".txt", ".srt", ".json", ".md", ".docx", ".vtt"}

# ─── Path Utilities ────────────────────────────────────────────────────────────

def normalize_path(path) -> Path:
    """Return a resolved, normalized Path. Works on Windows and POSIX."""
    return Path(path).resolve()


def ffmpeg_path(path) -> str:
    """Convert a Path to a string suitable for FFmpeg on Windows (forward slashes)."""
    return str(Path(path).resolve()).replace("\\", "/")


def safe_filename(name: str, max_len: int = 128) -> str:
    """Strip characters that are illegal in Windows filenames."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name[:max_len] if len(name) > max_len else name or "untitled"


def unique_output_path(base: Path, suffix: str = "") -> Path:
    """If base already exists, append _2, _3, etc. until unique."""
    if not base.exists():
        return base
    stem = base.stem
    ext = base.suffix
    parent = base.parent
    i = 2
    while True:
        candidate = parent / f"{stem}{suffix}_{i}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_size_str(path: Path) -> str:
    """Human-readable file size string."""
    try:
        size = float(path.stat().st_size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except Exception:
        return "?"


def file_md5(path: Path, chunk=65536) -> str:
    """Compute MD5 hash of a file for change detection / dedup."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while chunk_data := f.read(chunk):
                h.update(chunk_data)
        return h.hexdigest()
    except Exception:
        return ""


# ─── Format Detection ─────────────────────────────────────────────────────────

def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def is_transcript(path: Path) -> bool:
    return path.suffix.lower() in TRANSCRIPT_EXTS


def detect_project_files(folder: Path,
                         preferred_audio: str = "",
                         preferred_script: str = "",
                         audio_keywords: str = "narration,voiceover,audio,voice",
                         script_keywords: str = "script,transcript,narration,text",
                         bgm_keywords: str = "bgm,music,background,song") -> dict:
    """
    Scan a folder and detect audio, bgm, images, and transcript files.

    preferred_audio / preferred_script: exact filename to prefer (e.g. "narration.mp3")
    audio_keywords / script_keywords / bgm_keywords: comma-separated keywords to rank candidates

    Returns dict: {audio, bgm, images, transcript, issues}
    """
    result: dict[str, Any] = {"audio": None, "bgm": None, "images": [], "transcript": None, "prompts": None, "issues": []}
    issues = cast(list[str], result["issues"])
    if not folder.is_dir():
        issues.append(f"Not a directory: {folder}")
        return result

    all_files = list(folder.iterdir())
    audio_candidates = [f for f in all_files if f.is_file() and is_audio(f)]

    # ── Check for images in both root folder and 'images/' subfolder ──────────
    image_candidates = [f for f in all_files if f.is_file() and is_image(f)]
    images_subfolder = folder / "images"
    if images_subfolder.is_dir():
        image_candidates.extend([f for f in images_subfolder.iterdir() if f.is_file() and is_image(f)])

    image_candidates = sorted(image_candidates, key=lambda f: _natural_sort_key(f.name))
    transcript_candidates = [f for f in all_files if f.is_file() and is_transcript(f)]

    # ── Audio selection ────────────────────────────────────────────────────────
    def _pick_audio(candidates, preferred_name, keywords):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # 1) Exact preferred filename match
        if preferred_name:
            for f in candidates:
                if f.name.lower() == preferred_name.lower():
                    return f
        # 2) Keyword priority match (first keyword wins)
        for kw in [k.strip().lower() for k in keywords.split(",") if k.strip()]:
            for f in candidates:
                if kw in f.stem.lower():
                    return f
        # 3) Longest stem (usually the "main" file with the full title)
        return sorted(candidates, key=lambda f: len(f.stem), reverse=True)[0]

    if audio_candidates:
        # Separate BGM candidates from main audio candidates based on exact exclusions if necessary
        # However, _pick_audio handles finding the main audio.
        # Let's find bgm first by running _pick_audio on bgm keywords.
        bgm_obj = _pick_audio(audio_candidates, "", bgm_keywords)
        # If the returned object has a bgm keyword match, assign to bgm
        if bgm_obj and any(kw in bgm_obj.stem.lower() for kw in [k.strip().lower() for k in bgm_keywords.split(",") if k.strip()]):
            result["bgm"] = bgm_obj
            # Remove bgm from general audio candidates to avoid it being picked as narration
            audio_candidates.remove(bgm_obj)

    if audio_candidates:
        result["audio"] = _pick_audio(audio_candidates, preferred_audio, audio_keywords)
        if len(audio_candidates) > 1:
            audio_obj = result['audio']
            name = audio_obj.name if audio_obj else 'unknown'
            issues.append(
                f"Multiple audio files ({len(audio_candidates)}). Using main: {name}"
            )
    else:
        issues.append("No main audio file found")

    # ── Images ─────────────────────────────────────────────────────────────────
    images_dir = folder / "images"
    if images_dir.is_dir():
        img_files = list(images_dir.iterdir())
        images_dir_candidates = sorted([f for f in img_files if f.is_file() and is_image(f)],
                                       key=lambda f: _natural_sort_key(f.name))
        if images_dir_candidates:
            image_candidates = images_dir_candidates

    result["images"] = image_candidates
    if not image_candidates:
        issues.append("No image files found")

    # ── Transcript selection ───────────────────────────────────────────────────
    def _pick_transcript(candidates, preferred_name, keywords):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # 1) Exact preferred filename match
        if preferred_name:
            for f in candidates:
                if f.name.lower() == preferred_name.lower():
                    return f
        # Priority for the unified standard name (SRT/VTT first)
        for f in candidates:
            if f.name.lower() in ("transcript.srt", "audio.srt", "transcript.vtt", "audio.vtt"):
                return f
        # 2) Timed subtitle files (.srt, .vtt) take priority over plain text scripts
        timed = [f for f in candidates if f.suffix.lower() in (".srt", ".vtt")]
        if timed:
            for kw in [k.strip().lower() for k in keywords.split(",") if k.strip()]:
                for f in timed:
                    if kw in f.stem.lower():
                        return f
            return timed[0]
        # 3) Keyword match on remaining candidates
        for kw in [k.strip().lower() for k in keywords.split(",") if k.strip()]:
            for f in candidates:
                if kw in f.stem.lower():
                    return f
        # 4) Extension priority
        for ext in [".srt", ".vtt", ".txt", ".json", ".docx", ".md"]:
            match = [t for t in candidates if t.suffix.lower() == ext]
            if match:
                return match[0]
        return candidates[0]

    if transcript_candidates:
        result["transcript"] = _pick_transcript(transcript_candidates, preferred_script, script_keywords)
        if len(transcript_candidates) > 1:
            transcript_obj = result["transcript"]
            name = transcript_obj.name if transcript_obj else "unknown"
            issues.append(
                f"Multiple transcript files ({len(transcript_candidates)}). Using: {name}"
            )
    else:
        issues.append("No transcript/script file found (subtitles disabled)")

    # ── Scene Prompts selection ───────────────────────────────────────────────
    prompts_candidates = [
        f for f in all_files
        if f.is_file() and f.name.lower() in ("prompts.txt", "prompt.txt", "scene_prompts.txt", "scenes.txt")
    ]
    if prompts_candidates:
        result["prompts"] = prompts_candidates[0]

    return result


def _natural_sort_key(name: str):
    """Sort key for natural number ordering: 1,2,3,...,10,11 instead of 1,10,11,2."""
    import re as _re
    parts = _re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def read_transcript_text(path: Path) -> Optional[str]:
    """
    Read and return plain text from a transcript file.
    Handles .txt, .srt, .vtt, .json, .docx
    """
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="replace").strip()

        elif ext == ".srt":
            return _parse_srt_text(path)

        elif ext == ".vtt":
            return _parse_vtt_text(path)

        elif ext == ".json":
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            # Support various JSON formats
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                for key in ("text", "transcript", "content", "script"):
                    if key in data:
                        return str(data[key])
            if isinstance(data, list):
                # List of segments
                texts = []
                for seg in data:
                    if isinstance(seg, dict):
                        texts.append(seg.get("text", ""))
                    elif isinstance(seg, str):
                        texts.append(seg)
                return " ".join(texts)
            return str(data)

        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(str(path))
                return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                log.warning("python-docx not installed, cannot read .docx files")
                return None
        return None
    except Exception as e:
        log.error(f"Failed to read transcript {path}: {e}")
        return None
    return None


def _parse_srt_text(path: Path) -> str:
    """Extract plain text from an SRT file."""
    import re
    text = path.read_text(encoding="utf-8", errors="replace")
    # Remove block numbers and timestamps
    cleaned = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}", "", cleaned)
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    return " ".join(lines)


def parse_srt_segments(path: Path | str) -> list[dict]:
    """Parse an SRT file into a list of timed segment dicts: [{'start': float, 'end': float, 'text': str}, ...]."""
    import re
    try:
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log.error(f"Failed to read SRT file {path}: {e}")
        return []
    pattern = re.compile(
        r'(\d+)\s*\n'
        r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n'
        r'(.*?)(?=\n\s*\n\d+\s*\n|\Z)',
        re.DOTALL
    )
    segs = []
    for m in pattern.finditer(text):
        sh, sm, ss, sms = map(int, m.group(2, 3, 4, 5))
        eh, em, es, ems = map(int, m.group(6, 7, 8, 9))
        start = sh * 3600 + sm * 60 + ss + sms / 1000.0
        end = eh * 3600 + em * 60 + es + ems / 1000.0
        txt = re.sub(r'<[^>]+>', '', m.group(10))
        txt = ' '.join(txt.strip().split())
        if txt:
            segs.append({'start': start, 'end': end, 'text': txt})
    return segs


def parse_prompts_file(path: Path | str) -> list[dict]:
    """
    Parse a prompts.txt file into a list of structured scene dicts:
    [{
        'scene_number': int,
        'narration': str,
        'start_time': Optional[float],
        'end_time': Optional[float],
        'start_str': Optional[str],
        'end_str': Optional[str],
        'image_prompt': str
    }, ...]
    """
    import re
    try:
        path = Path(path)
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log.error(f"Failed to read prompts file {path}: {e}")
        return []

    def _parse_time_str(t_str: Optional[str]) -> Optional[float]:
        if not t_str:
            return None
        m = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)', t_str.strip())
        if m:
            h, mn, s, ms = m.groups()
            return int(h) * 3600 + int(mn) * 60 + int(s) + int(ms.ljust(3, '0')[:3]) / 1000.0
        return None

    # Split by SCENE headers (e.g. --- SCENE 1 --- or === SCENE 1 ===)
    scene_blocks = re.split(r'(?:^|\n)\s*(?:---|===)\s*SCENE\s*(\d+)\s*(?:---|===)', text, flags=re.IGNORECASE)
    scenes = []
    if len(scene_blocks) > 1:
        for i in range(1, len(scene_blocks), 2):
            try:
                sc_num = int(scene_blocks[i])
            except ValueError:
                sc_num = len(scenes) + 1
            block = scene_blocks[i + 1]

            # Extract timestamp range if present: [00:00:00,000 --> 00:00:02,305]
            time_m = re.search(r'\[(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\]', block)
            start_str = time_m.group(1) if time_m else None
            end_str = time_m.group(2) if time_m else None
            start_t = _parse_time_str(start_str)
            end_t = _parse_time_str(end_str)

            # Extract Narration
            narr_m = re.search(
                r'Narration:\s*(.*?)(?=\n(?:Visual|Characters|Location|Lighting|Lighting/Mood|Mood|Camera|Image Prompt):|\Z)',
                block,
                re.DOTALL | re.IGNORECASE
            )
            narration = narr_m.group(1).strip() if narr_m else ""

            # Extract Image Prompt
            prompt_m = re.search(r'Image Prompt:\s*(.*?)(?=\n(?:---|===)\s*SCENE|\Z)', block, re.DOTALL | re.IGNORECASE)
            prompt = prompt_m.group(1).strip() if prompt_m else ""

            scenes.append({
                "scene_number": sc_num,
                "narration": narration,
                "start_time": start_t,
                "end_time": end_t,
                "start_str": start_str,
                "end_str": end_str,
                "image_prompt": prompt,
            })
    else:
        # Fallback: check if line-by-line format
        lines = text.splitlines()
        current_sc = 1
        cur_narr = ""
        cur_prompt = ""
        for line in lines:
            line_s = line.strip()
            if line_s.lower().startswith("narration:"):
                cur_narr = line_s.split(":", 1)[1].strip()
            elif line_s.lower().startswith("image prompt:"):
                cur_prompt = line_s.split(":", 1)[1].strip()
                scenes.append({
                    "scene_number": current_sc,
                    "narration": cur_narr,
                    "start_time": None,
                    "end_time": None,
                    "start_str": None,
                    "end_str": None,
                    "image_prompt": cur_prompt,
                })
                current_sc += 1
                cur_narr = ""
                cur_prompt = ""

    return scenes


def align_scenes_with_timed_segments(
    scenes: list[dict],
    timed_segments: list[dict],
    audio_duration: float = 0.0
) -> list[dict]:
    """
    Aligns scene script chunks against timed audio segments (e.g. from SRT or Whisper)
    using monotonic sequence matching.
    Calculates exact start and end timestamps so each image corresponds precisely
    to when its script chunk is spoken in the audio.
    """
    if not scenes:
        return []

    # If no timed segments provided, check if scenes already have timestamps
    if not timed_segments:
        all_have_times = all(s.get("start_time") is not None and s.get("end_time") is not None for s in scenes)
        if all_have_times:
            result = []
            for i, s in enumerate(scenes):
                st = float(s["start_time"])
                et = float(s["end_time"])
                if i < len(scenes) - 1 and scenes[i + 1].get("start_time") is not None:
                    next_st = float(scenes[i + 1]["start_time"])
                    disp_dur = max(0.1, next_st - st)
                else:
                    disp_dur = max(0.1, (audio_duration - st) if audio_duration > st else (et - st))
                res_scene = dict(s)
                res_scene["start"] = st
                res_scene["end"] = et
                res_scene["display_duration"] = disp_dur
                result.append(res_scene)
            return result

        # Fallback: proportional word-count distribution across audio_duration
        if audio_duration > 0:
            total_words = sum(max(1, len(s.get("narration", "").split())) for s in scenes) or 1
            cur_t = 0.0
            result = []
            for i, s in enumerate(scenes):
                w_count = max(1, len(s.get("narration", "").split()))
                dur = (w_count / total_words) * audio_duration
                res_scene = dict(s)
                res_scene["start"] = cur_t
                res_scene["end"] = cur_t + dur
                res_scene["display_duration"] = max(0.1, dur)
                result.append(res_scene)
                cur_t += dur
            return result

        return [dict(s, start=i * 2.5, end=(i + 1) * 2.5, display_duration=2.5) for i, s in enumerate(scenes)]

    import difflib

    def _norm(w: str) -> str:
        return re.sub(r'[^\w]', '', w.lower())

    # 1. Flatten scene words
    scene_words = []
    scene_word_to_sc = []
    for sc_idx, s in enumerate(scenes):
        ws = [_norm(w) for w in s.get("narration", "").split() if _norm(w)]
        for w in ws:
            scene_words.append(w)
            scene_word_to_sc.append(sc_idx)

    # 2. Flatten timed segment words
    srt_words = []
    srt_word_times = []
    for seg in timed_segments:
        st = float(seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0))
        et = float(seg.get("end", st + 1.0) if isinstance(seg, dict) else getattr(seg, "end", st + 1.0))
        txt = str(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", ""))
        ws = [_norm(w) for w in txt.split() if _norm(w)]
        if not ws:
            continue
        dur = max(0.01, (et - st) / len(ws))
        for i, w in enumerate(ws):
            srt_words.append(w)
            srt_word_times.append((st + i * dur, st + (i + 1) * dur))

    if not srt_words:
        return align_scenes_with_timed_segments(scenes, [], audio_duration=audio_duration)

    # 3. Match using SequenceMatcher
    matcher = difflib.SequenceMatcher(None, scene_words, srt_words)
    scene_word_times = [None] * len(scene_words)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for off in range(i2 - i1):
                scene_word_times[i1 + off] = srt_word_times[j1 + off]

    # 4. Interpolate gaps for unmatched scene words
    last_t = srt_word_times[0][0] if srt_word_times else 0.0
    for i in range(len(scene_word_times)):
        if scene_word_times[i] is None:
            next_t = None
            next_i = None
            for k in range(i + 1, len(scene_word_times)):
                if scene_word_times[k] is not None:
                    next_t = scene_word_times[k][0]
                    next_i = k
                    break
            if next_t is None:
                next_t = srt_word_times[-1][1] if srt_word_times else (audio_duration or (last_t + 2.0))
                next_i = len(scene_word_times)
            span_count = max(1, next_i - i + 1)
            step = max(0.01, (next_t - last_t) / span_count)
            scene_word_times[i] = (last_t + step, last_t + step * 2)
        last_t = scene_word_times[i][1]

    # 5. Compute scene start and end times
    raw_timings = []
    prev_st = 0.0
    for sc_idx in range(len(scenes)):
        w_indices = [idx for idx, s_idx in enumerate(scene_word_to_sc) if s_idx == sc_idx]
        if w_indices:
            st = scene_word_times[w_indices[0]][0]
            et = scene_word_times[w_indices[-1]][1]
        else:
            st = prev_st
            et = prev_st + 1.0
        st = max(prev_st, st)
        et = max(st + 0.1, et)
        raw_timings.append((st, et))
        prev_st = st

    # 6. Build final scene dicts with display durations
    result = []
    num_scenes = len(scenes)
    for idx, s in enumerate(scenes):
        st, et = raw_timings[idx]
        if idx == 0:
            st = 0.0  # Scene 1 displays from start of video

        if idx < num_scenes - 1:
            next_st = raw_timings[idx + 1][0]
            disp_dur = max(0.1, next_st - st)
        else:
            disp_dur = max(0.1, (audio_duration - st) if audio_duration > st else (et - st))

        res_scene = dict(s)
        res_scene["start"] = st
        res_scene["end"] = et
        res_scene["display_duration"] = disp_dur
        result.append(res_scene)

    return result


def _parse_vtt_text(path: Path) -> str:
    """Extract plain text from a WebVTT file."""
    import re
    text = path.read_text(encoding="utf-8", errors="replace")
    cleaned = re.sub(r"WEBVTT.*?\n\n", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    lines = [l.strip() for l in cleaned.splitlines() if l.strip() and not l.startswith("NOTE")]
    return " ".join(lines)


def read_transcript_segments(path: Path) -> tuple[Optional[str], list[dict]]:
    """
    Read transcript and return (full_text, segments_with_speakers).
    Extracts explicit speaker labels like "Speaker 1: text" or "[Speaker A] text".
    """
    text = read_transcript_text(path)
    if not text:
        return None, []

    # Heuristic parsing for speaker tags:
    # "Speaker 1: Hello" or "[Host] Welcome"
    import re
    segments = []

    # Check if lines have speaker prefixes
    lines = text.splitlines() if "\n" in text else re.split(r'(?<=[.!?])\s+(?=[A-Z\[])', text)
    current_speaker = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match [Speaker] or Speaker:
        m = re.match(r'^\[([^\]]+)\]\s*(.*)$', line)
        if m:
            current_speaker = m.group(1).strip()
            content = m.group(2).strip()
            if content:
                segments.append({"speaker": current_speaker, "text": content})
            continue

        m = re.match(r'^([^:]+):\s*(.*)$', line)
        # Verify it's a short speaker name, not a weird colon usage
        if m and len(m.group(1)) < 20:
            current_speaker = m.group(1).strip()
            content = m.group(2).strip()
            if content:
                segments.append({"speaker": current_speaker, "text": content})
            continue

        segments.append({"speaker": current_speaker, "text": line})

    full_text_clean = " ".join(s["text"] for s in segments)
    return full_text_clean, segments


def scan_for_project_folders(root: Path, recursive: bool = True, max_depth: int = 4) -> list[Path]:
    """
    Return a list of folders that contain a valid project
    (at least one image AND at least one audio file).

    When recursive=False, still checks immediate child folders (depth 1)
    since the user-selected folder is typically a container, not the project itself.
    When recursive=True, scans up to max_depth levels deep.
    """
    candidates = []

    def _scan(folder: Path, depth: int):
        if depth > max_depth:
            return
        try:
            files = list(folder.iterdir())
        except PermissionError:
            return
        has_audio = any(f.is_file() and is_audio(f) for f in files)
        has_image = any(f.is_file() and is_image(f) for f in files)
        images_sub = folder / "images"
        if not has_image and images_sub.is_dir():
            has_image = any(f.is_file() and is_image(f) for f in images_sub.iterdir())

        if has_audio and has_image:
            candidates.append(folder)
            return  # Don't recurse into confirmed project folders

        # Always recurse at depth 0 (the user-selected root may be a container).
        # Only stop recursing at depth >= 1 when recursive=False.
        if recursive or depth == 0:
            for f in files:
                if f.is_dir():
                    _scan(f, depth + 1)

    _scan(root, 0)
    return candidates


def copy_file_safe(src: Path, dst: Path) -> bool:
    """Copy a file, creating parent directories as needed."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception as e:
        log.error(f"Failed to copy {src} -> {dst}: {e}")
        return False

