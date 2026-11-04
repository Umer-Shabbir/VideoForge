"""
Project table: displays all loaded projects with status, metadata, and actions.
Supports search, filter, sort, multi-select, drag-drop.

Fixes applied:
  - get_selected_project_ids: cellWidget returns the *container* QWidget, not the
    QCheckBox — must call findChild(QCheckBox) to get the actual checkbox.
  - _on_select_all: same fix.
  - Layout: cleaner toolbar that doesn't overflow on smaller screens.
  - Removed text-shadow from inline styles (not supported by Qt CSS engine).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLineEdit, QComboBox, QMenu, QFrame, QSizePolicy, QCheckBox,
    QProgressBar, QSpacerItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent

from app.core.project import Project, ProjectStatus
from app.gui.widgets.common import StatusBadge, HealthBar, SectionHeader
from app.gui.theme import COLORS, STATUS_COLORS


COLUMNS     = ["", "Name", "Preset", "Status", "Imgs", "Duration", "Words", "Health", "Output Path", "Actions"]
COL_CHECK   = 0
COL_NAME    = 1
COL_PRESET  = 2
COL_STATUS  = 3
COL_IMAGES  = 4
COL_DUR     = 5
COL_WORDS   = 6
COL_HEALTH  = 7
COL_OUTPUT  = 8
COL_ACTIONS = 9


def _find_checkbox(cell_widget) -> QCheckBox | None:
    """
    cellWidget() returns the container QWidget, not the QCheckBox inside it.
    Use findChild to get the actual QCheckBox.
    """
    if cell_widget is None:
        return None
    if isinstance(cell_widget, QCheckBox):
        return cell_widget
    return cell_widget.findChild(QCheckBox)


class ProjectTableWidget(QWidget):
    project_selected      = Signal(str)   # project_id
    queue_project         = Signal(str)   # project_id
    remove_project        = Signal(str)   # project_id
    open_folder           = Signal(str)   # project_id
    edit_project          = Signal(str)   # project_id
    queue_selected        = Signal(list)  # [project_id, ...]
    preset_changed        = Signal(str, str)  # (project_id, preset_name)
    batch_preset_applied  = Signal(list, str) # ([project_ids], preset_name)
    force_align_requested = Signal(str)       # (project_id)
    add_folders_requested = Signal()
    folders_dropped       = Signal(list)  # [path_str, ...]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: dict[str, Project] = {}
        self._available_presets: list[str] = []
        self._setup_ui()
        self.setAcceptDrops(True)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Toolbar row 1: search + filter ────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search projects...")
        self._search.setFixedHeight(32)
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter_changed)

        self._status_filter = QComboBox()
        self._status_filter.addItems(["All", "Valid", "Invalid", "Queued",
                                       "Processing", "Completed", "Failed"])
        self._status_filter.setFixedWidth(130)
        self._status_filter.setFixedHeight(32)
        self._status_filter.currentTextChanged.connect(self._on_filter_changed)

        self._count_lbl = QLabel("0 projects")
        self._count_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        self._count_lbl.setFixedWidth(90)

        row1.addWidget(self._search, 1)
        row1.addWidget(self._status_filter)
        row1.addWidget(self._count_lbl)
        layout.addLayout(row1)

        # ── Toolbar row 2: actions ─────────────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self._select_all_cb = QCheckBox("Select all")
        self._select_all_cb.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._select_all_cb.stateChanged.connect(self._on_select_all)

        btn_queue_sel = QPushButton("Queue Selected")
        btn_queue_sel.setObjectName("primary")
        btn_queue_sel.setFixedHeight(30)
        btn_queue_sel.clicked.connect(self._queue_selected)

        btn_remove_sel = QPushButton("Remove Selected")
        btn_remove_sel.setFixedHeight(30)
        btn_remove_sel.setStyleSheet(
            f"color: {COLORS['error']}; border-color: {COLORS['error']};"
        )
        btn_remove_sel.clicked.connect(self._remove_selected)

        btn_add = QPushButton("+ Add Folders")
        btn_add.setObjectName("success")
        btn_add.setFixedHeight(30)
        btn_add.clicked.connect(self.add_folders_requested)

        # Batch preset assignment controls
        lbl_preset = QLabel("Preset:")
        lbl_preset.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-left: 8px;")
        self._batch_preset_combo = QComboBox()
        self._batch_preset_combo.setFixedHeight(30)
        self._batch_preset_combo.setMinimumWidth(130)

        btn_apply_preset = QPushButton("Apply to Selected")
        btn_apply_preset.setFixedHeight(30)
        btn_apply_preset.clicked.connect(self._apply_batch_preset)

        row2.addWidget(self._select_all_cb)
        row2.addWidget(btn_queue_sel)
        row2.addWidget(btn_remove_sel)
        row2.addWidget(lbl_preset)
        row2.addWidget(self._batch_preset_combo)
        row2.addWidget(btn_apply_preset)
        row2.addStretch()
        row2.addWidget(btn_add)
        layout.addLayout(row2)

        # ── Table ──────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionsMovable(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        hdr = self._table.horizontalHeader()
        hdr.setDefaultSectionSize(90)
        hdr.resizeSection(COL_CHECK,   28)
        hdr.resizeSection(COL_NAME,    180)
        hdr.resizeSection(COL_PRESET,  135)
        hdr.resizeSection(COL_STATUS,  95)
        hdr.resizeSection(COL_IMAGES,  45)
        hdr.resizeSection(COL_DUR,     65)
        hdr.resizeSection(COL_WORDS,   55)
        hdr.resizeSection(COL_HEALTH,  65)
        hdr.resizeSection(COL_ACTIONS, 195)
        hdr.setSectionResizeMode(COL_NAME,   QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_OUTPUT, QHeaderView.Stretch)
        hdr.setMinimumSectionSize(28)

        layout.addWidget(self._table, 1)

        # ── Drop hint (shown when empty) ───────────────────────────────────────
        self._drop_hint = QLabel(
            "Drag & drop project folders here  —  or click '+ Add Folders'"
        )
        self._drop_hint.setAlignment(Qt.AlignCenter)
        self._drop_hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 14px; "
            f"border: 2px dashed {COLORS['border']}; border-radius: 8px; padding: 30px;"
        )
        self._drop_hint.setVisible(True)
        layout.addWidget(self._drop_hint)

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_project(self, project: Project):
        self._projects[project.id] = project
        self._rebuild_table()

    def update_project(self, project: Project):
        self._projects[project.id] = project
        self._update_row(project)

    def remove_project_by_id(self, project_id: str):
        self._projects.pop(project_id, None)
        self._rebuild_table()

    def set_projects(self, projects: list):
        self._projects = {p.id: p for p in projects}
        self._rebuild_table()

    def set_available_presets(self, presets: list[str]):
        self._available_presets = [p for p in presets if p]
        if hasattr(self, "_batch_preset_combo"):
            self._batch_preset_combo.blockSignals(True)
            self._batch_preset_combo.clear()
            self._batch_preset_combo.addItems(self._available_presets)
            self._batch_preset_combo.blockSignals(False)

    def get_selected_project_ids(self) -> list:
        """
        Return project IDs for every row whose checkbox is ticked.
        IMPORTANT: cellWidget(row, COL_CHECK) returns the *container* QWidget,
        not the QCheckBox itself — always use _find_checkbox().
        """
        ids = []
        for row in range(self._table.rowCount()):
            cb = _find_checkbox(self._table.cellWidget(row, COL_CHECK))
            if cb and cb.isChecked():
                item = self._table.item(row, COL_NAME)
                if item:
                    ids.append(item.data(Qt.UserRole))
        return ids

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _rebuild_table(self):
        self._table.setSortingEnabled(False)
        self._table.clearContents()
        self._table.setRowCount(0)

        visible = self._filtered_projects()
        total   = len(self._projects)
        shown   = len(visible)
        self._count_lbl.setText(
            f"{shown} / {total}" if shown != total else f"{total} projects"
        )
        for project in visible:
            self._append_row(project)

        self._table.setSortingEnabled(True)
        self._drop_hint.setVisible(total == 0)

    def _filtered_projects(self) -> list[Project]:
        projects = list(self._projects.values())

        # Status filter
        sf = self._status_filter.currentText().lower()
        if sf not in ("all", "all statuses", ""):
            projects = [p for p in projects if p.status.value == sf]

        # Search filter
        search = self._search.text().strip().lower()
        if search:
            projects = [p for p in projects
                        if search in p.name.lower() or search in str(p.folder).lower()]

        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def _append_row(self, project: Project):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._populate_row(row, project)

    def _populate_row(self, row: int, project: Project):
        # ── Checkbox column ────────────────────────────────────────────────────
        cb = QCheckBox()
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(cb)
        lay.addStretch()
        self._table.setCellWidget(row, COL_CHECK, container)

        # ── Name ───────────────────────────────────────────────────────────────
        name_item = QTableWidgetItem(project.name)
        name_item.setData(Qt.UserRole, project.id)
        name_item.setToolTip(str(project.folder))
        if project.status == ProjectStatus.INVALID:
            name_item.setForeground(QColor(COLORS["error"]))
        self._table.setItem(row, COL_NAME, name_item)

        # ── Preset column ──────────────────────────────────────────────────────
        preset_w = QWidget()
        preset_lay = QHBoxLayout(preset_w)
        preset_lay.setContentsMargins(4, 2, 4, 2)
        preset_combo = QComboBox()
        preset_combo.setFixedHeight(28)
        preset_combo.setStyleSheet("font-size: 11px;")

        curr_p = project.preset_name or "Default"
        items = list(self._available_presets) if self._available_presets else ["Default"]
        if curr_p not in items:
            items.insert(0, curr_p)
        preset_combo.blockSignals(True)
        preset_combo.addItems(items)
        preset_combo.setCurrentText(curr_p)
        preset_combo.blockSignals(False)

        def _on_p_changed(new_p, pid=project.id):
            if project.preset_name != new_p:
                project.preset_name = new_p
                self.preset_changed.emit(pid, new_p)

        preset_combo.currentTextChanged.connect(_on_p_changed)
        preset_lay.addWidget(preset_combo)
        self._table.setCellWidget(row, COL_PRESET, preset_w)

        # ── Status badge ───────────────────────────────────────────────────────
        badge = StatusBadge(project.status.value)
        badge_w = QWidget()
        badge_lay = QHBoxLayout(badge_w)
        badge_lay.setContentsMargins(4, 2, 4, 2)
        badge_lay.addWidget(badge)
        badge_lay.addStretch()
        self._table.setCellWidget(row, COL_STATUS, badge_w)

        # ── Image count ────────────────────────────────────────────────────────
        img_item = QTableWidgetItem(str(project.image_count))
        img_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, COL_IMAGES, img_item)

        # ── Audio duration ─────────────────────────────────────────────────────
        dur_item = QTableWidgetItem(project.duration_str)
        dur_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, COL_DUR, dur_item)

        # ── Word count ─────────────────────────────────────────────────────────
        wc = project.transcript_word_count
        word_item = QTableWidgetItem(str(wc) if wc else "—")
        word_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, COL_WORDS, word_item)

        # ── Health bar ─────────────────────────────────────────────────────────
        health = HealthBar(project.health_score)
        health_w = QWidget()
        health_lay = QHBoxLayout(health_w)
        health_lay.setContentsMargins(8, 0, 8, 0)
        health_lay.addWidget(health)
        self._table.setCellWidget(row, COL_HEALTH, health_w)

        # ── Output path ────────────────────────────────────────────────────────
        out = str(project.output_path) if project.output_path else "—"
        out_item = QTableWidgetItem(out)
        out_item.setForeground(QColor(COLORS["text_muted"]))
        out_item.setToolTip(out)
        self._table.setItem(row, COL_OUTPUT, out_item)

        # ── Actions ────────────────────────────────────────────────────────────
        self._table.setCellWidget(row, COL_ACTIONS, self._make_action_widget(project))

        self._table.setRowHeight(row, 44)

    def _make_action_widget(self, project: Project) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(4)

        can_queue = project.status in (
            ProjectStatus.VALID, ProjectStatus.FAILED, ProjectStatus.CANCELLED
        )

        btn_q = QPushButton("Queue")
        btn_q.setObjectName("primary" if can_queue else "")
        btn_q.setFixedHeight(28)
        btn_q.setFixedWidth(60)
        btn_q.setEnabled(can_queue)
        btn_q.clicked.connect(lambda _, pid=project.id: self.queue_project.emit(pid))

        btn_e = QPushButton("Edit")
        btn_e.setFixedHeight(28)
        btn_e.setFixedWidth(46)
        btn_e.clicked.connect(lambda _, pid=project.id: self.edit_project.emit(pid))

        btn_f = QPushButton("Folder")
        btn_f.setFixedHeight(28)
        btn_f.setFixedWidth(52)
        btn_f.setToolTip("Open project folder")
        btn_f.clicked.connect(lambda _, pid=project.id: self.open_folder.emit(pid))

        lay.addWidget(btn_q)
        lay.addWidget(btn_e)
        lay.addWidget(btn_f)
        return w

    def _update_row(self, project: Project):
        """Update an existing row in-place without a full rebuild."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_NAME)
            if item and item.data(Qt.UserRole) == project.id:
                self._populate_row(row, project)
                return
        # Not in table yet — add it
        self._append_row(project)
        self._drop_hint.setVisible(False)

    def _on_filter_changed(self):
        self._rebuild_table()

    def _on_select_all(self, state):
        """Toggle all visible checkboxes. Must use _find_checkbox() — not direct call."""
        for row in range(self._table.rowCount()):
            cb = _find_checkbox(self._table.cellWidget(row, COL_CHECK))
            if cb:
                cb.setChecked(state == Qt.Checked)

    def _queue_selected(self):
        ids = self.get_selected_project_ids()
        if ids:
            self.queue_selected.emit(ids)

    def _remove_selected(self):
        ids = self.get_selected_project_ids()
        for pid in ids:
            self.remove_project.emit(pid)

    def _on_double_click(self, row: int, col: int):
        item = self._table.item(row, COL_NAME)
        if item:
            self.project_selected.emit(item.data(Qt.UserRole))

    def _on_selection_changed(self):
        row = self._table.currentRow()
        item = self._table.item(row, COL_NAME)
        if item:
            self.project_selected.emit(item.data(Qt.UserRole))

    def _apply_batch_preset(self):
        sel_ids = self.get_selected_project_ids()
        pr_name = self._batch_preset_combo.currentText().strip()
        if sel_ids and pr_name:
            self.batch_preset_applied.emit(sel_ids, pr_name)

    def _handle_context_preset(self, pid: str, preset_name: str):
        sel_ids = self.get_selected_project_ids()
        if pid in sel_ids and len(sel_ids) > 1:
            self.batch_preset_applied.emit(sel_ids, preset_name)
        else:
            self.preset_changed.emit(pid, preset_name)

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._table.item(row, COL_NAME)
        if not item:
            return
        pid = item.data(Qt.UserRole)
        project = self._projects.get(pid)
        if not project:
            return

        menu = QMenu(self)
        can_queue = project.status in (
            ProjectStatus.VALID, ProjectStatus.FAILED, ProjectStatus.CANCELLED
        )
        if can_queue:
            menu.addAction("Queue for Rendering").triggered.connect(
                lambda: self.queue_project.emit(pid))

        # Preset submenu
        curr_p = project.preset_name or "Default"
        preset_menu = menu.addMenu(f"Apply Preset (Current: {curr_p})")
        preset_list = list(self._available_presets) if self._available_presets else ["Default"]
        if curr_p not in preset_list:
            preset_list.insert(0, curr_p)
        for pr_name in preset_list:
            preset_menu.addAction(pr_name).triggered.connect(
                lambda checked=False, p=pr_name, id_=pid: self._handle_context_preset(id_, p)
            )

        menu.addAction("⚡ Force Align Audio & Script").triggered.connect(
            lambda: self.force_align_requested.emit(pid))
        menu.addSeparator()
        menu.addAction("Edit Settings").triggered.connect(
            lambda: self.edit_project.emit(pid))
        menu.addAction("Open Folder").triggered.connect(
            lambda: self.open_folder.emit(pid))
        menu.addSeparator()
        menu.addAction("Remove from List").triggered.connect(
            lambda: self.remove_project.emit(pid))
        menu.exec_(self._table.viewport().mapToGlobal(pos))

    # ── Drag & Drop ────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_hint.setStyleSheet(
                f"color: {COLORS['accent']}; font-size: 14px; "
                f"border: 2px dashed {COLORS['accent']}; border-radius: 8px; padding: 30px;"
            )

    def dragLeaveEvent(self, event):
        self._drop_hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 14px; "
            f"border: 2px dashed {COLORS['border']}; border-radius: 8px; padding: 30px;"
        )

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.folders_dropped.emit(paths)
        self.dragLeaveEvent(event)
