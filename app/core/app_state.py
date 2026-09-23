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

        self._initialized = True
        log.info("AppState initialized successfully")

    def _load_persisted_projects(self):
        """Load project list from database, re-checking file existence."""
        if not self.db:
            return
        try:
            projects = self.db.load_all_projects()
            for p in projects:
                # Reset stuck processing state
                if p.status == ProjectStatus.PROCESSING:
                    p.status = ProjectStatus.FAILED
                    p.error_message = "Interrupted by application restart"

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
        """Add a project to the state. Returns False if duplicate folder."""
        # Check for duplicate folders
        for existing in self._projects.values():
            if existing.folder == project.folder:
                log.info(f"Duplicate folder ignored: {project.folder}")
                return False
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

        # Apply global subtitle settings so Settings changes take effect on every render.
        # The project profile stored in DB reflects the state at import time (phrase mode by
        # default). Users expect Settings → Subtitles to be the authoritative global override.
        if self.settings:
            from app.core.project import SubtitleMode
            sub_mode_raw = self.settings.get("sub_mode", "phrase")
            try:
                project.profile.subtitle_mode = SubtitleMode(sub_mode_raw)
            except ValueError:
                pass
            # Apply karaoke highlight colour (#RRGGBB → ASS &H00BBGGRR)
            kara_hex = self.settings.get("sub_karaoke_color", "#FFFF00")
            h = kara_hex.lstrip("#")
            if len(h) == 6:
                r, g, b = h[0:2], h[2:4], h[4:6]
                project.profile.subtitle_karaoke_color = f"&H00{b}{g}{r}".upper()
            log.debug(
                f"[{project.name}] subtitle mode → {project.profile.subtitle_mode.value} "
                f"karaoke colour → {project.profile.subtitle_karaoke_color}"
            )

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
        if self.db:
            self.db.close()
