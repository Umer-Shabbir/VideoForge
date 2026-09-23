"""
Queue panel: shows all jobs, live progress, and queue controls.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, Signal

from app.core.job import Job, JobState
from app.core.project import Project
from app.gui.widgets.common import StatusBadge, SectionHeader
from app.gui.theme import COLORS


class QueuePanel(QWidget):
    pause_clicked = Signal()
    resume_clicked = Signal()
    cancel_all_clicked = Signal()
    clear_completed_clicked = Signal()
    cancel_job = Signal(str)     # job_id
    retry_job = Signal(str)      # job_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job_rows: dict[str, "JobRow"] = {}
        self._paused = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header + controls
        hdr = QHBoxLayout()
        title = QLabel("Render Queue")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")

        self._btn_pause = QPushButton("⏸  Pause")
        self._btn_pause.setFixedHeight(32)
        self._btn_pause.clicked.connect(self._toggle_pause)

        btn_cancel_all = QPushButton("✕  Cancel All")
        btn_cancel_all.setObjectName("danger")
        btn_cancel_all.setFixedHeight(32)
        btn_cancel_all.clicked.connect(self.cancel_all_clicked)

        btn_clear = QPushButton("🗑  Clear Done")
        btn_clear.setFixedHeight(32)
        btn_clear.clicked.connect(self.clear_completed_clicked)

        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self._btn_pause)
        hdr.addWidget(btn_cancel_all)
        hdr.addWidget(btn_clear)
        layout.addLayout(hdr)

        # Thin divider below header
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color:{COLORS['border']};max-height:1px;margin:0;")
        layout.addWidget(div)

        # Stats bar
        self._stats_lbl = QLabel("No jobs in queue")
        self._stats_lbl.setStyleSheet(
            f"color:{COLORS['text_secondary']};font-size:12px;"
            f"padding:4px 2px;"
        )
        layout.addWidget(self._stats_lbl)

        # Overall progress
        self._overall_progress = QProgressBar()
        self._overall_progress.setRange(0, 100)
        self._overall_progress.setValue(0)
        self._overall_progress.setTextVisible(True)
        self._overall_progress.setFormat("Queue Progress: %p%")
        self._overall_progress.setFixedHeight(18)
        self._overall_progress.setVisible(False)
        layout.addWidget(self._overall_progress)

        # Job list scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._jobs_container = QWidget()
        self._jobs_layout = QVBoxLayout(self._jobs_container)
        self._jobs_layout.setContentsMargins(0, 0, 0, 0)
        self._jobs_layout.setSpacing(4)
        self._jobs_layout.addStretch()

        scroll.setWidget(self._jobs_container)
        layout.addWidget(scroll, 1)

        # Empty state
        self._empty_lbl = QLabel("No jobs queued yet.\nAdd projects and click 'Queue for Rendering'.")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 14px; padding: 40px;"
        )
        layout.addWidget(self._empty_lbl)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_job(self, job: Job, project_name: str):
        if job.job_id in self._job_rows:
            return
        row = JobRow(job.job_id, project_name)
        row.cancel_clicked.connect(self.cancel_job)
        row.retry_clicked.connect(self.retry_job)
        self._job_rows[job.job_id] = row
        # Insert before the stretch
        idx = self._jobs_layout.count() - 1
        self._jobs_layout.insertWidget(idx, row)
        self._update_empty_state()

    def update_job_progress(self, job_id: str, pct: float, msg: str = ""):
        row = self._job_rows.get(job_id)
        if row:
            row.update_progress(pct, msg)

    def update_job_status(self, job_id: str, status: str):
        row = self._job_rows.get(job_id)
        if row:
            row.set_status(status)

    def remove_job(self, job_id: str):
        row = self._job_rows.pop(job_id, None)
        if row:
            self._jobs_layout.removeWidget(row)
            row.deleteLater()
        self._update_empty_state()

    def refresh_from_jobs(self, jobs: list, projects: dict):
        """Full refresh from a list of Job objects."""
        # Add any new jobs
        existing_ids = set(self._job_rows.keys())
        for job in jobs:
            name = projects.get(job.project_id, {})
            pname = name.name if hasattr(name, "name") else str(job.project_id)[:8]
            if job.job_id not in existing_ids:
                self.add_job(job, pname)
            # Update status and progress
            self.update_job_status(job.job_id, job.state.value)
            self.update_job_progress(job.job_id, job.progress)

        # Stats
        total = len(jobs)
        running = sum(1 for j in jobs if j.state == JobState.RUNNING)
        pending = sum(1 for j in jobs if j.state == JobState.PENDING)
        done = sum(1 for j in jobs if j.state == JobState.COMPLETED)
        failed = sum(1 for j in jobs if j.state == JobState.FAILED)

        parts = []
        if running: parts.append(f"{running} running")
        if pending: parts.append(f"{pending} pending")
        if done:    parts.append(f"{done} done")
        if failed:  parts.append(f"{failed} failed")
        self._stats_lbl.setText("  |  ".join(parts) if parts else "Queue empty")

        # Overall progress
        if total > 0:
            pct = (done / total) * 100
            self._overall_progress.setValue(int(pct))
            self._overall_progress.setVisible(True)
        else:
            self._overall_progress.setVisible(False)

    def set_paused(self, paused: bool):
        self._paused = paused
        self._btn_pause.setText("▶  Resume" if paused else "⏸  Pause")

    def _toggle_pause(self):
        if self._paused:
            self.resume_clicked.emit()
        else:
            self.pause_clicked.emit()

    def _update_empty_state(self):
        has_jobs = len(self._job_rows) > 0
        self._empty_lbl.setVisible(not has_jobs)


class JobRow(QFrame):
    """A single job row in the queue panel."""
    cancel_clicked = Signal(str)
    retry_clicked = Signal(str)

    def __init__(self, job_id: str, project_name: str, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.setObjectName("panel")
        self.setFixedHeight(68)
        self._setup_ui(project_name)

    def _setup_ui(self, project_name: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Top row: name + status + buttons
        top = QHBoxLayout()
        top.setSpacing(8)

        self._name = QLabel(project_name)
        font = self._name.font()
        font.setPointSize(12)
        font.setBold(True)
        self._name.setFont(font)
        self._name.setToolTip(project_name)

        self._status = StatusBadge("queued")
        self._status.setFixedWidth(90)

        self._msg_lbl = QLabel("")
        self._msg_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        self._msg_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setObjectName("icon_btn")
        self._cancel_btn.setFixedSize(22, 22)
        self._cancel_btn.setToolTip("Cancel")
        self._cancel_btn.clicked.connect(lambda: self.cancel_clicked.emit(self.job_id))

        self._retry_btn = QPushButton("↻")
        self._retry_btn.setObjectName("icon_btn")
        self._retry_btn.setFixedSize(22, 22)
        self._retry_btn.setToolTip("Retry")
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(lambda: self.retry_clicked.emit(self.job_id))

        top.addWidget(self._name)
        top.addWidget(self._status)
        top.addWidget(self._msg_lbl, 1)
        top.addWidget(self._retry_btn)
        top.addWidget(self._cancel_btn)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(5)

        layout.addLayout(top)
        layout.addWidget(self._progress)

    def update_progress(self, pct: float, msg: str = ""):
        self._progress.setValue(int(pct))
        if msg:
            short = msg[:80] + "…" if len(msg) > 80 else msg
            self._msg_lbl.setText(short)

    def set_status(self, status: str):
        self._status.set_status(status)
        if status == "completed":
            self._progress.setValue(100)
            self._progress.setStyleSheet(
                f"QProgressBar::chunk {{ background: {COLORS['success']}; }}"
            )
            self._cancel_btn.setVisible(False)
        elif status == "failed":
            self._cancel_btn.setVisible(False)
            self._retry_btn.setVisible(True)
            self._progress.setStyleSheet(
                f"QProgressBar::chunk {{ background: {COLORS['error']}; }}"
            )
        elif status in ("cancelled", ):
            self._cancel_btn.setVisible(False)
        elif status == "running":
            self._cancel_btn.setVisible(True)
            self._retry_btn.setVisible(False)
