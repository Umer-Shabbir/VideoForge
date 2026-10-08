"""
Project validator: inspects a project before adding to queue.
Returns a ValidationResult with detailed issues, warnings, and fix suggestions.
"""

import logging
from pathlib import Path
from typing import Optional

from app.core.project import Project, ValidationResult
from app.utils.file_utils import is_audio, is_image, is_transcript, AUDIO_EXTS, IMAGE_EXTS

log = logging.getLogger("videoforge.validator")

MIN_AUDIO_DURATION = 0.5        # seconds
MAX_AUDIO_DURATION = 3 * 3600   # 3 hours
MIN_IMAGES = 1
MAX_IMAGES = 500
MAX_TRANSCRIPT_WORDS = 100_000


def validate_project(project: Project, check_files: bool = True) -> ValidationResult:
    """
    Full validation of a project. Mutates project.validation and returns it.
    If check_files=True, verifies that all referenced files exist and are readable.
    """
    result = ValidationResult()
    p = project

    # ── Folder ────────────────────────────────────────────────────────────────
    if check_files:
        if not p.folder or not p.folder.exists():
            result.add_error(
                f"Project folder not found: {p.folder}",
                "Check that the folder still exists and is accessible."
            )
            result.valid = False
            p.validation = result
            return result  # Can't continue without folder
    else:
        if not p.folder:
            result.add_error(
                "Project folder not specified.",
                "Specify a project folder."
            )
            result.valid = False
            p.validation = result
            return result

    # ── Audio ─────────────────────────────────────────────────────────────────
    if p.audio_path is None:
        if p.folder and ((p.folder / "video.mp4").exists() or (p.folder / f"{p.name}.mp4").exists()):
            pass
        else:
            result.add_error(
                "No audio file found in project folder.",
                f"Add an audio file ({', '.join(sorted(AUDIO_EXTS))}) to the folder."
            )
    else:
        if check_files:
            if not p.audio_path.exists():
                result.add_error(
                    f"Audio file missing: {p.audio_path.name}",
                    "The audio file has been moved or deleted. Re-scan the project."
                )
            elif p.audio_path.stat().st_size < 1024:
                result.add_error(
                    f"Audio file appears empty or too small: {p.audio_path.name}",
                    "Replace with a valid audio file."
                )
            else:
                _validate_audio_duration(p, result)
        else:
            # Still validate duration if we already have it
            if p.audio_duration is not None:
                _validate_audio_duration(p, result)

    # ── Images ────────────────────────────────────────────────────────────────
    if not p.image_paths:
        result.add_error(
            "No image files found in project folder.",
            f"Add images ({', '.join(sorted(IMAGE_EXTS))}) to the folder."
        )
    else:
        if len(p.image_paths) > MAX_IMAGES:
            result.add_warning(
                f"Very many images ({len(p.image_paths)}). "
                f"Processing may be slow. Consider using ≤{MAX_IMAGES}."
            )
        if check_files:
            missing = [str(img) for img in p.image_paths if not img.exists()]
            if missing:
                result.add_error(
                    f"{len(missing)} image file(s) missing: {', '.join(Path(m).name for m in missing[:3])}{'...' if len(missing) > 3 else ''}",
                    "Re-scan the project to refresh the file list."
                )
            unreadable = _check_images_readable(p.image_paths)
            if unreadable:
                result.add_warning(
                    f"{len(unreadable)} image(s) could not be read: "
                    f"{', '.join(Path(u).name for u in unreadable[:3])}"
                )

    # ── Transcript ────────────────────────────────────────────────────────────
    if p.transcript_path is None:
        result.add_warning(
            "No transcript/script file found.",
        )
        # Not an error — we can render without subtitles
    else:
        if check_files and not p.transcript_path.exists():
            result.add_error(
                f"Transcript file missing: {p.transcript_path.name}",
                "Re-scan to refresh, or add a transcript file."
            )
        elif p.transcript_text:
            word_count = len(p.transcript_text.split())
            if word_count == 0:
                result.add_warning("Transcript file appears empty — subtitles will be skipped.")
            elif word_count > MAX_TRANSCRIPT_WORDS:
                result.add_warning(
                    f"Transcript is very long ({word_count:,} words). "
                    "Alignment may take extra time."
                )
        else:
            result.add_warning("Transcript text could not be read.")

    # ── Output ────────────────────────────────────────────────────────────────
    if p.output_path and p.output_path.exists():
        result.add_warning(
            f"Output file already exists: {p.output_path.name}. "
            "It will be overwritten unless skip is enabled."
        )

    # ── Profile sanity ────────────────────────────────────────────────────────
    _validate_profile(p, result)

    # ── Final verdict ─────────────────────────────────────────────────────────
    result.valid = len(result.issues) == 0
    p.validation = result
    return result


def _validate_audio_duration(project: Project, result: ValidationResult):
    dur = project.audio_duration
    if dur is None:
        result.add_warning(
            "Audio duration could not be determined. FFprobe may not be installed."
        )
        return
    if dur < MIN_AUDIO_DURATION:
        result.add_error(
            f"Audio is too short ({dur:.2f}s). Minimum is {MIN_AUDIO_DURATION}s.",
            "Use a longer audio file."
        )
    elif dur > MAX_AUDIO_DURATION:
        result.add_warning(
            f"Audio is very long ({dur/3600:.1f} hours). Rendering may take considerable time."
        )
    if project.image_paths and dur > 0:
        time_per_image = dur / len(project.image_paths)
        if time_per_image < 1.0:
            result.add_warning(
                f"Very short display time per image ({time_per_image:.1f}s) with "
                f"{len(project.image_paths)} images. Consider using fewer images or a longer audio."
            )


def _check_images_readable(image_paths: list[Path]) -> list[str]:
    """Try opening each image with Pillow. Return list of unreadable paths."""
    unreadable = []
    try:
        from PIL import Image, UnidentifiedImageError
        for img_path in image_paths:
            try:
                with Image.open(img_path) as img:
                    img.verify()
            except (UnidentifiedImageError, Exception):
                unreadable.append(str(img_path))
    except ImportError:
        pass  # Pillow not installed, skip check
    return unreadable


def _validate_profile(project: Project, result: ValidationResult):
    profile = project.profile
    if profile.width < 64 or profile.height < 64:
        result.add_error(
            f"Output resolution {profile.width}x{profile.height} is too small.",
            "Set a resolution of at least 64x64."
        )
    if profile.fps < 1 or profile.fps > 120:
        result.add_error(
            f"Invalid FPS: {profile.fps}",
            "Set FPS between 1 and 120."
        )
    if profile.transition_duration < 0:
        result.add_error("Transition duration cannot be negative.")
    if profile.transition_duration >= 3.0:
        result.add_warning("Very long transitions (≥3s) may look awkward.")


def quick_validate_folder(folder: Path) -> tuple[bool, list[str]]:
    """
    Fast folder scan without creating a Project object.
    Returns (looks_valid, list_of_issues).
    """
    issues = []
    if not folder.is_dir():
        return False, ["Not a directory"]

    files = list(folder.iterdir())
    has_audio = any(f.is_file() and is_audio(f) for f in files)
    has_image = any(f.is_file() and is_image(f) for f in files)

    if not has_audio:
        issues.append("No audio file found")
    if not has_image:
        issues.append("No image files found")

    return has_audio and has_image, issues



