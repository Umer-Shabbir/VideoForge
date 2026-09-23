"""
Logs panel: live log viewer with filtering by level/project, export, and clear.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QFileDialog, QCheckBox, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QTextCursor

from app.gui.theme import COLORS
from app.utils.logger import get_log_buffer, export_logs


LEVEL_COLORS = {
    "DEBUG":    COLORS["text_muted"],
    "INFO":     COLORS["text_primary"],
    "WARNING":  COLORS["warning"],
    "ERROR":    COLORS["error"],
    "CRITICAL": COLORS["error"],
}


class LogsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._filter_level = "ALL"
        self._filter_project = None
        self._setup_ui()

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._flush_pending)
        self._refresh_timer.start(500)
        self._pending_lines: list[dict] = []

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Application Logs")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")

        self._level_combo = QComboBox()
        self._level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self._level_combo.setCurrentText("INFO")
        self._level_combo.setFixedWidth(120)
        self._level_combo.currentTextChanged.connect(self._on_filter_changed)

        self._auto_scroll_cb = QCheckBox("Auto-scroll")
        self._auto_scroll_cb.setChecked(True)

        btn_pause = QPushButton("⏸ Pause")
        btn_pause.setFixedHeight(30)
        btn_pause.clicked.connect(self._toggle_pause)
        self._btn_pause = btn_pause

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(30)
        btn_clear.clicked.connect(self._clear)

        btn_export = QPushButton("Export...")
        btn_export.setFixedHeight(30)
        btn_export.clicked.connect(self._export)

        self._count_lbl = QLabel("0 lines")
        self._count_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")

        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(QLabel("Level:"))
        hdr.addWidget(self._level_combo)
        hdr.addWidget(self._auto_scroll_cb)
        hdr.addWidget(btn_pause)
        hdr.addWidget(btn_clear)
        hdr.addWidget(btn_export)
        hdr.addWidget(self._count_lbl)
        layout.addLayout(hdr)

        # Thin divider below header
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color:{COLORS['border']};max-height:1px;margin:0;")
        layout.addWidget(div)

        # Log text area
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(5000)
        self._log_view.setFont(QFont("Consolas, Courier New, monospace", 11))
        self._log_view.setStyleSheet(
            f"background: {COLORS['bg_primary']}; "
            f"color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px;"
        )
        layout.addWidget(self._log_view, 1)

        # Status bar
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        layout.addWidget(self._status_lbl)

    # ── Public API ────────────────────────────────────────────────────────────

    def append_log(self, entry: dict):
        """Receive a log entry dict from the logging callback."""
        if not self._paused:
            self._pending_lines.append(entry)

    def load_buffer(self):
        """Load existing log buffer on panel open."""
        self._log_view.clear()
        buffer = get_log_buffer()
        for entry in buffer:
            self._write_entry(entry)
        self._scroll_to_bottom()

    def set_project_filter(self, project_id: str = None):
        """Filter logs to a specific project (or None for all)."""
        self._filter_project = project_id

    # ── Internal ──────────────────────────────────────────────────────────────

    def _flush_pending(self):
        if not self._pending_lines:
            return
        lines = self._pending_lines[:]
        self._pending_lines.clear()
        min_level = self._level_combo.currentText()

        for entry in lines:
            if not self._passes_filter(entry, min_level):
                continue
            self._write_entry(entry)

        if self._auto_scroll_cb.isChecked():
            self._scroll_to_bottom()

        count = self._log_view.document().blockCount()
        self._count_lbl.setText(f"{count:,} lines")

    def _write_entry(self, entry: dict):
        level = entry.get("level", "INFO")
        ts    = entry.get("timestamp", "")
        msg   = entry.get("message", "")
        color = LEVEL_COLORS.get(level, COLORS["text_primary"])

        # Format line
        prefix = f"[{ts}] [{level:<8}] "
        line = prefix + msg

        # Append with color
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(line + "\n", fmt)

    def _passes_filter(self, entry: dict, min_level: str) -> bool:
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        entry_level = level_order.get(entry.get("level", "INFO"), 1)
        min_order   = level_order.get(min_level, 0) if min_level != "ALL" else 0
        if entry_level < min_order:
            return False
        if self._filter_project:
            if entry.get("project_id") != self._filter_project:
                return False
        return True

    def _scroll_to_bottom(self):
        sb = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_filter_changed(self):
        # Rebuild view from buffer
        self.load_buffer()

    def _toggle_pause(self):
        self._paused = not self._paused
        self._btn_pause.setText("▶ Resume" if self._paused else "⏸ Pause")
        if not self._paused:
            self.load_buffer()

    def _clear(self):
        self._log_view.clear()
        from app.utils.logger import clear_log_buffer
        clear_log_buffer()

    def _export(self):
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", "videoforge_logs.txt", "Text Files (*.txt)"
        )
        if path:
            ok = export_logs(Path(path))
            self._status_lbl.setText(
                f"✅ Logs exported to {path}" if ok else "❌ Export failed"
            )
