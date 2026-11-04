"""
Project scanner service: takes a folder path, finds valid project folders,
and creates Project objects with detected files and metadata.
"""

import time
import logging
from pathlib import Path
from typing import Optional

from app.core.project import Project, ProjectStatus, RenderProfile
from app.utils.file_utils import detect_project_files, read_transcript_segments, scan_for_project_folders
from app.utils.ffmpeg_utils import get_audio_duration
from app.validators.project_validator import validate_project

log = logging.getLogger("videoforge.scanner")


def sync_project_preset_styling(project: Project, settings_manager=None) -> bool:
    """
    Ensure the project's profile has the proper typography & subtitle styling
    defined for its preset (from settings or master registry).
    Returns True if styling was updated, False otherwise.
    """
    if not project:
        return False

    preset_name = getattr(project, "preset_name", "") or ""

    # If preset is empty or Default, check folder for project.json or metadata.json
    if not preset_name or preset_name.lower() == "default":
        folder = getattr(project, "folder", None)
        if folder:
            fpath = Path(folder)
            meta_file = fpath / "project.json"
            if not meta_file.exists():
                meta_file = fpath / "metadata.json"
            if meta_file.exists():
                import json
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    preset_name = meta.get("preset_name", "")
                    if preset_name:
                        project.preset_name = preset_name
                except Exception:
                    pass

    if not preset_name or preset_name.lower() == "default":
        return False

    preset_profile = None
    if settings_manager and hasattr(settings_manager, "get_preset"):
        preset_profile = settings_manager.get_preset(preset_name)

    if not preset_profile:
        try:
            from app.storage.settings_manager import SettingsManager
            defaults = SettingsManager._default_presets()
            if preset_name in defaults:
                preset_profile = RenderProfile.from_dict(defaults[preset_name])
        except Exception as e:
            log.debug(f"Could not load default presets: {e}")

    if not preset_profile:
        return False

    pr = project.profile
    # Apply typography & ASS subtitle styling from preset
    pr.subtitle_enabled = True
    pr.subtitle_font = preset_profile.subtitle_font
    pr.subtitle_font_size = preset_profile.subtitle_font_size
    pr.subtitle_bold = preset_profile.subtitle_bold
    pr.subtitle_italic = preset_profile.subtitle_italic
    pr.subtitle_spacing = preset_profile.subtitle_spacing
    pr.subtitle_uppercase = preset_profile.subtitle_uppercase
    pr.subtitle_animation = preset_profile.subtitle_animation
    pr.subtitle_primary_color = preset_profile.subtitle_primary_color
    pr.subtitle_karaoke_color = preset_profile.subtitle_karaoke_color
    pr.subtitle_karaoke_outline = preset_profile.subtitle_karaoke_outline
    pr.subtitle_outline_color = preset_profile.subtitle_outline_color
    pr.subtitle_back_color = preset_profile.subtitle_back_color
    pr.subtitle_outline_width = preset_profile.subtitle_outline_width
    pr.subtitle_shadow = preset_profile.subtitle_shadow
    pr.subtitle_border_style = preset_profile.subtitle_border_style
    pr.subtitle_margin_v = preset_profile.subtitle_margin_v
    pr.subtitle_alignment = preset_profile.subtitle_alignment
    pr.subtitle_mode = preset_profile.subtitle_mode
    pr.subtitle_max_chars = preset_profile.subtitle_max_chars

    if preset_profile.allowed_transitions:
        pr.allowed_transitions = list(preset_profile.allowed_transitions)
    if preset_profile.transition_type:
        pr.transition_type = preset_profile.transition_type

    # Ensure transition duration is positive so transition effects are active
    dur = getattr(preset_profile, "transition_duration", 0.0) or 0.0
    pr.transition_duration = float(dur) if dur > 0 else 0.6

    # Ensure motion type and intensity are active
    mt = getattr(preset_profile, "motion_type", None)
    if not mt or str(mt).lower() in ("none", "static"):
        from app.core.project import MotionType
        pr.motion_type = MotionType.KEN_BURNS
    else:
        pr.motion_type = mt

    mi = getattr(preset_profile, "motion_intensity", 1.0) or 1.0
    pr.motion_intensity = float(mi) if mi > 0 else 1.0

    return True


class ProjectScanner:
    """
    Scans filesystem for project folders and builds Project objects.
    Can be run synchronously or called from a worker thread.
    """

    def __init__(
        self,
        recursive: bool = True,
        max_depth: int = 5,
        auto_validate: bool = True,
        default_profile: Optional[RenderProfile] = None,
        preferred_audio: str = "",
        preferred_script: str = "",
        audio_keywords: str = "narration,voiceover,audio,voice",
        script_keywords: str = "script,transcript,narration,text",
        settings_manager = None,
    ):
        self.recursive = recursive
        self.max_depth = max_depth
        self.auto_validate = auto_validate
        self.default_profile = default_profile or RenderProfile()
        self.preferred_audio = preferred_audio
        self.preferred_script = preferred_script
        self.audio_keywords = audio_keywords
        self.script_keywords = script_keywords
        self.settings_manager = settings_manager

    def scan_folder(
        self,
        root: Path,
        progress_callback=None,
        cancel_flag=None,
    ) -> list[Project]:
        """
        Scan root (and children if recursive) for project folders.
        Returns list of Project objects.

        progress_callback(pct: float, message: str) — optional
        cancel_flag: object with .is_set() method — check for cancellation
        """
        root = Path(root)
        log.info(f"Scanning: {root} (recursive={self.recursive})")

        if progress_callback:
            progress_callback(0.0, f"Finding project folders in {root.name}...")

        # First, find candidate folders
        if self._is_project_folder(root):
            # Root itself is a project
            candidates = [root]
        else:
            candidates = scan_for_project_folders(root, self.recursive, self.max_depth)

        if not candidates:
            log.info(f"No project folders found in {root}")
            return []

        log.info(f"Found {len(candidates)} candidate folder(s)")
        projects = []

        for i, folder in enumerate(candidates):
            if cancel_flag and cancel_flag.is_set():
                log.info("Scan cancelled by user")
                break

            pct = (i / len(candidates)) * 100
            if progress_callback:
                progress_callback(pct, f"Processing {folder.name} ({i+1}/{len(candidates)})...")

            project = self._build_project(folder)
            if project:
                projects.append(project)

        if progress_callback:
            progress_callback(100.0, f"Found {len(projects)} project(s)")

        return projects

    def scan_single_folder(self, folder: Path) -> Optional[Project]:
        """Build a Project from a single specific folder."""
        folder = Path(folder)
        return self._build_project(folder)

    def _is_project_folder(self, folder: Path) -> bool:
        """
        Quick check if folder looks like a direct project (not a parent container).
        A folder is a project if it directly contains at least one audio file
        OR at least one image file (at the top level or in an 'images/' subfolder).
        A container folder only has sub-directories but no media files at its root.
        """
        from app.utils.file_utils import is_audio, is_image
        try:
            # Check direct children
            files = [f for f in folder.iterdir() if f.is_file()]
            has_audio = any(is_audio(f) for f in files)
            has_image = any(is_image(f) for f in files)
            if not has_image:
                sub_img = folder / "images"
                if sub_img.is_dir():
                    has_image = any(is_image(f) for f in sub_img.iterdir() if f.is_file())
            return has_audio or has_image
        except PermissionError:
            return False

    def _build_project(self, folder: Path) -> Optional[Project]:
        """Build a Project from a folder. Returns None if folder is unreadable."""
        try:
            detected = detect_project_files(
                folder,
                preferred_audio=self.preferred_audio,
                preferred_script=self.preferred_script,
                audio_keywords=self.audio_keywords,
                script_keywords=self.script_keywords,
            )
        except Exception as e:
            log.error(f"Failed to scan {folder}: {e}")
            return None

        project = Project(
            folder=folder,
            name=folder.name,
        )

        # Resolve preset and styling
        project.profile = RenderProfile.from_dict(self.default_profile.to_dict())
        meta_file = folder / "project.json"
        if not meta_file.exists():
            meta_file = folder / "metadata.json"
        if meta_file.exists():
            import json
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                project.preset_name = meta.get("preset_name", "")
            except Exception:
                pass

        synced = sync_project_preset_styling(project, self.settings_manager)
        if synced:
            log.info(f"Loaded preset '{project.preset_name}' with subtitle style ({project.profile.subtitle_font} {project.profile.subtitle_font_size}pt) for project {folder.name}")
        else:
            if not project.preset_name:
                project.preset_name = "Default"
            log.info(f"Preset '{project.preset_name}' using default profile for {folder.name}.")

        from app.core.project import SubtitleMode
        if self.settings_manager:
            if self.settings_manager.get("sub_enabled", True) or project.profile.subtitle_mode == SubtitleMode.KARAOKE:
                project.profile.subtitle_enabled = True

        # Set files
        project.audio_path = detected.get("audio")
        project.bgm_path = detected.get("bgm")
        project.transcript_path = detected.get("transcript")
        project.prompts_path = detected.get("prompts")
        project.image_paths = detected.get("images", [])

        # Read scene chunks from prompts file if available
        if project.prompts_path:
            try:
                from app.utils.file_utils import parse_prompts_file
                project.scene_chunks = parse_prompts_file(project.prompts_path)
                log.info(f"Loaded {len(project.scene_chunks)} scene chunks from {project.prompts_path.name} for {folder.name}")
            except Exception as e:
                log.warning(f"Could not parse prompts file for {folder.name}: {e}")

        # Get audio duration
        if project.audio_path:
            try:
                dur = get_audio_duration(project.audio_path)
                project.audio_duration = dur
            except Exception as e:
                log.warning(f"Could not get audio duration for {folder.name}: {e}")

        # Read transcript text
        if project.transcript_path:
            try:
                from app.utils.file_utils import read_transcript_segments
                text, segments = read_transcript_segments(project.transcript_path)
                project.transcript_text = text
                if segments:
                    project.transcript_segments = segments
                if text:
                    project.transcript_word_count = len(text.split())
            except Exception as e:
                log.warning(f"Could not read transcript for {folder.name}: {e}")

        # Ensure chapters.txt is generated if script.txt is present and chapters.txt is missing
        chapters_file = folder / "chapters.txt"
        if not chapters_file.exists() and (folder / "script.txt").exists():
            try:
                from app.services.chapter_generator import generate_chapters_for_project
                generate_chapters_for_project(folder, final_duration=project.audio_duration)
            except Exception as chap_err:
                log.debug(f"Could not auto-generate chapters for {folder.name} on scan: {chap_err}")

        # Run validation
        if self.auto_validate:
            try:
                validate_project(project, check_files=True)
                project.status = (
                    ProjectStatus.VALID if project.validation.valid
                    else ProjectStatus.INVALID
                )
            except Exception as e:
                log.error(f"Validation failed for {folder.name}: {e}")
                project.validation.issues.append(f"Validation error: {e}")
                project.validation.valid = False
                project.status = ProjectStatus.INVALID
        else:
            project.status = ProjectStatus.DISCOVERED

        log.debug(
            f"Project '{project.name}': status={project.status.value}, "
            f"images={project.image_count}, "
            f"audio_dur={project.audio_duration:.1f}s" if project.audio_duration else
            f"Project '{project.name}': status={project.status.value}"
        )
        return project

    def refresh_project(self, project: Project) -> Project:
        """Re-scan a project's folder and update its metadata."""
        refreshed = self._build_project(project.folder)
        if refreshed:
            # Preserve ID and settings
            refreshed.id = project.id
            refreshed.profile = project.profile
            refreshed.output_folder = project.output_folder
            refreshed.notes = project.notes
            return refreshed
        return project


def make_scanner_from_settings(settings) -> "ProjectScanner":
    """Convenience: build a ProjectScanner with user preferences from settings."""
    return ProjectScanner(
        recursive=settings.get("recursive_scan", True),
        max_depth=settings.get("max_scan_depth", 5),
        auto_validate=True,
        default_profile=settings.get_default_profile(),
        preferred_audio=settings.get("preferred_audio_name", ""),
        preferred_script=settings.get("preferred_script_name", ""),
        audio_keywords=settings.get("preferred_audio_keywords",
                                    "narration,voiceover,audio,voice"),
        script_keywords=settings.get("preferred_script_keywords",
                                     "script,transcript,narration,text"),
        settings_manager=settings,
    )




