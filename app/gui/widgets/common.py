"""
Reusable GUI widgets used across multiple panels.
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame,
    QPushButton, QProgressBar, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPainterPath
from app.gui.theme import COLORS, STATUS_COLORS, status_badge_style


class StatCard(QFrame):
    """A metric card showing a large number + label."""
    def __init__(self, label: str, value: str = "0", color: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumSize(120, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName("metric_value")
        if color:
            self._value_lbl.setStyleSheet(
                f"font-size: 28px; font-weight: 700; color: {color};"
            )

        self._label_lbl = QLabel(label.upper())
        self._label_lbl.setObjectName("metric_label")

        layout.addWidget(self._value_lbl)
        layout.addWidget(self._label_lbl)
        layout.addStretch()

    def set_value(self, value: str):
        self._value_lbl.setText(value)

    def set_color(self, color: str):
        self._value_lbl.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {color};"
        )


class StatusBadge(QLabel):
    """A colored badge label for project/job status."""
    def __init__(self, status: str = "unknown", parent=None):
        super().__init__(parent)
        self.set_status(status)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_status(self, status: str):
        text = status.capitalize()
        self.setText(text)
        self.setStyleSheet(status_badge_style(status))


class SectionHeader(QLabel):
    """A styled section header label."""
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("section_header")


class Divider(QFrame):
    """A horizontal divider line."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet(f"color: {COLORS['border']}; max-height: 1px;")


class JobProgressRow(QWidget):
    """
    A single row in the queue panel showing job name, status, and progress bar.
    """
    cancel_clicked = Signal(str)   # job_id
    retry_clicked = Signal(str)    # job_id

    def __init__(self, job_id: str, project_name: str, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self._setup_ui(project_name)

    def _setup_ui(self, project_name: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Project name
        self._name_lbl = QLabel(project_name)
        self._name_lbl.setMinimumWidth(160)
        self._name_lbl.setMaximumWidth(220)
        self._name_lbl.setToolTip(project_name)
        font = self._name_lbl.font()
        font.setPointSize(12)
        self._name_lbl.setFont(font)

        # Status badge
        self._status = StatusBadge("queued")
        self._status.setFixedWidth(90)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)

        # Message label
        self._msg_lbl = QLabel("")
        self._msg_lbl.setObjectName("subtitle")
        self._msg_lbl.setMinimumWidth(100)
        self._msg_lbl.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )

        # Cancel button
        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setObjectName("icon_btn")
        self._cancel_btn.setFixedSize(24, 24)
        self._cancel_btn.setToolTip("Cancel job")
        self._cancel_btn.clicked.connect(lambda: self.cancel_clicked.emit(self.job_id))

        # Retry button (hidden by default)
        self._retry_btn = QPushButton("↻")
        self._retry_btn.setObjectName("icon_btn")
        self._retry_btn.setFixedSize(24, 24)
        self._retry_btn.setToolTip("Retry job")
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(lambda: self.retry_clicked.emit(self.job_id))

        layout.addWidget(self._name_lbl)
        layout.addWidget(self._status)
        layout.addWidget(self._progress, 1)
        layout.addWidget(self._msg_lbl)
        layout.addWidget(self._retry_btn)
        layout.addWidget(self._cancel_btn)

    def update_progress(self, pct: float, msg: str = ""):
        self._progress.setValue(int(pct))
        if msg:
            short = msg[:60] + "…" if len(msg) > 60 else msg
            self._msg_lbl.setText(short)

    def set_status(self, status: str):
        self._status.set_status(status)
        # Style progress bar based on status
        if status == "completed":
            self._progress.setObjectName("success_bar")
            self._progress.setValue(100)
            self._progress.style().unpolish(self._progress)
            self._progress.style().polish(self._progress)
            self._cancel_btn.setVisible(False)
        elif status == "failed":
            self._cancel_btn.setVisible(False)
            self._retry_btn.setVisible(True)
        elif status in ("cancelled", "completed"):
            self._cancel_btn.setVisible(False)
        elif status == "running":
            self._cancel_btn.setVisible(True)
            self._retry_btn.setVisible(False)


class HealthBar(QWidget):
    """Visual health score bar (0–100)."""
    def __init__(self, score: int = 100, parent=None):
        super().__init__(parent)
        self.score = score
        self.setFixedSize(60, 10)

    def set_score(self, score: int):
        self.score = max(0, min(100, score))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = h // 2

        # Background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(bg_path, QColor(COLORS["border"]))

        # Fill
        if self.score > 0:
            fill_w = int(w * self.score / 100)
            fill_path = QPainterPath()
            fill_path.addRoundedRect(0, 0, fill_w, h, r, r)
            if self.score >= 80:
                color = QColor(COLORS["success"])
            elif self.score >= 50:
                color = QColor(COLORS["warning"])
            else:
                color = QColor(COLORS["error"])
            painter.fillPath(fill_path, color)


class EmptyStateWidget(QWidget):
    """Shown when a list/panel has no content."""
    def __init__(self, title: str, subtitle: str = "", action_text: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        icon = QLabel("📂")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {COLORS['text_secondary']};"
        )

        layout.addWidget(icon)
        layout.addWidget(title_lbl)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setAlignment(Qt.AlignCenter)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
            layout.addWidget(sub)

        if action_text:
            self.action_btn = QPushButton(action_text)
            self.action_btn.setObjectName("primary")
            self.action_btn.setFixedWidth(160)
            layout.addWidget(self.action_btn, alignment=Qt.AlignCenter)


class TagLabel(QLabel):
    """A small colored tag/chip label."""
    def __init__(self, text: str, color: str = None, parent=None):
        super().__init__(text, parent)
        c = color or COLORS["accent"]
        dark = self._darken(c)
        self.setStyleSheet(
            f"color: {c}; background: {dark}; border-radius: 3px; "
            f"padding: 1px 6px; font-size: 11px; font-weight: 600;"
        )

    def _darken(self, hex_c: str) -> str:
        h = hex_c.lstrip("#")
        if len(h) != 6:
            return "#1a1a2e"
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{int(r*0.15):02x}{int(g*0.15):02x}{int(b*0.15):02x}"
