"""
Dashboard panel: shows overview stats, quick-action buttons, and recent activity.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from app.gui.widgets.common import StatCard, SectionHeader, Divider, TagLabel
from app.gui.theme import COLORS


class DashboardPanel(QWidget):
    add_folders_clicked = Signal()
    queue_all_clicked = Signal()
    open_settings_clicked = Signal()
    view_logs_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(3000)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)

        # Header
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("title")
        subtitle = QLabel("VideoForge — Bulk Video Generator")
        subtitle.setObjectName("subtitle")
        header.addWidget(title)
        header.addStretch()

        outer.addLayout(header)
        outer.addWidget(subtitle)

        # FFmpeg status
        self._ffmpeg_card = QFrame()
        self._ffmpeg_card.setObjectName("card")
        fcard_layout = QHBoxLayout(self._ffmpeg_card)
        fcard_layout.setContentsMargins(16, 10, 16, 10)
        self._ffmpeg_icon = QLabel("⚙")
        self._ffmpeg_icon.setStyleSheet("font-size: 20px;")
        self._ffmpeg_status_lbl = QLabel("Checking FFmpeg...")
        self._ffmpeg_status_lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        fcard_layout.addWidget(self._ffmpeg_icon)
        fcard_layout.addWidget(self._ffmpeg_status_lbl, 1)
        outer.addWidget(self._ffmpeg_card)

        # Stat cards — two rows of 4, using HBox rows so they never overflow
        outer.addWidget(SectionHeader("Overview"))

        self._card_total    = StatCard("Projects",    "0", COLORS["text_primary"])
        self._card_valid    = StatCard("Valid",        "0", COLORS["status_valid"])
        self._card_invalid  = StatCard("Issues",       "0", COLORS["status_invalid"])
        self._card_queued   = StatCard("Queued",       "0", COLORS["status_queued"])
        self._card_running  = StatCard("Processing",   "0", COLORS["status_processing"])
        self._card_done     = StatCard("Completed",    "0", COLORS["status_completed"])
        self._card_failed   = StatCard("Failed",       "0", COLORS["status_failed"])
        self._card_duration = StatCard("Total Audio",  "0s", COLORS["accent_text"])

        row1 = QHBoxLayout(); row1.setSpacing(12)
        for card in [self._card_total, self._card_valid, self._card_invalid, self._card_queued]:
            row1.addWidget(card, 1)

        row2 = QHBoxLayout(); row2.setSpacing(12)
        for card in [self._card_running, self._card_done, self._card_failed, self._card_duration]:
            row2.addWidget(card, 1)

        outer.addLayout(row1)
        outer.addLayout(row2)

        # Queue section
        outer.addWidget(SectionHeader("Queue Status"))
        queue_frame = QFrame()
        queue_frame.setObjectName("panel")
        queue_layout = QVBoxLayout(queue_frame)
        queue_layout.setContentsMargins(16, 14, 16, 14)
        queue_layout.setSpacing(8)

        row1 = QHBoxLayout()
        self._queue_status_lbl = QLabel("Queue idle")
        self._queue_status_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        self._estimated_time_lbl = QLabel("")
        self._estimated_time_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        row1.addWidget(self._queue_status_lbl)
        row1.addStretch()
        row1.addWidget(self._estimated_time_lbl)
        queue_layout.addLayout(row1)

        self._active_job_lbl = QLabel("")
        self._active_job_lbl.setStyleSheet(f"color: {COLORS['accent_text']};")
        self._active_job_lbl.setVisible(False)
        queue_layout.addWidget(self._active_job_lbl)

        outer.addWidget(queue_frame)

        # Quick actions
        outer.addWidget(SectionHeader("Quick Actions"))
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        btn_add = QPushButton("  ＋  Add Folders")
        btn_add.setObjectName("primary")
        btn_add.setFixedHeight(40)
        btn_add.clicked.connect(self.add_folders_clicked)

        btn_queue = QPushButton("  ▶  Queue All Valid")
        btn_queue.setFixedHeight(40)
        btn_queue.clicked.connect(self.queue_all_clicked)
        self._btn_queue = btn_queue

        btn_settings = QPushButton("  ⚙  Settings")
        btn_settings.setFixedHeight(40)
        btn_settings.clicked.connect(self.open_settings_clicked)

        btn_logs = QPushButton("  📋  View Logs")
        btn_logs.setFixedHeight(40)
        btn_logs.clicked.connect(self.view_logs_clicked)

        actions_row.addWidget(btn_add)
        actions_row.addWidget(btn_queue)
        actions_row.addWidget(btn_settings)
        actions_row.addWidget(btn_logs)
        actions_row.addStretch()
        outer.addLayout(actions_row)

        # Tips
        outer.addWidget(SectionHeader("Tips"))
        tips_frame = QFrame()
        tips_frame.setObjectName("panel")
        tips_layout = QVBoxLayout(tips_frame)
        tips_layout.setContentsMargins(16, 12, 16, 12)
        tips = [
            "📁  Each project folder needs: 1 audio file + at least 1 image + optional transcript",
            "⚡  Use 'Queue All Valid' to process everything at once — errors are isolated per project",
            "🎨  Apply a preset in Settings for consistent output across all projects",
            "💾  Projects and queue state are saved automatically between sessions",
        ]
        for tip in tips:
            lbl = QLabel(tip)
            lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
            lbl.setWordWrap(True)
            tips_layout.addWidget(lbl)
        outer.addWidget(tips_frame)

        outer.addStretch()

    def update_stats(self, stats: dict):
        self._card_total.set_value(str(stats.get("total_projects", 0)))
        self._card_valid.set_value(str(stats.get("valid", 0)))
        self._card_invalid.set_value(str(stats.get("invalid", 0)))
        self._card_queued.set_value(str(stats.get("queued", 0)))
        self._card_running.set_value(str(stats.get("processing", 0)))
        self._card_done.set_value(str(stats.get("completed", 0)))
        self._card_failed.set_value(str(stats.get("failed", 0)))

        dur = stats.get("total_audio_duration", 0)
        if dur >= 3600:
            dur_str = f"{dur/3600:.1f}h"
        elif dur >= 60:
            dur_str = f"{dur/60:.1f}m"
        else:
            dur_str = f"{int(dur)}s"
        self._card_duration.set_value(dur_str)

        # Queue status
        running = stats.get("running", 0)
        pending = stats.get("pending", 0)
        if running:
            self._queue_status_lbl.setText(f"Processing {running} job{'s' if running > 1 else ''}...")
            self._queue_status_lbl.setStyleSheet(
                f"color: {COLORS['status_processing']}; font-size: 14px; font-weight: 600;"
            )
        elif pending:
            paused = stats.get("paused", False)
            self._queue_status_lbl.setText(
                f"{'Paused — ' if paused else ''}{pending} job{'s' if pending > 1 else ''} waiting"
            )
            self._queue_status_lbl.setStyleSheet(
                f"color: {COLORS['status_queued']}; font-size: 14px;"
            )
        else:
            self._queue_status_lbl.setText("Queue idle")
            self._queue_status_lbl.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 14px;"
            )

    def update_ffmpeg_status(self, ok: bool, message: str):
        if ok:
            self._ffmpeg_icon.setText("✅")
            self._ffmpeg_status_lbl.setText(f"FFmpeg ready — {message}")
            self._ffmpeg_status_lbl.setStyleSheet(f"color: {COLORS['success']};")
            self._ffmpeg_card.setStyleSheet(
                f"QFrame#card {{ border-color: {COLORS['success']}; }}"
            )
        else:
            self._ffmpeg_icon.setText("⚠️")
            self._ffmpeg_status_lbl.setText(f"FFmpeg not found — {message}")
            self._ffmpeg_status_lbl.setStyleSheet(f"color: {COLORS['warning']};")
            self._ffmpeg_card.setStyleSheet(
                f"QFrame#card {{ border-color: {COLORS['warning']}; }}"
            )

    def set_estimated_time(self, seconds: float = None):
        if seconds is None:
            self._estimated_time_lbl.setText("")
        elif seconds < 60:
            self._estimated_time_lbl.setText(f"~{int(seconds)}s remaining")
        else:
            self._estimated_time_lbl.setText(f"~{seconds/60:.1f}m remaining")

    def _auto_refresh(self):
        """Emit a refresh request — parent connects this."""
        pass
