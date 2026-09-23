"""
Preset manager dialog: full CRUD for render profiles.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
    QFileDialog, QFrame, QSplitter, QFormLayout, QWidget,
    QScrollArea
)
from PySide6.QtCore import Qt, Signal

from app.core.project import RenderProfile
from app.storage.settings_manager import SettingsManager
from app.gui.theme import COLORS


class PresetManagerDialog(QDialog):
    """Manage all render presets: view details, create, rename, delete, import/export."""

    preset_applied = Signal(str)   # preset_name → caller can apply to current project

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Preset Manager")
        self.setMinimumSize(700, 480)
        self._setup_ui()
        self._load_presets()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Render Presets")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        # Main splitter: list on left, details on right
        splitter = QSplitter(Qt.Horizontal)

        # Left: list + buttons
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection)
        left_layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_new = QPushButton("＋ New")
        btn_new.clicked.connect(self._new_preset)
        btn_dup = QPushButton("⧉ Duplicate")
        btn_dup.clicked.connect(self._duplicate_preset)
        btn_del = QPushButton("🗑")
        btn_del.setObjectName("danger")
        btn_del.setFixedWidth(32)
        btn_del.clicked.connect(self._delete_preset)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_dup)
        btn_row.addStretch()
        btn_row.addWidget(btn_del)
        left_layout.addLayout(btn_row)

        # Import / Export
        io_row = QHBoxLayout()
        btn_import = QPushButton("Import...")
        btn_import.clicked.connect(self._import_presets)
        btn_export = QPushButton("Export...")
        btn_export.clicked.connect(self._export_presets)
        io_row.addWidget(btn_import)
        io_row.addWidget(btn_export)
        left_layout.addLayout(io_row)

        splitter.addWidget(left)

        # Right: details
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QFrame.NoFrame)

        self._detail_widget = QWidget()
        self._detail_layout = QFormLayout(self._detail_widget)
        self._detail_layout.setSpacing(8)
        right.setWidget(self._detail_widget)
        splitter.addWidget(right)

        splitter.setSizes([220, 460])
        layout.addWidget(splitter, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        self._apply_btn = QPushButton("Apply to Current Project")
        self._apply_btn.setObjectName("primary")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_preset)
        self._rename_btn = QPushButton("Rename...")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._rename_preset)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(self._rename_btn)
        footer.addWidget(self._apply_btn)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _load_presets(self):
        self._list.clear()
        for name in self.settings.list_presets():
            item = QListWidgetItem(name)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_selection(self, current, previous):
        enabled = current is not None
        self._apply_btn.setEnabled(enabled)
        self._rename_btn.setEnabled(enabled)
        if not current:
            self._clear_details()
            return
        name = current.text()
        profile = self.settings.get_preset(name)
        if profile:
            self._show_details(name, profile)

    def _show_details(self, name: str, profile: RenderProfile):
        # Clear existing
        while self._detail_layout.rowCount():
            self._detail_layout.removeRow(0)

        def row(label, value, color=None):
            lbl = QLabel(str(value))
            if color:
                lbl.setStyleSheet(f"color: {color};")
            self._detail_layout.addRow(QLabel(label), lbl)

        row("Name:", name)
        row("Resolution:", f"{profile.width} × {profile.height}")
        row("FPS:", str(profile.fps))
        row("Video Codec:", profile.video_codec)
        row("CRF:", str(profile.crf))
        row("Bitrate:", profile.video_bitrate)
        row("Encoding Preset:", profile.preset_name)
        row("Transition:", profile.transition_type.value)
        row("Trans. Duration:", f"{profile.transition_duration}s")
        row("Motion:", profile.motion_type.value)
        row("Motion Intensity:", f"{profile.motion_intensity:.1f}")
        row("Fit Mode:", profile.fit_mode.value)
        row("Subtitle Mode:", profile.subtitle_mode.value)
        row("Subtitle Font:", profile.subtitle_font)
        row("Font Size:", str(profile.subtitle_font_size))
        row("Normalize Audio:", "Yes" if profile.normalize_audio else "No")
        row("Audio Fade In:", f"{profile.audio_fade_in}s")
        row("Audio Fade Out:", f"{profile.audio_fade_out}s")
        row("Watermark:", "Enabled" if profile.watermark_enabled else "Off")
        row("Intro:", "Enabled" if profile.intro_enabled else "Off")
        row("Outro:", "Enabled" if profile.outro_enabled else "Off")

    def _clear_details(self):
        while self._detail_layout.rowCount():
            self._detail_layout.removeRow(0)

    def _new_preset(self):
        name, ok = QInputDialog.getText(self, "New Preset", "Preset name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.settings.list_presets():
            QMessageBox.warning(self, "Duplicate Name", f"A preset named '{name}' already exists.")
            return
        profile = self.settings.get_default_profile()
        self.settings.save_preset(name, profile)
        self._load_presets()
        # Select the new one
        items = self._list.findItems(name, Qt.MatchExactly)
        if items:
            self._list.setCurrentItem(items[0])

    def _duplicate_preset(self):
        current = self._list.currentItem()
        if not current:
            return
        orig_name = current.text()
        new_name, ok = QInputDialog.getText(
            self, "Duplicate Preset", "New name:", text=f"{orig_name} (copy)"
        )
        if not ok or not new_name.strip():
            return
        profile = self.settings.get_preset(orig_name)
        if profile:
            self.settings.save_preset(new_name.strip(), profile)
            self._load_presets()

    def _delete_preset(self):
        current = self._list.currentItem()
        if not current:
            return
        name = current.text()
        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.settings.delete_preset(name)
            self._load_presets()

    def _rename_preset(self):
        current = self._list.currentItem()
        if not current:
            return
        old_name = current.text()
        new_name, ok = QInputDialog.getText(
            self, "Rename Preset", "New name:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        if not self.settings.rename_preset(old_name, new_name.strip()):
            QMessageBox.warning(self, "Error", "Could not rename. Name may already exist.")
            return
        self._load_presets()

    def _apply_preset(self):
        current = self._list.currentItem()
        if current:
            self.preset_applied.emit(current.text())

    def _import_presets(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Presets", "", "JSON Files (*.json)"
        )
        if not path:
            return
        from pathlib import Path
        count = self.settings.import_presets(Path(path), overwrite=False)
        QMessageBox.information(self, "Import", f"Imported {count} preset(s)")
        self._load_presets()

    def _export_presets(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Presets", "videoforge_presets.json", "JSON Files (*.json)"
        )
        if not path:
            return
        from pathlib import Path
        ok = self.settings.export_presets(Path(path))
        if ok:
            QMessageBox.information(self, "Export", f"Presets exported to:\n{path}")
        else:
            QMessageBox.warning(self, "Export Failed", "Could not export presets.")
