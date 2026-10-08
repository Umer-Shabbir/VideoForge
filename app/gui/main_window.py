"""
VideoForge Main Window — sidebar layout, fixed-size elements, no crowding.
"""

import os
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QFileDialog, QStatusBar, QMessageBox,
    QProgressBar, QApplication, QFrame, QSizePolicy, QSpacerItem,
    QScrollArea, QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
    QAbstractItemView, QToolButton, QMenu
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QFont, QColor

from app.core.app_state import AppState
from app.core.project import Project, ProjectStatus
from app.gui.widgets.dashboard    import DashboardPanel
from app.gui.widgets.project_table import ProjectTableWidget
from app.gui.widgets.queue_panel  import QueuePanel
from app.gui.widgets.logs_panel   import LogsPanel
from app.gui.widgets.preview_panel import PreviewPanel
from app.gui.dialogs.project_detail import ProjectDetailDialog
from app.gui.dialogs.settings_dialog import SettingsDialog
from app.gui.dialogs.preset_manager  import PresetManagerDialog
from app.gui.theme import COLORS
from app.utils.logger import register_log_callback, get_logger

log = get_logger("main_window")

# ── Fixed dimensions (prevents crowding) ──────────────────────────────────────
SIDEBAR_W   = 180
TOP_BAR_H   = 48
NAV_BTN_H   = 46
STATUS_BAR_H= 24
BTN_H       = 32     # all action buttons same height
BTN_MIN_W   = 110    # minimum button width


class NavButton(QPushButton):
    """Left-sidebar navigation button with active state."""
    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._icon  = icon
        self._label = label
        self.setFixedHeight(NAV_BTN_H)
        self.setCheckable(False)
        self.setCursor(Qt.PointingHandCursor)
        self._set_active(False)

    def set_active(self, active: bool):
        self._set_active(active)

    def _set_active(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background:{COLORS['bg_selected']};
                    color:{COLORS['text_primary']};
                    border-left:3px solid {COLORS['accent']};
                    border-top:none; border-right:none; border-bottom:none;
                    border-radius:0; text-align:left; padding:0 14px;
                    font-size:13px; font-weight:600;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background:transparent;
                    color:{COLORS['text_secondary']};
                    border-left:3px solid transparent;
                    border-top:none; border-right:none; border-bottom:none;
                    border-radius:0; text-align:left; padding:0 14px;
                    font-size:13px;
                }}
                QPushButton:hover {{
                    background:{COLORS['bg_hover']};
                    color:{COLORS['text_primary']};
                }}
            """)
        self.setText(f"  {self._icon}  {self._label}")


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state         = AppState.instance()
        self._scan_worker   = None
        self._sample_worker = None
        self._nav_btns      = []

        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._restore_geometry()

        register_log_callback(self._on_log_entry)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(2000)

        QTimer.singleShot(200, self._initial_load)

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("VideoForge — Bulk Video Generator")
        self.setMinimumSize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_content(), 1)

        body_w = QWidget()
        body_w.setLayout(body)
        root.addWidget(body_w, 1)

        # Status bar
        sb = QStatusBar()
        sb.setFixedHeight(STATUS_BAR_H)
        sb.setStyleSheet(
            f"QStatusBar{{background:{COLORS['bg_tertiary']};"
            f"border-top:1px solid {COLORS['border']};"
            f"font-size:12px;color:{COLORS['text_secondary']};}}"
        )
        self.setStatusBar(sb)

        self._status_lbl = QLabel("Ready")
        self._ffmpeg_lbl = QLabel("FFmpeg: …")
        self._ffmpeg_lbl.setStyleSheet(f"color:{COLORS['text_muted']};padding:0 8px;")
        sb.addWidget(self._status_lbl, 1)
        sb.addPermanentWidget(self._ffmpeg_lbl)

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(TOP_BAR_H)
        bar.setStyleSheet(
            f"background:{COLORS['bg_tertiary']};"
            f"border-bottom:1px solid {COLORS['border']};"
        )

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)

        # Logo — fixed width so buttons never crowd it
        logo = QLabel("🎬  VideoForge")
        logo.setFixedWidth(150)
        logo.setStyleSheet(
            f"font-size:15px;font-weight:700;"
            f"color:{COLORS['accent_text']};background:transparent;"
        )

        # Action buttons — all identical height, minimum width enforced
        self._btn_add       = self._mkbtn("+ Add Folders", "primary",  BTN_MIN_W + 20)
        self._btn_queue_all = self._mkbtn("Queue All Valid", "",        BTN_MIN_W + 20)
        self._btn_pause     = self._mkbtn("Pause Queue",   "",          BTN_MIN_W)

        self._btn_add.clicked.connect(self._add_folders_dialog)
        self._btn_queue_all.clicked.connect(self._queue_all_valid)
        self._btn_pause.clicked.connect(self._toggle_queue_pause)

        # Progress elements — hidden when idle
        self._scan_bar = QProgressBar()
        self._scan_bar.setRange(0, 100)
        self._scan_bar.setFixedSize(100, 8)
        self._scan_bar.setTextVisible(False)
        self._scan_bar.setVisible(False)

        self._render_bar = QProgressBar()
        self._render_bar.setRange(0, 100)
        self._render_bar.setFixedSize(120, 8)
        self._render_bar.setTextVisible(False)
        self._render_bar.setVisible(False)

        self._render_lbl = QLabel("")
        self._render_lbl.setStyleSheet(
            f"color:{COLORS['accent_text']};font-size:11px;background:transparent;"
        )
        self._render_lbl.setFixedWidth(240)
        self._render_lbl.setVisible(False)

        btn_settings = self._mkbtn("⚙  Settings", "", BTN_MIN_W)
        btn_settings.clicked.connect(self._open_settings)

        # Thin vertical separator after logo
        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(
            f"background:{COLORS['border']};border:none;"
            f"margin-top:8px;margin-bottom:8px;"
        )

        lay.addWidget(logo)
        lay.addSpacing(4)
        lay.addWidget(vsep)
        lay.addSpacing(4)
        lay.addWidget(self._btn_add)
        lay.addWidget(self._btn_queue_all)
        lay.addWidget(self._btn_pause)
        lay.addSpacing(8)
        lay.addWidget(self._scan_bar)
        lay.addWidget(self._render_bar)
        lay.addWidget(self._render_lbl)
        lay.addStretch()
        lay.addWidget(btn_settings)
        return bar

    def _mkbtn(self, text: str, obj: str = "", min_w: int = 0) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(BTN_H)
        if min_w:
            b.setMinimumWidth(min_w)
        if obj:
            b.setObjectName(obj)
        return b

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QFrame:
        sb = QFrame()
        sb.setFixedWidth(SIDEBAR_W)
        sb.setStyleSheet(
            f"background:{COLORS['bg_tertiary']};"
            f"border-right:1px solid {COLORS['border']};"
        )

        lay = QVBoxLayout(sb)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(2)

        pages = [
            ("📊", "Dashboard"),
            ("📁", "Projects"),
            ("⏳", "Queue"),
            ("👁",  "Preview"),
            ("📋", "Logs"),
        ]
        for i, (icon, label) in enumerate(pages):
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda _, idx=i: self._switch_page(idx))
            self._nav_btns.append(btn)
            lay.addWidget(btn)

        self._nav_btns[0].set_active(True)

        # Divider
        lay.addSpacing(8)
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color:{COLORS['border']};max-height:1px;")
        lay.addWidget(div)
        lay.addSpacing(8)

        # Mini stats — 2×2 grid
        stats_label = QLabel("  STATS")
        stats_label.setStyleSheet(
            f"font-size:10px;font-weight:700;letter-spacing:1px;"
            f"color:{COLORS['text_muted']};background:transparent;"
        )
        lay.addWidget(stats_label)
        lay.addSpacing(4)

        row1 = QHBoxLayout()
        row1.setContentsMargins(8, 0, 8, 0)
        row1.setSpacing(6)
        self._st_total = self._mkstat("Total",    COLORS["text_primary"])
        self._st_valid = self._mkstat("Valid",     COLORS["success"])
        row1.addWidget(self._st_total)
        row1.addWidget(self._st_valid)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(8, 4, 8, 0)
        row2.setSpacing(6)
        self._st_done  = self._mkstat("Done",      COLORS["status_completed"])
        self._st_fail  = self._mkstat("Failed",    COLORS["error"])
        row2.addWidget(self._st_done)
        row2.addWidget(self._st_fail)
        lay.addLayout(row2)

        lay.addStretch()

        self._ffmpeg_dot = QLabel("  ● FFmpeg: checking")
        self._ffmpeg_dot.setWordWrap(True)
        self._ffmpeg_dot.setStyleSheet(
            f"font-size:11px;color:{COLORS['text_muted']};background:transparent;padding:4px 8px;"
        )
        lay.addWidget(self._ffmpeg_dot)
        return sb

    def _mkstat(self, label: str, color: str) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        f.setFixedHeight(52)
        vl = QVBoxLayout(f)
        vl.setContentsMargins(8, 4, 8, 4)
        vl.setSpacing(1)
        val = QLabel("0")
        val.setStyleSheet(f"font-size:18px;font-weight:700;color:{color};background:transparent;")
        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size:10px;color:{COLORS['text_muted']};background:transparent;")
        vl.addWidget(val)
        vl.addWidget(lbl)
        f._val = val
        return f

    # ── Content stack ─────────────────────────────────────────────────────────

    def _build_content(self) -> QStackedWidget:
        self._stack = QStackedWidget()

        self._dashboard     = DashboardPanel()
        self._project_table = ProjectTableWidget()
        self._queue_panel   = QueuePanel()
        self._preview_panel = PreviewPanel()
        self._logs_panel    = LogsPanel()

        for w in [self._dashboard, self._project_table,
                  self._queue_panel, self._preview_panel, self._logs_panel]:
            self._stack.addWidget(w)

        return self._stack

    def _switch_page(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.set_active(i == index)
        if index == 4:
            self._logs_panel.load_buffer()

    # ─────────────────────────────────────────────────────────────────────────
    # Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        a = QAction("Add Folders…", self)
        a.setShortcut(QKeySequence.Open)
        a.triggered.connect(self._add_folders_dialog)
        fm.addAction(a)
        fm.addSeparator()
        fm.addAction("Clear All Projects").triggered.connect(self._clear_all_projects)
        fm.addSeparator()
        q = QAction("Quit", self)
        q.setShortcut("Ctrl+Q")
        q.triggered.connect(self.close)
        fm.addAction(q)

        qm = mb.addMenu("Queue")
        qm.addAction("Queue All Valid").triggered.connect(self._queue_all_valid)
        qm.addAction("Pause / Resume").triggered.connect(self._toggle_queue_pause)
        qm.addAction("Cancel All").triggered.connect(self._cancel_all_jobs)
        qm.addSeparator()
        qm.addAction("Clear Completed").triggered.connect(self._clear_completed_jobs)

        tm = mb.addMenu("Tools")
        tm.addAction("Settings…\tCtrl+,").triggered.connect(self._open_settings)
        tm.addAction("Preset Manager…").triggered.connect(self._open_preset_manager)
        tm.addSeparator()
        tm.addAction("Export Logs…").triggered.connect(self._export_logs)

        hm = mb.addMenu("Help")
        hm.addAction("About VideoForge").triggered.connect(self._show_about)

    # ─────────────────────────────────────────────────────────────────────────
    # Signal wiring
    # ─────────────────────────────────────────────────────────────────────────

    def _connect_signals(self):
        s = self._state
        s.projects_changed.connect(self._refresh_projects)
        s.project_updated.connect(self._on_project_updated)
        s.ffmpeg_status_changed.connect(self._on_ffmpeg_status)

        self._dashboard.add_folders_clicked.connect(self._add_folders_dialog)
        self._dashboard.queue_all_clicked.connect(self._queue_all_valid)
        self._dashboard.open_settings_clicked.connect(self._open_settings)
        self._dashboard.view_logs_clicked.connect(lambda: self._switch_page(4))

        self._project_table.add_folders_requested.connect(self._add_folders_dialog)
        self._project_table.folders_dropped.connect(self._scan_paths)
        self._project_table.project_selected.connect(self._on_project_selected)
        self._project_table.queue_project.connect(self._queue_single_project)
        self._project_table.remove_project.connect(self._remove_project)
        self._project_table.open_folder.connect(self._open_project_folder)
        self._project_table.edit_project.connect(self._edit_project)
        self._project_table.queue_selected.connect(self._queue_selected_projects)

        self._queue_panel.pause_clicked.connect(self._pause_queue)
        self._queue_panel.resume_clicked.connect(self._resume_queue)
        self._queue_panel.cancel_all_clicked.connect(self._cancel_all_jobs)
        self._queue_panel.clear_completed_clicked.connect(self._clear_completed_jobs)
        self._queue_panel.cancel_job.connect(self._cancel_job)
        self._queue_panel.retry_job.connect(self._retry_job)

        self._preview_panel.sample_render_requested.connect(self._run_sample_render)

        q = s.queue
        if q:
            q.job_added.connect(self._on_job_added)
            q.job_started.connect(self._on_job_started)
            q.job_progress.connect(self._on_job_progress)
            q.job_completed.connect(self._on_job_completed)
            q.job_failed.connect(self._on_job_failed)
            q.job_cancelled.connect(self._on_job_cancelled)

    # ─────────────────────────────────────────────────────────────────────────
    # Startup
    # ─────────────────────────────────────────────────────────────────────────

    def _initial_load(self):
        projects = self._state.get_all_projects()
        if projects:
            self._project_table.set_projects(projects)
            log.info(f"Restored {len(projects)} projects from last session")
        self._refresh_stats()
        self._refresh_queue_panel()
        self._set_status(f"Ready — {len(projects)} project(s) loaded")

    # ─────────────────────────────────────────────────────────────────────────
    # Import / scan
    # ─────────────────────────────────────────────────────────────────────────

    def _add_folders_dialog(self):
        """
        Multi-mode folder import dialog.
        Lets users add:
          - A single project folder directly (the folder IS the project)
          - Multiple independent project folders at once
          - A container folder to scan recursively for sub-projects
        """
        dlg = _FolderImportDialog(
            parent=self,
            last_folder=self._state.settings.get("last_import_folder", ""),
        )
        if dlg.exec() == QDialog.Accepted:
            folders = dlg.selected_folders()
            scan_mode = dlg.scan_mode()   # "direct" | "container"
            if folders:
                self._state.settings.set(
                    "last_import_folder", str(Path(folders[-1]).parent)
                )
                self._scan_paths(folders, force_direct=(scan_mode == "direct"))

    def _scan_paths(self, paths: list, force_direct: bool = False):
        """
        Launch a background scan for the given folder paths.
        force_direct=True  → treat each folder as a standalone project (no sub-scan)
        force_direct=False → recursive container scan (existing behaviour)
        """
        from app.workers.render_worker import ScanWorker
        if self._scan_worker and self._scan_worker.isRunning():
            self._set_status("Scan already running…")
            return
        self._set_status(f"Scanning {len(paths)} folder(s)…")
        self._scan_bar.setValue(0)
        self._scan_bar.setVisible(True)

        self._scan_worker = ScanWorker(
            folders=[Path(p) for p in paths],
            recursive=False if force_direct else self._state.settings.get("recursive_scan", True),
            max_depth=0 if force_direct else self._state.settings.get("max_scan_depth", 5),
            force_direct=force_direct,
            default_profile=self._state.settings.get_default_profile(),
        )
        self._scan_worker.scan_progress.connect(self._on_scan_progress)
        self._scan_worker.project_found.connect(self._on_project_found)
        self._scan_worker.scan_complete.connect(self._on_scan_complete)
        self._scan_worker.scan_error.connect(lambda e: log.error(f"Scan: {e}"))
        self._scan_worker.start()

    def _on_scan_progress(self, pct: float, msg: str):
        self._scan_bar.setValue(int(pct))
        self._set_status(msg)

    def _on_project_found(self, project: Project):
        added = self._state.add_project(project)
        if added:
            self._project_table.add_project(project)
            if (self._state.settings.get("auto_queue_valid_projects", False)
                    and project.status == ProjectStatus.VALID):
                self._queue_single_project(project.id)

    def _on_scan_complete(self, count: int):
        self._scan_bar.setVisible(False)
        self._set_status(f"Scan complete — {count} project(s) found")
        self._refresh_stats()
        self._switch_page(1)

    # ─────────────────────────────────────────────────────────────────────────
    # Queue actions
    # ─────────────────────────────────────────────────────────────────────────

    def _queue_all_valid(self):
        valid = self._state.get_projects_by_status(ProjectStatus.VALID)
        if not valid:
            self._set_status("No valid projects to queue")
            return
        self._state.queue_all_valid()
        self._set_status(f"Queued {len(valid)} project(s)")
        self._switch_page(2)

    def _queue_single_project(self, project_id: str):
        project = self._state.get_project(project_id)
        if not project:
            return
        ok = self._state.queue_project(project)
        self._set_status(f"Queued: {project.name}" if ok else
                         f"Cannot queue: {project.status.value}")

    def _queue_selected_projects(self, ids: list):
        queued = sum(
            1 for pid in ids
            if (p := self._state.get_project(pid)) and self._state.queue_project(p)
        )
        self._set_status(f"Queued {queued} project(s)")

    def _pause_queue(self):
        if self._state.queue:
            self._state.queue.pause()
            self._queue_panel.set_paused(True)
            self._btn_pause.setText("Resume Queue")
            self._set_status("Queue paused")

    def _resume_queue(self):
        if self._state.queue:
            self._state.queue.resume()
            self._queue_panel.set_paused(False)
            self._btn_pause.setText("Pause Queue")
            self._set_status("Queue resumed")

    def _toggle_queue_pause(self):
        if self._state.queue and self._state.queue.is_paused:
            self._resume_queue()
        else:
            self._pause_queue()

    def _cancel_all_jobs(self):
        if self._state.queue:
            self._state.queue.cancel_all()
            self._set_status("All jobs cancelled")

    def _clear_completed_jobs(self):
        if self._state.queue:
            self._state.queue.clear_completed()
            self._refresh_queue_panel()

    def _cancel_job(self, job_id: str):
        if self._state.queue:
            self._state.queue.cancel_job(job_id)

    def _retry_job(self, job_id: str):
        if self._state.queue:
            self._state.queue.retry_job(job_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Project actions
    # ─────────────────────────────────────────────────────────────────────────

    def _on_project_selected(self, project_id: str):
        project = self._state.get_project(project_id)
        if project:
            self._preview_panel.set_project(project)

    def _edit_project(self, project_id: str):
        project = self._state.get_project(project_id)
        if not project:
            return
        presets = {n: p.to_dict()
                   for n in self._state.settings.list_presets()
                   if (p := self._state.settings.get_preset(n))}
        dlg = ProjectDetailDialog(project, presets=presets, parent=self)
        dlg.project_updated.connect(self._on_project_edited)
        dlg.exec()

    def _on_project_edited(self, project: Project):
        self._state.update_project(project)
        if getattr(project, "_queue_after_save", False):
            self._queue_single_project(project.id)
            delattr(project, "_queue_after_save")

    def _remove_project(self, project_id: str):
        self._state.remove_project(project_id)
        self._project_table.remove_project_by_id(project_id)
        self._refresh_stats()

    def _open_project_folder(self, project_id: str):
        project = self._state.get_project(project_id)
        if project and project.folder.exists():
            self._open_in_explorer(project.folder)

    def _clear_all_projects(self):
        if QMessageBox.question(
            self, "Clear All", "Remove all projects? (Files on disk are NOT deleted.)",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            for p in self._state.get_all_projects():
                self._state.remove_project(p.id)
            self._project_table.set_projects([])
            self._refresh_stats()

    # ─────────────────────────────────────────────────────────────────────────
    # Queue callbacks
    # ─────────────────────────────────────────────────────────────────────────

    def _on_job_added(self, job_id: str):
        job = self._state.queue.get_job(job_id) if self._state.queue else None
        if not job:
            return
        project = self._state.get_project(job.project_id)
        pname = project.name if project else job.project_id[:8]
        self._queue_panel.add_job(job, pname)
        self._update_queue_badge()

    def _on_job_started(self, job_id: str):
        import time as _time
        self._render_start_time = _time.time()
        self._queue_panel.update_job_status(job_id, "running")
        job = self._state.queue.get_job(job_id) if self._state.queue else None
        if job:
            project = self._state.get_project(job.project_id)
            if project:
                n = len(project.image_paths)
                dur = project.audio_duration or 0
                dur_str = f"{int(dur//60)}m{int(dur%60):02d}s" if dur >= 60 else f"{dur:.0f}s"
                name = project.name[:30] + "…" if len(project.name) > 30 else project.name
                self._render_lbl.setText(
                    f"Rendering: {name}  ({n} images, {dur_str})"
                )
                self._render_lbl.setVisible(True)
                self._render_bar.setValue(0)
                self._render_bar.setVisible(True)

    def _on_job_progress(self, job_id: str, pct: float, msg: str):
        import time as _time
        self._queue_panel.update_job_progress(job_id, pct, msg)
        self._render_bar.setValue(int(pct))
        if msg:
            short = msg[:55] + "…" if len(msg) > 55 else msg
            # Add elapsed time if we have a start time
            start = getattr(self, '_render_start_time', None)
            if start and pct > 1:
                elapsed = _time.time() - start
                if pct > 5 and elapsed > 10:
                    remaining = elapsed / (pct / 100) - elapsed
                    if remaining > 60:
                        eta = f"  ~{int(remaining//60)}m{int(remaining%60):02d}s left"
                    else:
                        eta = f"  ~{int(remaining)}s left"
                else:
                    eta = f"  {int(elapsed)}s elapsed"
                self._render_lbl.setText(f"{short}{eta}")
            else:
                self._render_lbl.setText(short)

    def _on_job_completed(self, job_id: str, output_path: str):
        import time as _time
        self._queue_panel.update_job_status(job_id, "completed")
        self._queue_panel.update_job_progress(job_id, 100.0)
        self._render_lbl.setVisible(False)
        self._render_bar.setVisible(False)
        job = self._state.queue.get_job(job_id) if self._state.queue else None
        if job:
            project = self._state.get_project(job.project_id)
            if project:
                self._project_table.update_project(project)
                # Show size and time if available
                elapsed = round(_time.time() - getattr(self, '_render_start_time', _time.time()))
                size_str = ""
                if output_path:
                    try:
                        sz = Path(output_path).stat().st_size
                        size_str = f" — {sz//(1024*1024)} MB"
                    except Exception:
                        pass
                mins, secs = elapsed // 60, elapsed % 60
                time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
                self._set_status(f"✓ Done: {project.name}  ({time_str}{size_str})")
                if output_path and self._state.settings.get("auto_open_output", False):
                    self._open_in_explorer(Path(output_path).parent)
        self._refresh_stats()
        self._update_queue_badge()

    def _on_job_failed(self, job_id: str, error: str):
        self._queue_panel.update_job_status(job_id, "failed")
        self._render_lbl.setVisible(False)
        self._render_bar.setVisible(False)
        job = self._state.queue.get_job(job_id) if self._state.queue else None
        if job:
            project = self._state.get_project(job.project_id)
            if project:
                self._project_table.update_project(project)
                self._set_status(f"Failed: {project.name} — {error[:50]}")
        self._refresh_stats()
        self._update_queue_badge()

    def _on_job_cancelled(self, job_id: str):
        self._queue_panel.update_job_status(job_id, "cancelled")
        self._render_lbl.setVisible(False)
        self._render_bar.setVisible(False)
        self._update_queue_badge()

    def _on_project_updated(self, project_id: str):
        project = self._state.get_project(project_id)
        if project:
            self._project_table.update_project(project)

    def _on_ffmpeg_status(self, ok: bool, message: str):
        if ok:
            self._ffmpeg_lbl.setText("FFmpeg: ✓")
            self._ffmpeg_lbl.setStyleSheet(f"color:{COLORS['success']};padding:0 8px;")
            self._ffmpeg_dot.setText("  ● FFmpeg ready")
            self._ffmpeg_dot.setStyleSheet(
                f"font-size:11px;color:{COLORS['success']};background:transparent;padding:4px 8px;"
            )
        else:
            self._ffmpeg_lbl.setText("FFmpeg: not found")
            self._ffmpeg_lbl.setStyleSheet(f"color:{COLORS['warning']};padding:0 8px;")
            self._ffmpeg_lbl.setToolTip(message)
            self._ffmpeg_dot.setText("  ● FFmpeg missing")
            self._ffmpeg_dot.setStyleSheet(
                f"font-size:11px;color:{COLORS['warning']};background:transparent;padding:4px 8px;"
            )
        self._dashboard.update_ffmpeg_status(ok, message)

    def _on_log_entry(self, entry: dict):
        self._logs_panel.append_log(entry)

    # ─────────────────────────────────────────────────────────────────────────
    # Settings
    # ─────────────────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._state.settings, parent=self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.ffmpeg_path_changed.connect(self._on_ffmpeg_path_changed)
        dlg.exec()

    def _open_preset_manager(self):
        PresetManagerDialog(self._state.settings, parent=self).exec()

    def _on_settings_changed(self):
        if self._state.queue:
            self._state.queue.max_concurrent = self._state.settings.get(
                "max_concurrent_jobs", 1
            )
        self._set_status("Settings saved")

    def _on_ffmpeg_path_changed(self, path: str):
        from app.utils import ffmpeg_utils
        ffmpeg_utils._ffmpeg_path  = path or None
        ffmpeg_utils._ffprobe_path = None
        ok, msg = ffmpeg_utils.check_ffmpeg_ready()
        self._on_ffmpeg_status(ok, msg)

    def _run_sample_render(self, project_id: str):
        project = self._state.get_project(project_id)
        if not project or not project.audio_path:
            self._set_status("Cannot render sample: project not ready")
            return
        from app.utils.ffmpeg_utils import find_ffmpeg
        ffmpeg = find_ffmpeg(self._state.settings.get("ffmpeg_path") or None)
        if not ffmpeg:
            self._set_status("FFmpeg not found — cannot render sample")
            return
        out = project.folder / "_vf_temp" / f"_sample_{project.name[:30]}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        from app.core.job import Job
        from app.workers.render_worker import RenderWorker
        sample_job = Job(project_id=project.id)
        self._sample_worker = RenderWorker(
            job=sample_job, project=project, output_path=out,
            ffmpeg_bin=ffmpeg, overwrite=True,
        )
        self._sample_worker.signals.job_progress.connect(
            lambda _jid, pct, _msg: self._scan_bar.setValue(int(pct))
        )
        self._sample_worker.signals.job_completed.connect(
            lambda _jid, path: self._on_sample_done(path)
        )
        self._sample_worker.signals.job_failed.connect(
            lambda _jid, err: self._set_status(f"Sample failed: {err[:50]}")
        )
        self._scan_bar.setVisible(True)
        self._set_status(f"Generating sample for {project.name}…")
        self._sample_worker.start()

    def _on_sample_done(self, output_path: str):
        self._scan_bar.setVisible(False)
        self._set_status(f"Sample ready: {Path(output_path).name}")
        if output_path and os.path.exists(output_path):
            try:
                if os.name == "nt":
                    os.startfile(output_path)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Refresh helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_stats(self):
        stats = self._state.get_stats()
        self._dashboard.update_stats(stats)
        self._st_total._val.setText(str(stats.get("total_projects", 0)))
        self._st_valid._val.setText(str(stats.get("valid", 0)))
        self._st_done._val.setText(str(stats.get("completed", 0)))
        self._st_fail._val.setText(str(stats.get("failed", 0)))
        self._update_queue_badge()

    def _refresh_projects(self):
        self._project_table.set_projects(self._state.get_all_projects())
        self._refresh_stats()

    def _refresh_queue_panel(self):
        if not self._state.queue:
            return
        jobs     = self._state.queue.get_all_jobs()
        projects = {p.id: p for p in self._state.get_all_projects()}
        self._queue_panel.refresh_from_jobs(jobs, projects)

    def _update_queue_badge(self):
        if not self._state.queue:
            return
        n = self._state.queue.active_count + self._state.queue.pending_count
        self._nav_btns[2].setText(
            f"  ⏳  Queue ({n})" if n else "  ⏳  Queue"
        )

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)
        self.statusBar().showMessage(msg, 7000)

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def _open_in_explorer(self, path: Path):
        try:
            if os.name == "nt":
                os.startfile(str(path))
        except Exception as e:
            log.warning(f"Could not open folder: {e}")

    def _export_logs(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", "videoforge_logs.txt", "Text Files (*.txt)"
        )
        if path:
            from app.utils.logger import export_logs
            export_logs(Path(path))
            self._set_status("Logs exported")

    def _show_about(self):
        QMessageBox.about(
            self, "About VideoForge",
            "<b>VideoForge</b> v1.0<br><br>"
            "Bulk video generation from images, audio, and transcripts.<br><br>"
            "Stack: Python · PySide6 · FFmpeg · SQLite · faster-whisper<br><br>"
            "Subtitles burned directly into video using ASS format."
        )

    def _restore_geometry(self):
        geo = self._state.settings.get("window_geometry", {})
        if isinstance(geo, dict) and geo:
            try:
                self.resize(geo.get("w", 1280), geo.get("h", 780))
                self.move(geo.get("x", 80), geo.get("y", 80))
                return
            except Exception:
                pass
        self.resize(1280, 780)
        scr = QApplication.primaryScreen().geometry()
        self.move(
            max(0, (scr.width() - self.width()) // 2),
            max(0, (scr.height() - self.height()) // 2),
        )

    def closeEvent(self, event: QCloseEvent):
        g = self.geometry()
        self._state.settings.set("window_geometry",
            {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()})
        if self._state.queue and self._state.queue.active_count > 0:
            if QMessageBox.question(
                self, "Render in Progress",
                f"{self._state.queue.active_count} render(s) still running.\nClose anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) == QMessageBox.No:
                event.ignore()
                return
        self._state.shutdown()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Multi-folder import dialog
# ─────────────────────────────────────────────────────────────────────────────

class _FolderImportDialog(QDialog):
    """
    Dialog for flexible project folder import.

    Three modes the user can choose:
      Add Project Folder   — picks one or more folders, each treated as a
                             standalone project (no recursive sub-scan).
      Scan Container Folder — picks one parent folder and scans it recursively
                              for sub-projects (original behaviour).

    The user builds a list of folders to process, then clicks OK.
    """

    def __init__(self, parent=None, last_folder: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Add Project Folders")
        self.setMinimumSize(600, 420)
        self._last_folder = last_folder or str(Path.home())
        self._mode = "container"   # "direct" | "container"
        self._folders: list[str] = []
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        from app.gui.theme import COLORS
        self.setStyleSheet(
            f"QDialog{{background:{COLORS['bg_primary']};color:{COLORS['text_primary']};}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Mode selector ──────────────────────────────────────────────────
        mode_frame = QFrame()
        mode_frame.setStyleSheet(
            f"QFrame{{background:{COLORS['bg_secondary']};"
            f"border:1px solid {COLORS['border']};border-radius:6px;padding:6px;}}"
        )
        mode_lay = QHBoxLayout(mode_frame)
        mode_lay.setContentsMargins(8, 4, 8, 4)
        mode_lay.setSpacing(8)

        self._btn_mode_direct    = QPushButton("📁  Add Project Folder(s)")
        self._btn_mode_container = QPushButton("🗂  Select Master Output Folder")

        for btn in (self._btn_mode_direct, self._btn_mode_container):
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)

        self._btn_mode_container.setChecked(True)
        self._btn_mode_direct.clicked.connect(lambda: self._set_mode("direct"))
        self._btn_mode_container.clicked.connect(lambda: self._set_mode("container"))

        mode_lay.addWidget(self._btn_mode_direct, 1)
        mode_lay.addWidget(self._btn_mode_container, 1)
        root.addWidget(mode_frame)

        # ── Description label ──────────────────────────────────────────────
        self._desc_lbl = QLabel()
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(
            f"color:{COLORS['text_secondary']};font-size:12px;padding:2px 0;"
        )
        root.addWidget(self._desc_lbl)

        # ── Folder list ────────────────────────────────────────────────────
        list_header = QLabel("Selected folders:")
        list_header.setStyleSheet(f"color:{COLORS['text_primary']};font-weight:600;")
        root.addWidget(list_header)

        self._folder_list = QListWidget()
        self._folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._folder_list.setMinimumHeight(160)
        self._folder_list.setStyleSheet(
            f"QListWidget{{background:{COLORS['bg_secondary']};"
            f"border:1px solid {COLORS['border']};border-radius:4px;"
            f"color:{COLORS['text_primary']};font-size:12px;}}"
            f"QListWidget::item:selected{{background:{COLORS['bg_selected']};}}"
        )
        root.addWidget(self._folder_list, 1)

        # ── Folder list action buttons ─────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_browse = QPushButton("+ Browse…")
        self._btn_browse.setFixedHeight(28)
        self._btn_browse.setCursor(Qt.PointingHandCursor)
        self._btn_browse.clicked.connect(self._browse_add)

        self._btn_remove = QPushButton("− Remove Selected")
        self._btn_remove.setFixedHeight(28)
        self._btn_remove.setCursor(Qt.PointingHandCursor)
        self._btn_remove.clicked.connect(self._remove_selected)

        self._btn_clear = QPushButton("Clear All")
        self._btn_clear.setFixedHeight(28)
        self._btn_clear.setCursor(Qt.PointingHandCursor)
        self._btn_clear.clicked.connect(self._clear_all)

        btn_row.addWidget(self._btn_browse)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_clear)
        root.addLayout(btn_row)

        # ── OK / Cancel ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._update_mode_styles()
        self._update_desc()

    # ── Mode handling ─────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        self._btn_mode_direct.setChecked(mode == "direct")
        self._btn_mode_container.setChecked(mode == "container")
        self._update_mode_styles()
        self._update_desc()
        # Container mode only makes sense with one folder
        if mode == "container" and self._folder_list.count() > 1:
            # Keep only the first
            first = self._folders[0]
            self._folders = [first]
            self._folder_list.clear()
            self._folder_list.addItem(first)

    def _update_mode_styles(self):
        from app.gui.theme import COLORS
        for btn, mode in (
            (self._btn_mode_direct, "direct"),
            (self._btn_mode_container, "container"),
        ):
            active = (self._mode == mode)
            btn.setStyleSheet(
                f"QPushButton{{background:{COLORS['accent'] if active else COLORS['bg_tertiary']};"
                f"color:{COLORS['text_primary']};border:1px solid "
                f"{COLORS['accent'] if active else COLORS['border']};"
                f"border-radius:4px;font-size:12px;font-weight:{'600' if active else '400'};}}"
                f"QPushButton:hover{{background:{COLORS['accent_hover'] if active else COLORS['bg_hover']};}}"
            )

    def _update_desc(self):
        if self._mode == "direct":
            self._desc_lbl.setText(
                "Each folder you add is treated as a complete project. "
                "The folder must contain images, audio, and optionally a script. "
                "Use this when your project folders are spread across different locations."
            )
        else:
            self._desc_lbl.setText(
                "Pick one parent folder that contains multiple project sub-folders. "
                "VideoForge will scan it recursively to find all projects inside. "
                "This is the original container-scan behaviour."
            )

    # ── List management ───────────────────────────────────────────────────────

    def _browse_add(self):
        if self._mode == "container":
            # Container mode: pick exactly one folder
            folder = QFileDialog.getExistingDirectory(
                self, "Select Container Folder", self._last_folder
            )
            if folder:
                self._last_folder = folder
                self._folders = [folder]
                self._folder_list.clear()
                self._folder_list.addItem(folder)
        else:
            # Direct mode: pick one folder (call repeatedly to add more)
            folder = QFileDialog.getExistingDirectory(
                self, "Select Project Folder", self._last_folder
            )
            if folder and folder not in self._folders:
                self._last_folder = folder
                self._folders.append(folder)
                self._folder_list.addItem(folder)

    def _remove_selected(self):
        # Collect rows in descending order so earlier removals
        # don't shift the indices of later items in the list.
        rows = sorted(
            {self._folder_list.row(item) for item in self._folder_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self._folder_list.takeItem(row)
            if 0 <= row < len(self._folders):
                self._folders.pop(row)

    def _clear_all(self):
        self._folders.clear()
        self._folder_list.clear()

    # ── Result accessors ──────────────────────────────────────────────────────

    def selected_folders(self) -> list[str]:
        return list(self._folders)

    def scan_mode(self) -> str:
        return self._mode

    # ── Validation ────────────────────────────────────────────────────────────

    def _on_ok(self):
        if not self._folders:
            QMessageBox.warning(
                self, "No Folders Selected",
                "Please add at least one folder before clicking OK."
            )
            return
        self.accept()


