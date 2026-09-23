"""
Project detail dialog: shows project metadata and allows per-project settings override.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit, QFrame,
    QScrollArea, QFileDialog, QMessageBox, QGroupBox, QListWidget,
    QListWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage

from app.core.project import (
    Project, RenderProfile, ProjectStatus,
    TransitionType, MotionType, FitMode, SubtitleMode
)
from app.gui.theme import COLORS, STATUS_COLORS
from app.gui.widgets.common import StatusBadge, HealthBar, Divider


class ProjectDetailDialog(QDialog):
    project_updated = Signal(object)   # Project

    def __init__(self, project: Project, presets: dict = None, parent=None):
        super().__init__(parent)
        self.project = project
        self.presets = presets or {}
        self.setWindowTitle(f"Project Settings — {project.name}")
        self.setMinimumSize(760, 640)
        self.setModal(True)
        self._setup_ui()
        self._load_values()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel(self.project.name)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        badge = StatusBadge(self.project.status.value)
        health = HealthBar(self.project.health_score)
        health_lbl = QLabel(f"Health: {self.project.health_score}%")
        health_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        header.addWidget(title)
        header.addWidget(badge)
        header.addWidget(health)
        header.addWidget(health_lbl)
        header.addStretch()
        layout.addLayout(header)

        # Folder
        folder_lbl = QLabel(f"📁  {self.project.folder}")
        folder_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        layout.addWidget(folder_lbl)

        # Tabs
        tabs = QTabWidget()

        tabs.addTab(self._make_overview_tab(), "Overview")
        tabs.addTab(self._make_output_tab(), "Output")
        tabs.addTab(self._make_subtitle_tab(), "Subtitles")
        tabs.addTab(self._make_images_tab(), "Images")
        tabs.addTab(self._make_validation_tab(), "Validation")

        layout.addWidget(tabs, 1)

        # Footer buttons
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        queue_btn = QPushButton("Save & Queue")
        queue_btn.setObjectName("success")
        queue_btn.clicked.connect(self._save_and_queue)
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        footer.addWidget(queue_btn)
        layout.addLayout(footer)

    def _make_overview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Files info
        files_group = QGroupBox("Detected Files")
        files_form = QFormLayout(files_group)
        files_form.setSpacing(8)

        audio = str(self.project.audio_path.name) if self.project.audio_path else "Not found"
        transcript = str(self.project.transcript_path.name) if self.project.transcript_path else "Not found"
        images = f"{self.project.image_count} image(s)"
        duration = f"{self.project.duration_str}" if self.project.audio_duration else "Unknown"
        words = f"{self.project.transcript_word_count:,}" if self.project.transcript_word_count else "0"

        for label, value in [
            ("Audio file:", audio),
            ("Transcript:", transcript),
            ("Images:", images),
            ("Audio duration:", duration),
            ("Transcript words:", words),
        ]:
            v_lbl = QLabel(value)
            ok = "Not found" not in value and value != "0"
            v_lbl.setStyleSheet(
                f"color: {COLORS['success'] if ok else COLORS['error']};"
            )
            files_form.addRow(QLabel(label), v_lbl)

        layout.addWidget(files_group)

        # Notes
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlainText(self.project.notes)
        self._notes_edit.setFixedHeight(80)
        self._notes_edit.setPlaceholderText("Optional notes about this project...")
        notes_layout.addWidget(self._notes_edit)
        layout.addWidget(notes_group)

        layout.addStretch()
        return w

    def _make_output_tab(self) -> QWidget:
        w = QScrollArea()
        w.setWidgetResizable(True)
        container = QWidget()
        w.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Preset selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Apply Preset:"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItem("— Custom —")
        for name in self.presets:
            self._preset_combo.addItem(name)
        self._preset_combo.currentTextChanged.connect(self._apply_preset)
        preset_row.addWidget(self._preset_combo, 1)
        layout.addLayout(preset_row)

        # Output path
        output_group = QGroupBox("Output")
        output_form = QFormLayout(output_group)
        output_form.setSpacing(8)

        path_row = QHBoxLayout()
        self._output_path_edit = QLineEdit()
        self._output_path_edit.setPlaceholderText("Leave empty for auto-generated path")
        if self.project.output_path:
            self._output_path_edit.setText(str(self.project.output_path))
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_output)
        path_row.addWidget(self._output_path_edit, 1)
        path_row.addWidget(browse_btn)

        output_form.addRow("Output file:", path_row)
        layout.addWidget(output_group)

        # Video settings
        video_group = QGroupBox("Video")
        video_form = QFormLayout(video_group)
        video_form.setSpacing(8)

        # Resolution
        res_row = QHBoxLayout()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(64, 7680)
        self._width_spin.setSingleStep(2)
        self._width_spin.setValue(self.project.profile.width)
        self._height_spin = QSpinBox()
        self._height_spin.setRange(64, 4320)
        self._height_spin.setSingleStep(2)
        self._height_spin.setValue(self.project.profile.height)

        res_presets = QComboBox()
        res_presets.addItems(["1920×1080 (16:9)", "1280×720 (16:9)",
                               "1080×1920 (9:16)", "1080×1080 (1:1)",
                               "1080×1350 (4:5)", "Custom"])
        res_presets.currentTextChanged.connect(self._apply_resolution_preset)

        res_row.addWidget(self._width_spin)
        res_row.addWidget(QLabel("×"))
        res_row.addWidget(self._height_spin)
        res_row.addWidget(res_presets)
        video_form.addRow("Resolution:", res_row)

        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(15, 60)
        self._fps_spin.setValue(self.project.profile.fps)
        video_form.addRow("FPS:", self._fps_spin)

        self._codec_combo = QComboBox()
        self._codec_combo.addItems(["libx264", "libx265", "libvpx-vp9"])
        self._codec_combo.setCurrentText(self.project.profile.video_codec)
        video_form.addRow("Video Codec:", self._codec_combo)

        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51)
        self._crf_spin.setValue(self.project.profile.crf)
        self._crf_spin.setToolTip("Lower = better quality, larger file (18=high, 23=default, 28=fast)")
        video_form.addRow("CRF (Quality):", self._crf_spin)

        self._bitrate_edit = QLineEdit(self.project.profile.video_bitrate)
        self._bitrate_edit.setToolTip("e.g. 4M, 6000k")
        video_form.addRow("Max Bitrate:", self._bitrate_edit)

        self._enc_preset = QComboBox()
        self._enc_preset.addItems(["ultrafast","superfast","veryfast","faster","fast","medium","slow","slower"])
        self._enc_preset.setCurrentText(self.project.profile.preset_name)
        video_form.addRow("Encoding Speed:", self._enc_preset)

        layout.addWidget(video_group)

        # Motion & Transitions
        motion_group = QGroupBox("Motion & Transitions")
        motion_form = QFormLayout(motion_group)
        motion_form.setSpacing(8)

        self._transition_combo = QComboBox()
        for t in TransitionType:
            self._transition_combo.addItem(t.value.replace("_", " ").title(), t)
        self._transition_combo.setCurrentText(
            self.project.profile.transition_type.value.replace("_", " ").title()
        )
        motion_form.addRow("Transition:", self._transition_combo)

        self._trans_dur_spin = QDoubleSpinBox()
        self._trans_dur_spin.setRange(0.0, 3.0)
        self._trans_dur_spin.setSingleStep(0.1)
        self._trans_dur_spin.setDecimals(1)
        self._trans_dur_spin.setValue(self.project.profile.transition_duration)
        motion_form.addRow("Transition Duration (s):", self._trans_dur_spin)

        self._motion_combo = QComboBox()
        for m in MotionType:
            self._motion_combo.addItem(m.value.replace("_", " ").title(), m)
        self._motion_combo.setCurrentText(
            self.project.profile.motion_type.value.replace("_", " ").title()
        )
        motion_form.addRow("Motion Effect:", self._motion_combo)

        self._motion_intensity_spin = QDoubleSpinBox()
        self._motion_intensity_spin.setRange(0.0, 2.0)
        self._motion_intensity_spin.setSingleStep(0.1)
        self._motion_intensity_spin.setDecimals(1)
        self._motion_intensity_spin.setValue(self.project.profile.motion_intensity)
        motion_form.addRow("Motion Intensity:", self._motion_intensity_spin)

        self._fit_combo = QComboBox()
        for f in FitMode:
            self._fit_combo.addItem(f.value.replace("_", " ").title(), f)
        self._fit_combo.setCurrentText(
            self.project.profile.fit_mode.value.replace("_", " ").title()
        )
        motion_form.addRow("Image Fit Mode:", self._fit_combo)

        layout.addWidget(motion_group)

        # Audio
        audio_group = QGroupBox("Audio")
        audio_form = QFormLayout(audio_group)
        audio_form.setSpacing(8)

        self._normalize_cb = QCheckBox("Normalize audio levels")
        self._normalize_cb.setChecked(self.project.profile.normalize_audio)
        audio_form.addRow("", self._normalize_cb)

        self._fade_in_spin = QDoubleSpinBox()
        self._fade_in_spin.setRange(0, 5.0)
        self._fade_in_spin.setSingleStep(0.1)
        self._fade_in_spin.setValue(self.project.profile.audio_fade_in)
        audio_form.addRow("Fade In (s):", self._fade_in_spin)

        self._fade_out_spin = QDoubleSpinBox()
        self._fade_out_spin.setRange(0, 5.0)
        self._fade_out_spin.setSingleStep(0.1)
        self._fade_out_spin.setValue(self.project.profile.audio_fade_out)
        audio_form.addRow("Fade Out (s):", self._fade_out_spin)

        layout.addWidget(audio_group)
        layout.addStretch()
        return w

    def _make_subtitle_tab(self) -> QWidget:
        w = QScrollArea()
        w.setWidgetResizable(True)
        container = QWidget()
        w.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sub_group = QGroupBox("Subtitle Settings")
        sub_form = QFormLayout(sub_group)
        sub_form.setSpacing(8)

        self._sub_enabled_cb = QCheckBox("Enable subtitles")
        self._sub_enabled_cb.setChecked(self.project.profile.subtitle_enabled)
        sub_form.addRow("", self._sub_enabled_cb)

        self._sub_mode_combo = QComboBox()
        for sm in SubtitleMode:
            self._sub_mode_combo.addItem(sm.value.replace("_", " ").title(), sm)
        self._sub_mode_combo.setCurrentText(
            self.project.profile.subtitle_mode.value.replace("_", " ").title()
        )
        self._sub_mode_combo.setToolTip(
            "Phrase  — short natural phrases (recommended)\n"
            "Classic — full sentences\n"
            "Viral   — 2-4 words (TikTok / Shorts style)\n"
            "Word    — one word at a time\n"
            "Karaoke — moving highlight: current word lights up as it's spoken"
        )
        sub_form.addRow("Mode:", self._sub_mode_combo)

        self._sub_font_edit = QLineEdit(self.project.profile.subtitle_font)
        sub_form.addRow("Font:", self._sub_font_edit)

        self._sub_size_spin = QSpinBox()
        self._sub_size_spin.setRange(12, 200)
        self._sub_size_spin.setValue(self.project.profile.subtitle_font_size)
        sub_form.addRow("Font Size:", self._sub_size_spin)

        self._sub_bold_cb = QCheckBox("Bold")
        self._sub_bold_cb.setChecked(self.project.profile.subtitle_bold)
        sub_form.addRow("Style:", self._sub_bold_cb)

        self._sub_outline_spin = QDoubleSpinBox()
        self._sub_outline_spin.setRange(0, 10)
        self._sub_outline_spin.setSingleStep(0.5)
        self._sub_outline_spin.setValue(self.project.profile.subtitle_outline_width)
        sub_form.addRow("Outline Width:", self._sub_outline_spin)

        self._sub_margin_spin = QSpinBox()
        self._sub_margin_spin.setRange(0, 500)
        self._sub_margin_spin.setValue(self.project.profile.subtitle_margin_v)
        sub_form.addRow("Vertical Margin:", self._sub_margin_spin)

        self._sub_max_chars_spin = QSpinBox()
        self._sub_max_chars_spin.setRange(10, 200)
        self._sub_max_chars_spin.setValue(self.project.profile.subtitle_max_chars)
        sub_form.addRow("Max Chars/Line:", self._sub_max_chars_spin)

        layout.addWidget(sub_group)

        # ── Karaoke settings — always visible ────────────────────────────────
        from app.gui.dialogs.settings_dialog import ColorButton

        def _ass_to_hex(ass_color: str) -> str:
            h = ass_color.strip().lstrip("&H").rstrip("&")
            if len(h) == 8:   # AABBGGRR
                bb, gg, rr = h[2:4], h[4:6], h[6:8]
                return f"#{rr}{gg}{bb}".upper()
            if len(h) == 6:   # BBGGRR
                bb, gg, rr = h[0:2], h[2:4], h[4:6]
                return f"#{rr}{gg}{bb}".upper()
            return "#FFFF00"

        self._kara_group = QGroupBox("Karaoke — Word-by-Word Highlight")
        self._kara_group.setStyleSheet(
            f"QGroupBox {{ border: 2px solid {COLORS['accent']}; "
            f"border-radius: 6px; margin-top: 14px; padding: 12px 8px 8px 8px; "
            f"color: {COLORS['accent_text']}; font-weight: bold; font-size: 12px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; top: -8px; "
            f"padding: 0 6px; background-color: {COLORS['bg_primary']}; "
            f"color: {COLORS['accent_text']}; }}"
        )
        kf = QFormLayout(self._kara_group); kf.setSpacing(8)

        kara_cb_row = QHBoxLayout()
        self._kara_enable_cb = QCheckBox("Enable karaoke for this project")
        self._kara_enable_cb.setToolTip(
            "Highlights each word in turn as it is spoken.\n"
            "Overrides the global subtitle mode for this project."
        )
        self._kara_enable_cb.setStyleSheet(
            f"font-weight: 600; color: {COLORS['text_primary']};"
        )
        is_karaoke_now = self.project.profile.subtitle_mode.value == "karaoke"
        self._kara_enable_cb.setChecked(is_karaoke_now)
        kara_cb_row.addWidget(self._kara_enable_cb)
        kara_cb_row.addStretch()
        kf.addRow("", kara_cb_row)

        self._kara_color_btn = ColorButton(
            _ass_to_hex(self.project.profile.subtitle_karaoke_color)
        )
        self._kara_color_btn.setToolTip(
            "The colour that highlights the word currently being spoken.\n"
            "Yellow (#FFFF00) is the most legible on dark backgrounds."
        )
        kf.addRow("Highlight colour:", self._kara_color_btn)

        kara_tip = QLabel(
            "Each word lights up in this colour as it is spoken.\n"
            "For accurate word timing, use Whisper model 'small' or larger."
        )
        kara_tip.setWordWrap(True)
        kara_tip.setStyleSheet(
            f"color:{COLORS['text_secondary']};font-size:11px;"
            f"background:{COLORS['bg_card']};border-radius:4px;padding:6px;"
        )
        kf.addRow("", kara_tip)

        layout.addWidget(self._kara_group)

        # Sync karaoke checkbox ↔ mode combo
        def _on_kara_cb_changed(state):
            # Use isChecked() — avoids unreliable Qt.Checked enum vs int comparison
            self._sub_mode_combo.blockSignals(True)
            if self._kara_enable_cb.isChecked():
                self._sub_mode_combo.setCurrentText("Karaoke")
            else:
                if self._sub_mode_combo.currentText().lower() == "karaoke":
                    self._sub_mode_combo.setCurrentText("Phrase")
            self._sub_mode_combo.blockSignals(False)

        def _on_mode_changed(text):
            is_karaoke = text.lower().replace(" ", "_") == "karaoke"
            self._kara_enable_cb.blockSignals(True)
            self._kara_enable_cb.setChecked(is_karaoke)
            self._kara_enable_cb.blockSignals(False)

        self._kara_enable_cb.stateChanged.connect(_on_kara_cb_changed)
        self._sub_mode_combo.currentTextChanged.connect(_on_mode_changed)

        # Transcript preview
        if self.project.transcript_text:
            prev_group = QGroupBox("Transcript Preview (first 500 chars)")
            prev_layout = QVBoxLayout(prev_group)
            prev_text = QTextEdit()
            prev_text.setReadOnly(True)
            prev_text.setPlainText(self.project.transcript_text[:500])
            prev_text.setFixedHeight(100)
            prev_layout.addWidget(prev_text)
            layout.addWidget(prev_group)

        layout.addStretch()
        return w

    def _make_images_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        info = QLabel(f"{self.project.image_count} image(s) detected")
        info.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(info)

        img_list = QListWidget()
        img_list.setDragDropMode(QAbstractItemView.InternalMove)
        img_list.setToolTip("Drag to reorder images")
        for img in self.project.image_paths:
            item = QListWidgetItem(f"🖼  {img.name}")
            item.setToolTip(str(img))
            img_list.addItem(item)
        self._img_list = img_list
        layout.addWidget(img_list, 1)

        hint = QLabel("💡 Drag to reorder. Order affects slide sequence in output video.")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        layout.addWidget(hint)
        return w

    def _make_validation_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        v = self.project.validation
        status = "✅ All checks passed" if v.valid else f"❌ {len(v.issues)} issue(s) found"
        status_lbl = QLabel(status)
        status_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; "
            f"color: {COLORS['success'] if v.valid else COLORS['error']};"
        )
        layout.addWidget(status_lbl)

        if v.issues:
            issues_group = QGroupBox("Issues (must fix to render)")
            iss_layout = QVBoxLayout(issues_group)
            for issue in v.issues:
                lbl = QLabel(f"  ❌  {issue}")
                lbl.setStyleSheet(f"color: {COLORS['error']};")
                lbl.setWordWrap(True)
                iss_layout.addWidget(lbl)
            layout.addWidget(issues_group)

        if v.warnings:
            warn_group = QGroupBox("Warnings")
            warn_layout = QVBoxLayout(warn_group)
            for warn in v.warnings:
                lbl = QLabel(f"  ⚠️  {warn}")
                lbl.setStyleSheet(f"color: {COLORS['warning']};")
                lbl.setWordWrap(True)
                warn_layout.addWidget(lbl)
            layout.addWidget(warn_group)

        if v.suggestions:
            sug_group = QGroupBox("Suggestions")
            sug_layout = QVBoxLayout(sug_group)
            for sug in v.suggestions:
                lbl = QLabel(f"  💡  {sug}")
                lbl.setStyleSheet(f"color: {COLORS['info']};")
                lbl.setWordWrap(True)
                sug_layout.addWidget(lbl)
            layout.addWidget(sug_group)

        layout.addStretch()
        return w

    # ── Actions ───────────────────────────────────────────────────────────────

    def _load_values(self):
        pass  # Values are set during widget construction

    def _apply_preset(self, preset_name: str):
        if preset_name.startswith("—"):
            return
        profile = self.presets.get(preset_name)
        if not profile:
            return
        from app.core.project import RenderProfile
        p = RenderProfile.from_dict(profile)
        self._width_spin.setValue(p.width)
        self._height_spin.setValue(p.height)
        self._fps_spin.setValue(p.fps)
        self._codec_combo.setCurrentText(p.video_codec)
        self._crf_spin.setValue(p.crf)
        self._bitrate_edit.setText(p.video_bitrate)
        self._enc_preset.setCurrentText(p.preset_name)
        self._sub_mode_combo.setCurrentText(
            p.subtitle_mode.value.replace("_", " ").title()
        )
        self._sub_size_spin.setValue(p.subtitle_font_size)
        self._sub_margin_spin.setValue(p.subtitle_margin_v)

    def _apply_resolution_preset(self, text: str):
        presets = {
            "1920×1080 (16:9)": (1920, 1080),
            "1280×720 (16:9)": (1280, 720),
            "1080×1920 (9:16)": (1080, 1920),
            "1080×1080 (1:1)": (1080, 1080),
            "1080×1350 (4:5)": (1080, 1350),
        }
        if text in presets:
            w, h = presets[text]
            self._width_spin.setValue(w)
            self._height_spin.setValue(h)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Set Output Path", "", "MP4 Video (*.mp4)"
        )
        if path:
            self._output_path_edit.setText(path)

    def _collect_values(self) -> Project:
        """Read all form values back into the project."""
        p = self.project
        p.notes = self._notes_edit.toPlainText()

        # Output path
        out_text = self._output_path_edit.text().strip()
        if out_text:
            from pathlib import Path
            p.output_path = Path(out_text)

        # Profile
        pr = p.profile
        pr.width = self._width_spin.value()
        pr.height = self._height_spin.value()
        pr.fps = self._fps_spin.value()
        pr.video_codec = self._codec_combo.currentText()
        pr.crf = self._crf_spin.value()
        pr.video_bitrate = self._bitrate_edit.text().strip()
        pr.preset_name = self._enc_preset.currentText()

        trans_text = self._transition_combo.currentText().lower().replace(" ", "")
        for t in TransitionType:
            if t.value.replace("_", "").lower() == trans_text:
                pr.transition_type = t
                break
        pr.transition_duration = self._trans_dur_spin.value()

        motion_text = self._motion_combo.currentText().lower().replace(" ", "_")
        for m in MotionType:
            if m.value == motion_text:
                pr.motion_type = m
                break
        pr.motion_intensity = self._motion_intensity_spin.value()

        fit_text = self._fit_combo.currentText().lower().replace(" ", "_")
        for f in FitMode:
            if f.value == fit_text:
                pr.fit_mode = f
                break

        pr.normalize_audio = self._normalize_cb.isChecked()
        pr.audio_fade_in = self._fade_in_spin.value()
        pr.audio_fade_out = self._fade_out_spin.value()

        pr.subtitle_enabled = self._sub_enabled_cb.isChecked()
        sub_mode_text = self._sub_mode_combo.currentText().lower().replace(" ", "_")
        matched_mode = None
        for sm in SubtitleMode:
            if sm.value == sub_mode_text:
                matched_mode = sm
                break
        if matched_mode is not None:
            pr.subtitle_mode = matched_mode
        else:
            pr.subtitle_mode = SubtitleMode.PHRASE
        pr.subtitle_font = self._sub_font_edit.text().strip() or "Arial"
        pr.subtitle_font_size = self._sub_size_spin.value()
        pr.subtitle_bold = self._sub_bold_cb.isChecked()
        pr.subtitle_outline_width = self._sub_outline_spin.value()
        pr.subtitle_margin_v = self._sub_margin_spin.value()
        pr.subtitle_max_chars = self._sub_max_chars_spin.value()

        # Karaoke highlight colour
        def _hex_to_ass(h: str) -> str:
            h = h.lstrip("#")
            if len(h) == 6:
                r, g, b = h[0:2], h[2:4], h[4:6]
                return f"&H00{b}{g}{r}".upper()
            return "&H0000FFFF"
        pr.subtitle_karaoke_color = _hex_to_ass(self._kara_color_btn.get_color())

        # Image order from list widget
        new_order = []
        for i in range(self._img_list.count()):
            item = self._img_list.item(i)
            name = item.text().replace("🖼  ", "")
            for img in p.image_paths:
                if img.name == name:
                    new_order.append(img)
                    break
        if len(new_order) == len(p.image_paths):
            p.image_paths = new_order

        return p

    def _save(self):
        self._collect_values()
        self.project_updated.emit(self.project)
        self.accept()

    def _save_and_queue(self):
        self._collect_values()
        self.project_updated.emit(self.project)
        self.project._queue_after_save = True
        self.accept()
