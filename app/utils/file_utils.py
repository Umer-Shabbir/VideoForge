"""
File and path utilities for VideoForge.
Handles Windows paths, format detection, and folder scanning.
"""

import os
import re
import hashlib
import shutil
from pathlib import Path
from typing import Optional
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
        size = path.stat().st_size
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
                         script_keywords: str = "script,transcript,narration,text") -> dict:
    """
    Scan a folder and detect audio, images, and transcript files.
    
    preferred_audio / preferred_script: exact filename to prefer (e.g. "narration.mp3")
    audio_keywords / script_keywords: comma-separated keywords to rank candidates
    
    Returns dict: {audio, images, transcript, issues}
    """
    result = {"audio": None, "images": [], "transcript": None, "issues": []}
    if not folder.is_dir():
        result["issues"].append(f"Not a directory: {folder}")
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
        result["audio"] = _pick_audio(audio_candidates, preferred_audio, audio_keywords)
        if len(audio_candidates) > 1:
            result["issues"].append(
                f"Multiple audio files ({len(audio_candidates)}). Using: {result['audio'].name}"
            )
    else:
        result["issues"].append("No audio file found")

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
        result["issues"].append("No image files found")

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
        # 2) Keyword match
        for kw in [k.strip().lower() for k in keywords.split(",") if k.strip()]:
            for f in candidates:
                if kw in f.stem.lower():
                    return f
        # 3) Extension priority
        for ext in [".txt", ".srt", ".json", ".vtt", ".docx", ".md"]:
            match = [t for t in candidates if t.suffix.lower() == ext]
            if match:
                return match[0]
        return candidates[0]

    if transcript_candidates:
        result["transcript"] = _pick_transcript(transcript_candidates, preferred_script, script_keywords)
        if len(transcript_candidates) > 1:
            result["issues"].append(
                f"Multiple transcript files ({len(transcript_candidates)}). Using: {result['transcript'].name}"
            )
    else:
        result["issues"].append("No transcript/script file found (subtitles disabled)")

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
    except Exception as e:
        log.error(f"Failed to read transcript {path}: {e}")
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


def _parse_vtt_text(path: Path) -> str:
    """Extract plain text from a WebVTT file."""
    import re
    text = path.read_text(encoding="utf-8", errors="replace")
    cleaned = re.sub(r"WEBVTT.*?\n\n", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    lines = [l.strip() for l in cleaned.splitlines() if l.strip() and not l.startswith("NOTE")]
    return " ".join(lines)


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
