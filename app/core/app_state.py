"""
Application state: singleton holding all runtime state.
Provides access to database, settings, queue, and project list.
"""

import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from app.core.project import Project, ProjectStatus
from app.core.queue_manager import QueueManager
from app.storage.database import Database
from app.storage.settings_manager import SettingsManager, get_app_data_dir
from app.utils.logger import setup_logging

log = logging.getLogger("videoforge.app_state")

_INSTANCE: Optional["AppState"] = None


class AppState(QObject):
    """
    Central application state. Access via AppState.instance().
    """

    # Signals
    projects_changed = Signal()
    project_updated = Signal(str)   # project_id
    ffmpeg_status_changed = Signal(bool, str)   # ok, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: dict[str, Project] = {}  # id -> Project
        self.db: Optional[Database] = None
        self.settings: Optional[SettingsManager] = None
        self.queue: Optional[QueueManager] = None
        self._initialized = False

    @classmethod
    def instance(cls) -> "AppState":
        global _INSTANCE
        if _INSTANCE is None:
            _INSTANCE = cls()
        return _INSTANCE

    def initialize(self, app_data_dir: Optional[Path] = None):
        """Initialize all subsystems. Call once at startup."""
        if self._initialized:
            return

        if app_data_dir is None:
            app_data_dir = get_app_data_dir()
        app_data_dir = Path(app_data_dir)
        app_data_dir.mkdir(parents=True, exist_ok=True)

        # Logging
        setup_logging(
            log_dir=app_data_dir / "logs",
            debug=os.environ.get("VF_DEBUG", "").lower() in ("1", "true", "yes"),
        )

        # Settings
        self.settings = SettingsManager(app_data_dir / "settings.json")
        log.info(f"Settings loaded from {app_data_dir}")

        # Re-setup logging with debug flag from settings
        if self.settings.get("debug_mode", False):
            setup_logging(log_dir=app_data_dir / "logs", debug=True)

        # Database
        self.db = Database(app_data_dir / "videoforge.db")
        log.info("Database initialized")

        # Queue manager
        max_concurrent = self.settings.get("max_concurrent_jobs", 1)
        self.queue = QueueManager(
            max_concurrent=max_concurrent,
            db=self.db,
            settings=self.settings,
        )

        # Connect queue signals for state sync
        self.queue.job_completed.connect(self._on_job_completed)
        self.queue.job_failed.connect(self._on_job_failed)
        self.queue.queue_changed.connect(self.projects_changed)

        # Load persisted projects
        self._load_persisted_projects()

        # Check FFmpeg
        self._check_ffmpeg()

        # Automatic temp directory cleanup on startup
        try:
            self.cleanup_orphaned_temp_dirs()
        except Exception as e:
            log.warning(f"Startup temp cleanup encountered an error: {e}")

        self._initialized = True
        log.info("AppState initialized successfully")

    def cleanup_orphaned_temp_dirs(self) -> tuple[int, float]:
        """
        Scan for and purge orphaned `_vf_temp` directories across all loaded projects,
        workspace folders, and system temp directory.
        Returns (purged_dir_count, reclaimed_megabytes).
        """
        import shutil
        import tempfile
        purged_count = 0
        total_bytes = 0

        # Gather target folders to check
        target_dirs = set()
        for p in self._projects.values():
            if p.folder and Path(p.folder).exists():
                target_dirs.add(Path(p.folder) / "_vf_temp")

        # Also check configured workspace / import directories
        if self.settings:
            ws = self.settings.get("workspace_folder", "")
            if ws and Path(ws).exists():
                try:
                    for child in Path(ws).iterdir():
                        if child.is_dir():
                            target_dirs.add(child / "_vf_temp")
                except Exception:
                    pass

        # Also scan system temp for orphaned vf temp dirs
        sys_temp = Path(tempfile.gettempdir())
        try:
            for p in sys_temp.glob("_vf_temp*"):
                if p.is_dir():
                    target_dirs.add(p)
            for p in sys_temp.glob("videoforge_*"):
                if p.is_dir():
                    target_dirs.add(p)
        except Exception:
            pass

        for td in target_dirs:
            if td.exists() and td.is_dir():
                try:
                    # Calculate size
                    dir_size = sum(f.stat().st_size for f in td.glob("**/*") if f.is_file())
                    shutil.rmtree(td, ignore_errors=True)
                    purged_count += 1
                    total_bytes += dir_size
                    log.info(f"Purged orphaned temp directory: {td} ({dir_size / (1024*1024):.2f} MB)")
                except Exception as exc:
                    log.warning(f"Could not purge temp directory {td}: {exc}")

        reclaimed_mb = total_bytes / (1024 * 1024)
        if purged_count > 0:
            log.info(f"Automatic temp cleanup: purged {purged_count} orphaned temp directories ({reclaimed_mb:.2f} MB reclaimed)")
        else:
            log.debug("Automatic temp cleanup: no orphaned temp directories found")

        return purged_count, reclaimed_mb

    def _load_persisted_projects(self):
        """Load project list from database, re-checking file existence."""
        if not self.db:
            return
        try:
            from app.services.project_scanner import sync_project_preset_styling
            projects = self.db.load_all_projects()
            for p in projects:
                # Reset stuck processing state
                if p.status == ProjectStatus.PROCESSING:
                    p.status = ProjectStatus.FAILED
                    p.error_message = "Interrupted by application restart"

                # Synchronize preset typography and subtitle styles
                sync_project_preset_styling(p, self.settings)

                # Re-validate file existence — files may have moved since last run
                if p.status not in (ProjectStatus.COMPLETED, ProjectStatus.FAILED,
                                     ProjectStatus.CANCELLED, ProjectStatus.INVALID):
                    if p.audio_path and not p.audio_path.exists():
                        p.status = ProjectStatus.INVALID
                        p.validation.valid = False
                        msg = f"Audio file no longer exists: {p.audio_path.name}"
                        if msg not in p.validation.issues:
                            p.validation.issues.append(msg)
                        log.warning(f"[{p.name}] {msg}")
                    missing_imgs = [img for img in p.image_paths if not img.exists()]
                    if missing_imgs:
                        p.status = ProjectStatus.INVALID
                        p.validation.valid = False
                        msg = f"{len(missing_imgs)} image file(s) missing"
                        if msg not in p.validation.issues:
                            p.validation.issues.append(msg)
                        log.warning(f"[{p.name}] {msg}")

                self._projects[p.id] = p
                self.db.save_project(p)
            log.info(f"Loaded {len(projects)} projects from database")
        except Exception as e:
            log.error(f"Failed to load projects from database: {e}")

    def _check_ffmpeg(self):
        from app.utils.ffmpeg_utils import (
            check_ffmpeg_ready, invalidate_ffmpeg_cache, find_ffmpeg
        )
        custom = self.settings.get("ffmpeg_path", "") if self.settings else ""
        if custom:
            from app.utils import ffmpeg_utils
            ffmpeg_utils._ffmpeg_path = custom
        ok, msg = check_ffmpeg_ready(force=True)  # force on startup/settings change
        self.ffmpeg_status_changed.emit(ok, msg)
        if not ok:
            log.warning(f"FFmpeg check: {msg}")

    # ─── Project Management ───────────────────────────────────────────────────

    def add_project(self, project: Project) -> bool:
        """Add a project to the state. Updates existing project if duplicate folder."""
        from app.services.project_scanner import sync_project_preset_styling
        # Check for duplicate folders
        for existing in self._projects.values():
            if existing.folder == project.folder:
                # Update existing project with newly scanned profile/preset
                existing.preset_name = project.preset_name or existing.preset_name
                sync_project_preset_styling(existing, self.settings)
                if project.audio_path:
                    existing.audio_path = project.audio_path
                if project.transcript_path:
                    existing.transcript_path = project.transcript_path
                if project.image_paths:
                    existing.image_paths = project.image_paths
                if project.prompts_path:
                    existing.prompts_path = project.prompts_path
                if self.db:
                    self.db.save_project(existing)
                self.project_updated.emit(existing.id)
                self.projects_changed.emit()
                log.info(f"Updated existing project from folder: {project.folder} (preset: {existing.preset_name})")
                return False

        sync_project_preset_styling(project, self.settings)
        self._projects[project.id] = project
        if self.db:
            self.db.save_project(project)
        self.projects_changed.emit()
        return True

    def add_projects(self, projects: list[Project]) -> int:
        """Add multiple projects. Returns count of newly added."""
        added = 0
        for p in projects:
            if self.add_project(p):
                added += 1
        return added

    def update_project(self, project: Project):
        """Update a project in state and database."""
        self._projects[project.id] = project
        if self.db:
            self.db.save_project(project)
        self.project_updated.emit(project.id)
        self.projects_changed.emit()

    def save_project(self, project: Project):
        """Alias for update_project for backward compatibility."""
        self.update_project(project)

    def remove_project(self, project_id: str):
        """Remove a project from state and database."""
        project = self._projects.pop(project_id, None)
        if self.db and project:
            self.db.delete_project(project_id)
            self.db.delete_jobs_for_project(project_id)
        self.projects_changed.emit()

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def get_all_projects(self) -> list[Project]:
        return list(self._projects.values())

    def get_projects_by_status(self, status: ProjectStatus) -> list[Project]:
        return [p for p in self._projects.values() if p.status == status]

    def get_stats(self) -> dict:
        projects = list(self._projects.values())
        # Use cached check — calling check_ffmpeg_ready() every 2s spawns
        # 'ffmpeg -version' which times out while FFmpeg is busy rendering
        from app.utils.ffmpeg_utils import check_ffmpeg_ready
        ffmpeg_ok, ffmpeg_msg = check_ffmpeg_ready(force=False)  # cached

        stats = {
            "total_projects": len(projects),
            "valid": sum(1 for p in projects if p.status == ProjectStatus.VALID),
            "invalid": sum(1 for p in projects if p.status == ProjectStatus.INVALID),
            "completed": sum(1 for p in projects if p.status == ProjectStatus.COMPLETED),
            "failed": sum(1 for p in projects if p.status == ProjectStatus.FAILED),
            "processing": sum(1 for p in projects if p.status == ProjectStatus.PROCESSING),
            "queued": sum(1 for p in projects if p.status == ProjectStatus.QUEUED),
            "total_images": sum(len(p.image_paths) for p in projects),
            "total_audio_duration": sum(p.audio_duration or 0 for p in projects),
            "ffmpeg_ok": ffmpeg_ok,
            "ffmpeg_msg": ffmpeg_msg,
        }
        if self.queue:
            stats.update(self.queue.get_stats())
        return stats

    # ─── Queue Shortcuts ──────────────────────────────────────────────────────

    def queue_project(self, project: Project, priority: int = 0) -> bool:
        """Add a valid project to the render queue."""
        if not self.queue:
            return False
        if project.status not in (ProjectStatus.VALID, ProjectStatus.FAILED, ProjectStatus.CANCELLED):
            log.warning(f"Cannot queue project with status: {project.status}")
            return False

        # Resolve output path from template if not already set
        if self.settings and (not project.output_path or not str(project.output_path).endswith(".mp4")):
            try:
                project.output_path = self.settings.resolve_output_path(project.folder, project.name)
            except Exception as e:
                log.warning(f"Could not resolve output path for {project.name}: {e}")

        # Ensure preset typography and subtitle style are synchronized
        from app.services.project_scanner import sync_project_preset_styling
        sync_project_preset_styling(project, self.settings)

        # Apply global subtitle settings so Settings changes take effect on every render,
        # but preserve project-level customizations (e.g. if project specifically enabled karaoke).
        if self.settings:
            from app.core.project import SubtitleMode
            sub_mode_raw = self.settings.get("sub_mode", "phrase")
            sub_enabled_global = self.settings.get("sub_enabled", True)

            # Preserve preset subtitle mode if already configured, otherwise respect global setting
            if project.profile.subtitle_mode == SubtitleMode.KARAOKE:
                project.profile.subtitle_enabled = True
            elif sub_mode_raw.lower() == "karaoke":
                project.profile.subtitle_mode = SubtitleMode.KARAOKE
                project.profile.subtitle_enabled = True
            elif not project.profile.subtitle_mode:
                try:
                    project.profile.subtitle_mode = SubtitleMode(sub_mode_raw)
                except ValueError:
                    pass
                if sub_enabled_global:
                    project.profile.subtitle_enabled = True

            # If project has an assigned preset or subtitles are globally enabled, ensure subtitle_enabled is True
            if sub_enabled_global or (project.preset_name and project.preset_name.lower() != "default"):
                project.profile.subtitle_enabled = True

            # Preserve preset karaoke highlight colour; only apply global default if unset
            if not getattr(project.profile, "subtitle_karaoke_color", None):
                kara_hex = self.settings.get("sub_karaoke_color", "#FFFF00")
                h = kara_hex.lstrip("#")
                if len(h) == 6:
                    r, g, b = h[0:2], h[2:4], h[4:6]
                    project.profile.subtitle_karaoke_color = f"&H00{b}{g}{r}".upper()
            
            # Avoid invisible highlight where karaoke color matches primary color (e.g. punk_zine)
            if getattr(project.profile, "subtitle_karaoke_color", "") == getattr(project.profile, "subtitle_primary_color", ""):
                # Use high-contrast alternate highlight
                pri = getattr(project.profile, "subtitle_primary_color", "")
                project.profile.subtitle_karaoke_color = "&H003300FF" if "FFFF" in pri else "&H0000FFFF"
            log.debug(
                f"[{project.name}] subtitle mode → {project.profile.subtitle_mode.value} "
                f"karaoke colour → {project.profile.subtitle_karaoke_color} "
                f"subtitle enabled → {project.profile.subtitle_enabled}"
            )

        if self.db:
            self.db.save_project(project)

        # Skip if output already exists and skip_completed is enabled
        if (self.settings
                and self.settings.get("skip_completed_projects", True)
                and project.output_path
                and project.output_path.exists()
                and project.output_path.stat().st_size > 1024):
            log.info(f"Skipping {project.name} — output already exists: {project.output_path.name}")
            project.status = ProjectStatus.COMPLETED
            if self.db:
                self.db.save_project(project)
            self.project_updated.emit(project.id)
            return False

        job = self.queue.add_project(project, priority=priority)
        return job is not None

    def queue_all_valid(self):
        """Queue all valid projects."""
        if not self.queue:
            return
        valid = self.get_projects_by_status(ProjectStatus.VALID)
        self.queue.add_projects_bulk(valid)

    # ─── Callbacks ────────────────────────────────────────────────────────────

    def _on_job_completed(self, job_id: str, output_path: str):
        # Update project state in our local dict
        job = self.queue.get_job(job_id) if self.queue else None
        if job:
            project = self._projects.get(job.project_id)
            if project:
                project.status = ProjectStatus.COMPLETED
                self.project_updated.emit(project.id)

    def _on_job_failed(self, job_id: str, error: str):
        job = self.queue.get_job(job_id) if self.queue else None
        if job:
            project = self._projects.get(job.project_id)
            if project:
                project.status = ProjectStatus.FAILED
                project.error_message = error
                self.project_updated.emit(project.id)

    def shutdown(self):
        """Graceful shutdown: cancel queue, wait for workers, save state."""
        log.info("AppState shutting down...")
        if self.queue:
            self.queue.pause()
            # Wait up to 8 s for any running render to reach a safe stopping point
            if hasattr(self.queue, "wait_for_all_workers"):
                self.queue.wait_for_all_workers(timeout_ms=8000)
        try:
            from app.subtitles.aligner import clear_model_cache
            clear_model_cache()
        except Exception as e:
            log.warning(f"Error clearing subtitle model cache: {e}")
        if self.db:
            self.db.close()
