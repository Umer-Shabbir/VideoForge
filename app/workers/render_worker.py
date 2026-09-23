"""
Render worker: QThread-based worker for rendering a single project.

Fix applied: workers are kept alive with setParent(QApplication.instance())
so Python's GC does not destroy them while still running.
The QThread 'finished' signal triggers deleteLater() for clean cleanup.
"""

import threading
import time
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtWidgets import QApplication

from app.core.project import Project, ProjectStatus
from app.core.job import Job, JobState
from app.render.renderer import render_project, RenderResult

log = logging.getLogger("videoforge.render_worker")


class RenderSignals(QObject):
    """Signals emitted by the render worker."""
    job_started   = Signal(str)           # job_id
    job_progress  = Signal(str, float, str)  # job_id, pct, message
    job_completed = Signal(str, str)      # job_id, output_path
    job_failed    = Signal(str, str)      # job_id, error_message
    job_cancelled = Signal(str)           # job_id
    ffmpeg_log    = Signal(str, str)      # job_id, log_line


class RenderWorker(QThread):
    """
    Background thread that renders a single project.
    One RenderWorker is created per active job.

    Ownership: QueueManager holds a strong reference in self._workers.
    The worker also parents itself to QApplication so it is never prematurely
    garbage-collected by Python while the OS thread is still running.
    """

    def __init__(
        self,
        job: Job,
        project: Project,
        output_path: Path,
        ffmpeg_bin: str = "",
        ffmpeg_threads: int = 0,
        overwrite: bool = False,
        parent=None,
    ):
        # Parent to QApplication so the C++ object outlives local Python refs
        app = QApplication.instance()
        super().__init__(app if parent is None else parent)
        self.job           = job
        self.project       = project
        self.output_path   = Path(output_path) if output_path else None
        self.ffmpeg_bin    = ffmpeg_bin
        self.ffmpeg_threads = ffmpeg_threads
        self.overwrite     = overwrite
        self.signals       = RenderSignals()
        self._cancel_flag  = threading.Event()

        # Auto-cleanup: once the thread finishes, schedule deleteLater
        self.finished.connect(self.deleteLater)

    def run(self):
        """Main thread entry — runs the full render pipeline."""
        job = self.job
        job.state      = JobState.RUNNING
        job.started_at = time.time()

        self.signals.job_started.emit(job.job_id)
        log.info(f"Starting render job {job.job_id} for '{self.project.name}'")

        def progress_cb(pct: float, msg: str = ""):
            job.progress = pct
            self.signals.job_progress.emit(job.job_id, pct, msg)

        def log_cb(line: str):
            job.log_lines.append(line)
            self.signals.ffmpeg_log.emit(job.job_id, line)

        try:
            result: RenderResult = render_project(
                project          = self.project,
                output_path      = self.output_path,
                progress_callback= progress_cb,
                log_callback     = log_cb,
                cancel_flag      = self._cancel_flag,
                ffmpeg_bin       = self.ffmpeg_bin or None,
                ffmpeg_threads   = self.ffmpeg_threads,
                overwrite        = self.overwrite,
            )

            job.finished_at = time.time()

            if self._cancel_flag.is_set():
                job.state = JobState.CANCELLED
                self.signals.job_cancelled.emit(job.job_id)
                log.info(f"Job {job.job_id} cancelled")
            elif result.success:
                job.state    = JobState.COMPLETED
                job.progress = 100.0
                if result.metrics:
                    self.project.metrics = result.metrics
                self.signals.job_completed.emit(
                    job.job_id,
                    str(result.output_path) if result.output_path else "",
                )
                log.info(f"Job {job.job_id} completed")
            else:
                job.state = JobState.FAILED
                job.error = result.error
                self.signals.job_failed.emit(job.job_id, result.error)
                log.error(f"Job {job.job_id} failed: {result.error}")

        except Exception as e:
            import traceback
            job.finished_at = time.time()
            job.state = JobState.FAILED
            job.error = str(e)
            self.signals.job_failed.emit(job.job_id, str(e))
            log.error(f"Job {job.job_id} crashed: {e}\n{traceback.format_exc()}")

    def cancel(self):
        log.info(f"Cancelling job {self.job.job_id}")
        self._cancel_flag.set()


class ScanWorker(QThread):
    """Background thread for scanning folders for projects."""

    scan_progress = Signal(float, str)  # pct, message
    project_found = Signal(object)       # Project
    scan_complete = Signal(int)          # total found
    scan_error    = Signal(str)          # error message

    def __init__(
        self,
        folders: list,
        recursive: bool = True,
        max_depth: int  = 5,
        force_direct: bool = False,
        default_profile = None,
        parent = None,
    ):
        app = QApplication.instance()
        super().__init__(app if parent is None else parent)
        self.folders         = [Path(f) for f in folders]
        self.recursive       = recursive
        self.max_depth       = max_depth
        self.force_direct    = force_direct
        self.default_profile = default_profile
        self._cancel_flag    = threading.Event()
        self.finished.connect(self.deleteLater)

    def run(self):
        from app.services.project_scanner import ProjectScanner
        from app.core.project import RenderProfile
        from app.core.app_state import AppState

        app_state = AppState.instance()
        settings_mgr = getattr(app_state, "settings", None)

        scanner = ProjectScanner(
            recursive       = self.recursive,
            max_depth       = self.max_depth,
            auto_validate   = True,
            default_profile = self.default_profile or RenderProfile(),
            settings_manager= settings_mgr,
        )

        all_projects  = []
        total_folders = len(self.folders)

        for idx, folder in enumerate(self.folders):
            if self._cancel_flag.is_set():
                break

            base_pct = (idx / max(total_folders, 1)) * 100

            def _progress(pct, msg, _b=base_pct, _t=total_folders):
                self.scan_progress.emit(_b + pct / max(_t, 1), msg)

            try:
                if self.force_direct:
                    # Treat this folder as a standalone project — no recursive search
                    project = scanner.scan_single_folder(folder)
                    if project:
                        all_projects.append(project)
                        self.project_found.emit(project)
                    _progress(100.0, f"Loaded {folder.name}")
                else:
                    projects = scanner.scan_folder(
                        folder,
                        progress_callback = _progress,
                        cancel_flag       = self._cancel_flag,
                    )
                    for proj in projects:
                        all_projects.append(proj)
                        self.project_found.emit(proj)
            except Exception as e:
                self.scan_error.emit(f"Error scanning {folder}: {e}")
                log.error(f"Scan error for {folder}: {e}")

        self.scan_complete.emit(len(all_projects))

    def cancel(self):
        self._cancel_flag.set()
