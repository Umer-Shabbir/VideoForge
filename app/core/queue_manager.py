"""
Queue manager: manages the render job queue.
Handles job scheduling, worker lifecycle, pause/resume, retries, and state persistence.
"""

import time
import logging
from pathlib import Path
from collections import OrderedDict
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal

from app.core.project import Project, ProjectStatus
from app.core.job import Job, JobState
from app.workers.render_worker import RenderWorker

log = logging.getLogger("videoforge.queue")


class QueueManager(QObject):
    """
    Manages the render queue and worker lifecycle.
    Runs on the main thread but spawns QThread workers for rendering.
    """

    # Signals
    queue_changed = Signal()
    job_added = Signal(str)         # job_id
    job_started = Signal(str)       # job_id
    job_progress = Signal(str, float, str)  # job_id, pct, message
    job_completed = Signal(str, str)        # job_id, output_path
    job_failed = Signal(str, str)           # job_id, error_message
    job_cancelled = Signal(str)             # job_id
    ffmpeg_log_line = Signal(str, str)      # job_id, line

    def __init__(
        self,
        max_concurrent: int = 1,
        db=None,
        settings=None,
        parent=None,
    ):
        super().__init__(parent)
        self.max_concurrent = max_concurrent
        self.db = db
        self.settings = settings
        self._paused = False
        self._jobs: OrderedDict[str, Job] = OrderedDict()       # job_id -> Job
        self._projects: dict[str, Project] = {}                  # project_id -> Project
        self._workers: dict[str, RenderWorker] = {}              # job_id -> worker
        self._watchdog_interval = 300  # seconds before considering a job stuck

    # ─── Queue Control ────────────────────────────────────────────────────────

    def add_project(
        self,
        project: Project,
        priority: int = 0,
        output_path: Optional[Path] = None,
    ) -> Optional[Job]:
        """Add a project to the queue. Returns the created Job."""
        if not project.validation.valid and not project.image_paths:
            log.warning(f"Refusing to queue invalid project: {project.name}")
            return None

        # Deduplicate: don't add same project twice if already pending
        for job in self._jobs.values():
            if job.project_id == project.id and job.state in (JobState.PENDING, JobState.RUNNING, JobState.PAUSED):
                log.info(f"Project '{project.name}' already in queue")
                return job

        job = Job(project_id=project.id, priority=priority)
        project.status = ProjectStatus.QUEUED
        project.updated_at = time.time()

        # Resolve output path
        if output_path:
            project.output_path = output_path
        elif not project.output_path:
            if self.settings:
                project.output_path = self.settings.resolve_output_path(
                    project.folder, project.name
                )
            else:
                project.output_path = project.folder / f"{project.name}_output.mp4"

        self._jobs[job.job_id] = job
        self._projects[project.id] = project

        if self.db:
            self.db.save_project(project)
            self.db.save_job(job)

        log.info(f"Queued job {job.job_id} for '{project.name}' (priority={priority})")
        self.job_added.emit(job.job_id)
        self.queue_changed.emit()

        # Try to start next job immediately
        if not self._paused:
            self._try_start_next()

        return job

    def add_projects_bulk(self, projects: list[Project], priority: int = 0):
        """Add multiple projects to the queue."""
        for project in projects:
            self.add_project(project, priority=priority)

    def remove_job(self, job_id: str):
        """Remove a pending job from the queue."""
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.state == JobState.RUNNING:
            self.cancel_job(job_id)
            return
        project = self._projects.get(job.project_id)
        if project:
            project.status = ProjectStatus.VALID
            if self.db:
                self.db.save_project(project)
        self._jobs.pop(job_id, None)
        if self.db:
            self.db.delete_job(job_id)
        self.queue_changed.emit()

    def cancel_job(self, job_id: str):
        """Cancel a running or pending job."""
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.state == JobState.RUNNING:
            worker = self._workers.get(job_id)
            if worker:
                worker.cancel()
                return  # Will handle in _on_job_cancelled
        job.state = JobState.CANCELLED
        project = self._projects.get(job.project_id)
        if project:
            project.status = ProjectStatus.CANCELLED
            if self.db:
                self.db.save_project(project)
        if self.db:
            self.db.save_job(job)
        self.job_cancelled.emit(job_id)
        self.queue_changed.emit()

    def retry_job(self, job_id: str):
        """Reset a failed job and re-queue it."""
        job = self._jobs.get(job_id)
        if not job or not job.can_retry():
            return
        job.reset_for_retry()
        project = self._projects.get(job.project_id)
        if project:
            project.status = ProjectStatus.QUEUED
            if self.db:
                self.db.save_project(project)
        if self.db:
            self.db.save_job(job)
        self.queue_changed.emit()
        if not self._paused:
            self._try_start_next()

    def pause(self):
        """Pause the queue (don't start new jobs)."""
        self._paused = True
        log.info("Queue paused")

    def resume(self):
        """Resume the queue."""
        self._paused = False
        log.info("Queue resumed")
        self._try_start_next()

    def cancel_all(self):
        """Cancel all pending and running jobs."""
        for job_id in list(self._jobs.keys()):
            job = self._jobs.get(job_id)
            if job and not job.is_terminal:
                self.cancel_job(job_id)

    def clear_completed(self):
        """Remove all completed/failed/cancelled jobs from the queue view."""
        to_remove = [
            jid for jid, j in self._jobs.items()
            if j.is_terminal
        ]
        for jid in to_remove:
            self._jobs.pop(jid, None)
            if self.db:
                self.db.delete_job(jid)
        self.queue_changed.emit()

    # ─── State & Queries ──────────────────────────────────────────────────────

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.state == JobState.RUNNING)

    @property
    def pending_count(self) -> int:
        return sum(1 for j in self._jobs.values()
                   if j.state in (JobState.PENDING, JobState.RETRYING))

    def get_all_jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def get_project_for_job(self, job_id: str) -> Optional[Project]:
        job = self._jobs.get(job_id)
        if job:
            return self._projects.get(job.project_id)
        return None

    def get_stats(self) -> dict:
        jobs = list(self._jobs.values())
        return {
            "total": len(jobs),
            "pending": sum(1 for j in jobs if j.state == JobState.PENDING),
            "running": sum(1 for j in jobs if j.state == JobState.RUNNING),
            "completed": sum(1 for j in jobs if j.state == JobState.COMPLETED),
            "failed": sum(1 for j in jobs if j.state == JobState.FAILED),
            "cancelled": sum(1 for j in jobs if j.state == JobState.CANCELLED),
            "paused": self._paused,
        }

    def estimate_remaining_time(self) -> Optional[float]:
        """Rough estimate of remaining queue time in seconds."""
        pending = [j for j in self._jobs.values()
                   if j.state in (JobState.PENDING, JobState.RETRYING)]
        if not pending:
            return 0.0

        # Use average of completed jobs
        completed = [j for j in self._jobs.values()
                     if j.state == JobState.COMPLETED and j.elapsed_time()]
        if not completed:
            return None

        avg_time = sum(j.elapsed_time() for j in completed) / len(completed)
        return avg_time * len(pending)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _try_start_next(self):
        """Start the next pending job if capacity allows."""
        if self._paused:
            return
        while self.active_count < self.max_concurrent:
            job = self._get_next_pending_job()
            if not job:
                break
            self._start_job(job)

    def _get_next_pending_job(self) -> Optional[Job]:
        """Get the highest-priority pending job."""
        pending = [
            j for j in self._jobs.values()
            if j.state in (JobState.PENDING, JobState.RETRYING)
        ]
        if not pending:
            return None
        return max(pending, key=lambda j: (j.priority, -j.queued_at))

    def _start_job(self, job: Job):
        """Start rendering a job."""
        # Guard: never start the same job twice
        if job.job_id in self._workers:
            log.warning(f"Job {job.job_id} already has a running worker — skipping duplicate start")
            return
        # Mark as running immediately so active_count is accurate before worker starts
        job.state = JobState.RUNNING

        project = self._projects.get(job.project_id)
        if not project:
            log.error(f"No project found for job {job.job_id}")
            job.state = JobState.FAILED
            job.error = "Project not found in memory"
            return

        ffmpeg_bin = ""
        ffmpeg_threads = 0   # 0 = FFmpeg auto-selects (uses all cores) — fastest
        overwrite = False
        if self.settings:
            ffmpeg_bin = self.settings.get("ffmpeg_path", "")
            # 0 = auto = FFmpeg uses all available CPU threads (fastest for single job)
            ffmpeg_threads = self.settings.get("ffmpeg_threads", 0)
            overwrite = self.settings.get("overwrite_existing", False)
            # Apply global subtitle style defaults to project profile if not yet customized
            _apply_subtitle_defaults(project, self.settings)

        worker = RenderWorker(
            job=job,
            project=project,
            output_path=project.output_path,
            ffmpeg_bin=ffmpeg_bin,
            ffmpeg_threads=ffmpeg_threads,
            overwrite=overwrite,
        )

        # Connect signals
        worker.signals.job_started.connect(self._on_job_started)
        worker.signals.job_progress.connect(self._on_job_progress)
        worker.signals.job_completed.connect(self._on_job_completed)
        worker.signals.job_failed.connect(self._on_job_failed)
        worker.signals.job_cancelled.connect(self._on_job_cancelled)
        worker.signals.ffmpeg_log.connect(self._on_ffmpeg_log)

        self._workers[job.job_id] = worker
        project.status = ProjectStatus.PROCESSING
        if self.db:
            self.db.save_project(project)

        worker.start()
        log.info(f"Started worker for job {job.job_id}")

    def _cleanup_worker(self, job_id: str):
        # Just drop the dict reference; the worker's finished->deleteLater()
        # handles C++ cleanup.  Calling quit()+wait() here on a thread that
        # hasn't finished yet causes the "Destroyed while running" warning.
        self._workers.pop(job_id, None)

    def wait_for_all_workers(self, timeout_ms: int = 10_000):
        """Block until every running worker finishes. Call during shutdown."""
        for job_id, worker in list(self._workers.items()):
            if worker.isRunning():
                import logging
                logging.getLogger("videoforge.queue").info(
                    f"Waiting for worker {job_id} to finish…"
                )
                worker.wait(timeout_ms)

    def _on_job_started(self, job_id: str):
        job = self._jobs.get(job_id)
        if job:
            job.state = JobState.RUNNING
            if self.db:
                self.db.save_job(job)
        self.job_started.emit(job_id)
        self.queue_changed.emit()

    def _on_job_progress(self, job_id: str, pct: float, msg: str):
        job = self._jobs.get(job_id)
        if job:
            job.progress = pct
        self.job_progress.emit(job_id, pct, msg)

    def _on_job_completed(self, job_id: str, output_path: str):
        self._cleanup_worker(job_id)
        job = self._jobs.get(job_id)
        project = self.get_project_for_job(job_id)

        if job:
            job.state = JobState.COMPLETED
            job.progress = 100.0
            job.finished_at = time.time()
            if self.db:
                self.db.save_job(job)

        if project:
            project.status = ProjectStatus.COMPLETED
            project.output_path = Path(output_path) if output_path else project.output_path
            if self.db:
                self.db.save_project(project)
                self.db.add_render_history(
                    project_id=project.id,
                    job_id=job_id,
                    output_path=output_path,
                    render_time=job.elapsed_time() if job else None,
                    output_size=project.metrics.output_size_bytes,
                    success=True,
                )

        self.job_completed.emit(job_id, output_path)
        self.queue_changed.emit()
        self._try_start_next()

    def _on_job_failed(self, job_id: str, error: str):
        self._cleanup_worker(job_id)
        job = self._jobs.get(job_id)
        project = self.get_project_for_job(job_id)

        if job:
            job.state = JobState.FAILED
            job.error = error
            job.finished_at = time.time()
            if self.db:
                self.db.save_job(job)

        if project:
            project.status = ProjectStatus.FAILED
            project.error_message = error
            if self.db:
                self.db.save_project(project)
                self.db.add_render_history(
                    project_id=project.id, job_id=job_id,
                    output_path=None, render_time=job.elapsed_time() if job else None,
                    output_size=0, success=False, error=error,
                )

        self.job_failed.emit(job_id, error)
        self.queue_changed.emit()

        # Auto-retry only for transient errors, not permanent ones like missing files
        _permanent_errors = ("not found", "no such file", "missing", "access is denied")
        is_permanent = any(kw in (error or "").lower() for kw in _permanent_errors)

        if job and job.can_retry() and not is_permanent:
            log.info(f"Auto-retrying job {job_id} (attempt {job.retry_count + 1})")
            self.retry_job(job_id)
        else:
            if is_permanent:
                log.warning(f"Job {job_id} failed with permanent error, not retrying: {error[:80]}")
                # Exhaust retries so it shows as permanently failed
                if job:
                    job.retry_count = job.max_retries
            self._try_start_next()

    def _on_job_cancelled(self, job_id: str):
        self._cleanup_worker(job_id)
        job = self._jobs.get(job_id)
        project = self.get_project_for_job(job_id)

        if job:
            job.state = JobState.CANCELLED
            job.finished_at = time.time()
            if self.db:
                self.db.save_job(job)

        if project:
            project.status = ProjectStatus.CANCELLED
            if self.db:
                self.db.save_project(project)

        self.job_cancelled.emit(job_id)
        self.queue_changed.emit()
        self._try_start_next()

    def _on_ffmpeg_log(self, job_id: str, line: str):
        self.ffmpeg_log_line.emit(job_id, line)

    def restore_from_db(self, projects: list[Project]):
        """Restore queue state from database on startup."""
        for project in projects:
            self._projects[project.id] = project

        if not self.db:
            return

        pending_jobs = self.db.load_pending_jobs()
        for job in pending_jobs:
            if job.project_id in self._projects:
                self._jobs[job.job_id] = job
                log.info(f"Restored pending job {job.job_id}")

        if not self._paused and self._jobs:
            self._try_start_next()

        log.info(f"Queue restored: {len(self._jobs)} jobs")


def _apply_subtitle_defaults(project, settings) -> None:
    """
    Copy global subtitle style settings to a project profile
    so that global changes in Settings take effect on all queued renders.
    Only applied if the project is using the default font (not user-customized).
    """
    try:
        pr = project.profile
        # Only override if font matches default "Arial" (not user-customized)
        if pr.subtitle_font == "Arial" or not pr.subtitle_font:
            pr.subtitle_font = settings.get("sub_font", "Arial")
        pr.subtitle_font_size    = settings.get("sub_font_size", pr.subtitle_font_size)
        pr.subtitle_bold         = settings.get("sub_bold", pr.subtitle_bold)
        pr.subtitle_outline_width= settings.get("sub_outline_width", pr.subtitle_outline_width)
        pr.subtitle_shadow       = settings.get("sub_shadow", pr.subtitle_shadow)
        pr.subtitle_margin_v     = settings.get("sub_margin_v", pr.subtitle_margin_v)
        pr.subtitle_max_chars    = settings.get("sub_max_chars", pr.subtitle_max_chars)

        # Convert hex colors to ASS format if provided in settings
        def hex_to_ass(h: str, default: str) -> str:
            if not h or not h.startswith("#") or len(h) != 7:
                return default
            b, g, r = h[5:7], h[3:5], h[1:3]
            return f"&H00{b}{g}{r}".upper()

        pr.subtitle_primary_color = hex_to_ass(
            settings.get("sub_primary_color", ""), pr.subtitle_primary_color
        )
        pr.subtitle_outline_color = hex_to_ass(
            settings.get("sub_outline_color", ""), pr.subtitle_outline_color
        )
        pr.subtitle_karaoke_color = hex_to_ass(
            settings.get("sub_karaoke_color", "#FFFF00"),
            pr.subtitle_karaoke_color
        )

        from app.core.project import SubtitleMode
        mode_str = settings.get("sub_mode", "")
        if mode_str:
            try:
                pr.subtitle_mode = SubtitleMode(mode_str)
            except ValueError:
                pass
    except Exception:
        pass  # never fail a render because of subtitle style settings
