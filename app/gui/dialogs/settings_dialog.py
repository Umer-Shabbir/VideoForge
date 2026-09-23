"""
Settings dialog — all application-level settings.
Tabs: General | FFmpeg & Performance | Output & Files | Subtitles | Advanced
"""

import os
import psutil
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox,
    QFileDialog, QMessageBox, QScrollArea, QColorDialog, QFrame, QSlider
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from app.storage.settings_manager import SettingsManager
from app.gui.theme import COLORS


# ── Colour swatch button ──────────────────────────────────────────────────────

class ColorButton(QPushButton):
    """A button that displays a color and opens a color picker when clicked."""
    color_changed = Signal(str)  # emits hex string e.g. "#FFFFFF"

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(44, 28)
        self.clicked.connect(self._pick)
        self._refresh()

    def set_color(self, hex_color: str):
        self._color = hex_color
        self._refresh()

    def get_color(self) -> str:
        return self._color

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Pick Color")
        if c.isValid():
            self._color = c.name().upper()
            self._refresh()
            self.color_changed.emit(self._color)

    def _refresh(self):
        r, g, b = int(self._color[1:3], 16), int(self._color[3:5], 16), int(self._color[5:7], 16)
        luminance = (0.299*r + 0.587*g + 0.114*b) / 255
        text_color = "#000000" if luminance > 0.5 else "#FFFFFF"
        self.setStyleSheet(
            f"background-color:{self._color};color:{text_color};"
            f"border:2px solid #555;border-radius:4px;font-size:11px;font-weight:bold;"
        )
        self.setText(self._color)


# ── Main dialog ───────────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    settings_changed    = Signal()
    ffmpeg_path_changed = Signal(str)

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings — VideoForge")
        self.setMinimumSize(700, 640)
        self.setModal(True)
        self._setup_ui()
        self._load_values()

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Settings")
        title.setStyleSheet("font-size:18px;font-weight:700;")
        lay.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._tab_general(),     "General")
        self._tabs.addTab(self._tab_perf(),        "Performance")
        self._tabs.addTab(self._tab_files(),       "Files & Naming")
        self._tabs.addTab(self._tab_subtitles(),   "Subtitles")
        self._tabs.addTab(self._tab_advanced(),    "Advanced")
        lay.addWidget(self._tabs, 1)

        # Footer buttons
        foot = QHBoxLayout()
        foot.addStretch()
        btn_reset = QPushButton("Reset All")
        btn_reset.setObjectName("danger")
        btn_reset.clicked.connect(self._reset)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save")
        btn_save.setObjectName("primary")
        btn_save.setFixedWidth(100)
        btn_save.clicked.connect(self._save)
        for b in [btn_reset, btn_cancel, btn_save]:
            b.setFixedHeight(32)
        foot.addWidget(btn_reset)
        foot.addWidget(btn_cancel)
        foot.addWidget(btn_save)
        lay.addLayout(foot)

    # ─────────────────────────────────────────────────────────────────────────
    # Tab: General
    # ─────────────────────────────────────────────────────────────────────────

    def _tab_general(self) -> QWidget:
        w, lay = self._scroll_tab()

        scan = QGroupBox("Scanning")
        f = QFormLayout(scan); f.setSpacing(8)
        self._recursive_cb   = QCheckBox("Scan subfolders recursively")
        self._max_depth_spin = QSpinBox(); self._max_depth_spin.setRange(1, 20)
        self._max_depth_spin.setFixedWidth(70)
        f.addRow("", self._recursive_cb)
        f.addRow("Max folder depth:", self._max_depth_spin)
        lay.addWidget(scan)

        behaviour = QGroupBox("Behaviour")
        f2 = QFormLayout(behaviour); f2.setSpacing(8)
        self._auto_validate_cb  = QCheckBox("Validate projects when imported")
        self._auto_queue_cb     = QCheckBox("Auto-queue valid projects after scan")
        self._skip_completed_cb = QCheckBox("Skip projects that already have an output file")
        self._overwrite_cb      = QCheckBox("Overwrite existing output files")
        self._reopen_cb         = QCheckBox("Restore last session on startup")
        self._auto_open_cb      = QCheckBox("Open output folder after each render")
        for cb in [self._auto_validate_cb, self._auto_queue_cb, self._skip_completed_cb,
                   self._overwrite_cb, self._reopen_cb, self._auto_open_cb]:
            f2.addRow("", cb)
        lay.addWidget(behaviour)
        lay.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────────────────
    # Tab: Performance
    # ─────────────────────────────────────────────────────────────────────────

    def _tab_perf(self) -> QWidget:
        w, lay = self._scroll_tab()

        # System info
        cpu_count = psutil.cpu_count(logical=True) or 4
        ram_gb    = psutil.virtual_memory().total // (1024**3)

        info_lbl = QLabel(
            f"System: {psutil.cpu_count(logical=False)} physical cores "
            f"({cpu_count} logical), {ram_gb} GB RAM"
        )
        info_lbl.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:12px;padding:4px;")
        lay.addWidget(info_lbl)

        ffmpeg_g = QGroupBox("FFmpeg & Encoding")
        f = QFormLayout(ffmpeg_g); f.setSpacing(10)

        self._threads_spin = QSpinBox()
        self._threads_spin.setRange(0, cpu_count)
        self._threads_spin.setFixedWidth(80)
        self._threads_spin.setSpecialValueText("Auto (all cores)")
        self._threads_spin.setToolTip(
            "0 = FFmpeg uses all CPU cores (fastest).\n"
            f"Your CPU has {cpu_count} logical cores."
        )
        f.addRow("FFmpeg threads  (0=auto):", self._threads_spin)

        self._concurrent_spin = QSpinBox()
        self._concurrent_spin.setRange(1, max(4, psutil.cpu_count(logical=False) // 2))
        self._concurrent_spin.setFixedWidth(80)
        self._concurrent_spin.setToolTip(
            "Number of render jobs to run at the same time.\n"
            "1 is safest. Use 2+ only on machines with many cores."
        )
        f.addRow("Parallel render jobs:", self._concurrent_spin)

        self._gpu_cb = QCheckBox("Use GPU for Whisper speech recognition (requires CUDA)")
        f.addRow("", self._gpu_cb)

        lay.addWidget(ffmpeg_g)

        whisper_g = QGroupBox("Whisper Model")
        fw = QFormLayout(whisper_g); fw.setSpacing(8)

        self._whisper_device_combo = QComboBox()
        self._whisper_device_combo.addItems(["cpu", "cuda"])
        self._whisper_device_combo.setFixedWidth(100)
        fw.addRow("Device:", self._whisper_device_combo)

        self._whisper_model_combo = QComboBox()
        self._whisper_model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self._whisper_model_combo.setFixedWidth(120)
        self._whisper_model_combo.setToolTip(
            "tiny: fastest, least accurate\n"
            "small: good balance (~250MB)\n"
            "medium: more accurate (~1.5GB)\n"
            "large: most accurate (~3GB)"
        )
        fw.addRow("Model:", self._whisper_model_combo)

        self._whisper_lang_edit = QLineEdit()
        self._whisper_lang_edit.setPlaceholderText("auto — detect automatically")
        self._whisper_lang_edit.setFixedWidth(200)
        self._whisper_lang_edit.setToolTip("Leave blank for auto. Or use ISO code: en, es, fr, de, zh…")
        fw.addRow("Language:", self._whisper_lang_edit)

        lay.addWidget(whisper_g)

        note = self._info_label(
            "💡 For fastest rendering: set FFmpeg threads to 0 (auto) and parallel jobs to 1.\n"
            "FFmpeg will use all your CPU cores on a single project, which is faster than\n"
            "splitting cores between multiple parallel jobs."
        )
        lay.addWidget(note)
        lay.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────────────────
    # Tab: Files & Naming
    # ─────────────────────────────────────────────────────────────────────────

    def _tab_files(self) -> QWidget:
        w, lay = self._scroll_tab()

        out_g = QGroupBox("Output Location & Naming")
        f = QFormLayout(out_g); f.setSpacing(10)

        out_row = QHBoxLayout()
        self._output_folder_edit = QLineEdit()
        self._output_folder_edit.setPlaceholderText("Same folder as project (default)")
        browse_out = QPushButton("Browse…")
        browse_out.setFixedWidth(80)
        browse_out.setFixedHeight(30)
        browse_out.clicked.connect(self._browse_output_folder)
        out_row.addWidget(self._output_folder_edit, 1)
        out_row.addWidget(browse_out)
        f.addRow("Default output folder:", out_row)

        self._name_template_edit = QLineEdit()
        self._name_template_edit.setPlaceholderText("{project_name}_{date}")
        self._name_template_edit.setToolTip("Variables: {project_name}  {date}  {folder}")
        f.addRow("Filename template:", self._name_template_edit)
        lay.addWidget(out_g)

        pref_g = QGroupBox("Preferred File Names  (when a project folder has multiple audio / script files)")
        pf = QFormLayout(pref_g); pf.setSpacing(10)

        self._pref_audio_edit = QLineEdit()
        self._pref_audio_edit.setPlaceholderText("e.g.  narration.mp3  (exact filename, leave blank for auto)")
        pf.addRow("Preferred audio file:", self._pref_audio_edit)

        self._pref_audio_kw_edit = QLineEdit()
        self._pref_audio_kw_edit.setPlaceholderText("narration,voiceover,audio,voice")
        self._pref_audio_kw_edit.setToolTip(
            "Comma-separated keywords. If a project has multiple audio files,\n"
            "the one whose name contains the first matching keyword wins."
        )
        pf.addRow("Audio keyword priority:", self._pref_audio_kw_edit)

        self._pref_script_edit = QLineEdit()
        self._pref_script_edit.setPlaceholderText("e.g.  script.txt  (exact filename, leave blank for auto)")
        pf.addRow("Preferred script file:", self._pref_script_edit)

        self._pref_script_kw_edit = QLineEdit()
        self._pref_script_kw_edit.setPlaceholderText("script,transcript,narration,text")
        pf.addRow("Script keyword priority:", self._pref_script_kw_edit)

        lay.addWidget(pref_g)

        lay.addWidget(self._info_label(
            "💡 Example: If your project folders always contain both 'audio.mp3' and 'music.mp3',\n"
            "set the keyword priority to 'audio' so VideoForge always picks the narration.\n\n"
            "Filename template variables:  {project_name}  {date} (YYYYMMDD)  {folder} (parent folder)"
        ))
        lay.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────────────────
    # Tab: Subtitles
    # ─────────────────────────────────────────────────────────────────────────

    def _tab_subtitles(self) -> QWidget:
        w, lay = self._scroll_tab()

        style_g = QGroupBox("Subtitle Style  (default for all projects)")
        f = QFormLayout(style_g); f.setSpacing(10)

        # Font
        self._sub_font_edit = QLineEdit()
        self._sub_font_edit.setFixedWidth(200)
        self._sub_font_edit.setPlaceholderText("Arial")
        self._sub_font_edit.setToolTip("Any font installed on Windows. E.g. Arial, Impact, Segoe UI")
        f.addRow("Font:", self._sub_font_edit)

        # Size
        self._sub_size_spin = QSpinBox()
        self._sub_size_spin.setRange(24, 150)
        self._sub_size_spin.setSuffix(" px")
        self._sub_size_spin.setFixedWidth(90)
        f.addRow("Font size:", self._sub_size_spin)

        # Bold
        self._sub_bold_cb = QCheckBox("Bold text")
        f.addRow("", self._sub_bold_cb)

        # Text colour
        text_row = QHBoxLayout()
        self._sub_text_color_btn  = ColorButton("#FFFFFF")
        self._sub_outline_color_btn = ColorButton("#000000")
        text_row.addWidget(QLabel("Text:"))
        text_row.addWidget(self._sub_text_color_btn)
        text_row.addSpacing(16)
        text_row.addWidget(QLabel("Outline:"))
        text_row.addWidget(self._sub_outline_color_btn)
        text_row.addStretch()
        f.addRow("Colors:", text_row)

        # Outline width
        self._sub_outline_spin = QDoubleSpinBox()
        self._sub_outline_spin.setRange(0.0, 8.0)
        self._sub_outline_spin.setSingleStep(0.5)
        self._sub_outline_spin.setSuffix(" px")
        self._sub_outline_spin.setFixedWidth(90)
        self._sub_outline_spin.setToolTip("3.0 is the recommended minimum for readability")
        f.addRow("Outline width:", self._sub_outline_spin)

        # Shadow
        self._sub_shadow_spin = QDoubleSpinBox()
        self._sub_shadow_spin.setRange(0.0, 6.0)
        self._sub_shadow_spin.setSingleStep(0.5)
        self._sub_shadow_spin.setSuffix(" px")
        self._sub_shadow_spin.setFixedWidth(90)
        f.addRow("Shadow depth:", self._sub_shadow_spin)

        # Vertical margin
        self._sub_margin_spin = QSpinBox()
        self._sub_margin_spin.setRange(0, 500)
        self._sub_margin_spin.setSuffix(" px from bottom")
        self._sub_margin_spin.setFixedWidth(150)
        self._sub_margin_spin.setToolTip(
            "Distance from the bottom edge.\n"
            "Increase this for Reels/Shorts so subs don't cover faces."
        )
        f.addRow("Vertical position:", self._sub_margin_spin)

        # Mode — Title-case items so they look polished; save/load as lowercase
        self._sub_mode_combo = QComboBox()
        self._sub_mode_combo.addItems(["Phrase", "Classic", "Viral", "Word", "Karaoke"])
        self._sub_mode_combo.setFixedWidth(160)
        self._sub_mode_combo.setToolTip(
            "Phrase  — short natural phrases (recommended)\n"
            "Classic — full sentences\n"
            "Viral   — 2-4 words (TikTok / Shorts style)\n"
            "Word    — one word at a time\n"
            "Karaoke — moving highlight: current word lights up as it's spoken"
        )
        f.addRow("Subtitle mode:", self._sub_mode_combo)
        self._sub_mode_combo.currentTextChanged.connect(self._on_mode_changed)

        # Max chars per line
        self._sub_maxchars_spin = QSpinBox()
        self._sub_maxchars_spin.setRange(10, 120)
        self._sub_maxchars_spin.setSuffix(" chars")
        self._sub_maxchars_spin.setFixedWidth(110)
        f.addRow("Max chars per line:", self._sub_maxchars_spin)

        lay.addWidget(style_g)

        # ── Karaoke settings — always visible ─────────────────────────────────
        self._kara_group = QGroupBox("Karaoke — Word-by-Word Highlight")
        self._kara_group.setStyleSheet(
            f"QGroupBox {{ border: 2px solid {COLORS['accent']}; "
            f"border-radius: 6px; margin-top: 14px; padding: 12px 8px 8px 8px; "
            f"color: {COLORS['accent_text']}; font-weight: bold; font-size: 12px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; top: -8px; "
            f"padding: 0 6px; background-color: {COLORS['bg_primary']}; "
            f"color: {COLORS['accent_text']}; }}"
        )
        kf = QFormLayout(self._kara_group); kf.setSpacing(10)

        kara_enable_row = QHBoxLayout()
        self._kara_enable_cb = QCheckBox("Enable karaoke mode")
        self._kara_enable_cb.setToolTip(
            "When ON, subtitles highlight each word in turn as it is spoken.\n"
            "All other words in the line stay in the normal colour.\n"
            "Requires a transcript file in the project folder."
        )
        self._kara_enable_cb.setStyleSheet(
            f"font-weight: 600; color: {COLORS['text_primary']};"
        )
        kara_enable_row.addWidget(self._kara_enable_cb)
        kara_enable_row.addStretch()
        kf.addRow("", kara_enable_row)

        self._sub_karaoke_color_btn = ColorButton("#FFFF00")
        self._sub_karaoke_color_btn.setToolTip(
            "Colour used to highlight the word currently being spoken.\n"
            "Yellow (#FFFF00) gives maximum contrast on dark backgrounds."
        )
        kf.addRow("Highlight colour:", self._sub_karaoke_color_btn)

        kara_tip = QLabel(
            "When enabled, the subtitle mode is automatically set to Karaoke.\n"
            "Each word lights up as it is spoken — all other words stay white.\n"
            "For accurate word timing, use Whisper model 'small' or larger\n"
            "(Performance tab → Whisper model)."
        )
        kara_tip.setWordWrap(True)
        kara_tip.setStyleSheet(
            f"color:{COLORS['text_secondary']};font-size:11px;"
            f"background:{COLORS['bg_card']};border-radius:4px;padding:8px;"
        )
        kf.addRow("", kara_tip)

        # When karaoke enable checkbox changes, update the mode combo accordingly
        self._kara_enable_cb.stateChanged.connect(self._on_kara_enable_changed)

        lay.addWidget(self._kara_group)

        # Preview swatch
        self._sub_preview = QLabel("Sample subtitle text — preview")
        self._sub_preview.setAlignment(Qt.AlignCenter)
        self._sub_preview.setFixedHeight(70)
        self._sub_preview.setStyleSheet(
            "background:#111118;border-radius:6px;"
            "color:#FFFFFF;font-size:18px;font-weight:700;"
            "border:1px solid #333;"
        )
        lay.addWidget(self._sub_preview)

        # Connect preview update
        for widget in [self._sub_text_color_btn, self._sub_outline_color_btn,
                       self._sub_font_edit, self._sub_size_spin, self._sub_bold_cb]:
            if hasattr(widget, "color_changed"):
                widget.color_changed.connect(self._update_sub_preview)
            elif hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._update_sub_preview)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._update_sub_preview)
            elif hasattr(widget, "stateChanged"):
                widget.stateChanged.connect(self._update_sub_preview)

        lay.addWidget(self._info_label(
            "These are global defaults applied to all new projects.\n"
            "You can override per-project in the project editor (Edit button in the Projects tab)."
        ))
        lay.addStretch()
        return w

    def _on_mode_changed(self, mode: str):
        """Sync the karaoke enable checkbox when the mode combo changes."""
        is_karaoke = mode.lower() == "karaoke"
        self._kara_enable_cb.blockSignals(True)
        self._kara_enable_cb.setChecked(is_karaoke)
        self._kara_enable_cb.blockSignals(False)

    def _on_kara_enable_changed(self, state):
        """Sync the mode combo when the karaoke checkbox changes."""
        # Use isChecked() — avoids unreliable Qt.Checked enum vs int comparison in PySide6
        checked = self._kara_enable_cb.isChecked()
        self._sub_mode_combo.blockSignals(True)
        if checked:
            self._sub_mode_combo.setCurrentText("Karaoke")
        else:
            if self._sub_mode_combo.currentText().lower() == "karaoke":
                self._sub_mode_combo.setCurrentText("Phrase")
        self._sub_mode_combo.blockSignals(False)

    def _update_sub_preview(self, *_):
        color = self._sub_text_color_btn.get_color()
        size  = max(12, min(self._sub_size_spin.value() // 3, 28))
        bold  = "700" if self._sub_bold_cb.isChecked() else "400"
        font  = self._sub_font_edit.text().strip() or "Arial"
        self._sub_preview.setStyleSheet(
            f"background:#111118;border-radius:6px;"
            f"color:{color};font-size:{size}px;font-weight:{bold};"
            f"font-family:'{font}';"
            f"border:1px solid #333;"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Tab: Advanced
    # ─────────────────────────────────────────────────────────────────────────

    def _tab_advanced(self) -> QWidget:
        w, lay = self._scroll_tab()

        ffmpeg_g = QGroupBox("FFmpeg Binary")
        f = QFormLayout(ffmpeg_g); f.setSpacing(10)

        ffp_row = QHBoxLayout()
        self._ffmpeg_path_edit = QLineEdit()
        self._ffmpeg_path_edit.setPlaceholderText("Auto-detected (leave blank)")
        browse_ff = QPushButton("Browse…")
        browse_ff.setFixedWidth(80); browse_ff.setFixedHeight(30)
        browse_ff.clicked.connect(self._browse_ffmpeg)
        ffp_row.addWidget(self._ffmpeg_path_edit, 1)
        ffp_row.addWidget(browse_ff)
        f.addRow("ffmpeg.exe path:", ffp_row)

        test_row = QHBoxLayout()
        test_btn = QPushButton("Test FFmpeg")
        test_btn.setFixedWidth(120); test_btn.setFixedHeight(30)
        test_btn.clicked.connect(self._test_ffmpeg)
        self._ffmpeg_status_lbl = QLabel("")
        test_row.addWidget(test_btn)
        test_row.addWidget(self._ffmpeg_status_lbl, 1)
        f.addRow("", test_row)
        lay.addWidget(ffmpeg_g)

        debug_g = QGroupBox("Debug & Diagnostics")
        fd = QFormLayout(debug_g); fd.setSpacing(8)
        self._debug_cb      = QCheckBox("Enable verbose debug logging")
        self._log_ffmpeg_cb = QCheckBox("Log all FFmpeg stderr output to Logs panel")
        self._show_cmd_cb   = QCheckBox("Show full FFmpeg command in Logs panel")
        for cb in [self._debug_cb, self._log_ffmpeg_cb, self._show_cmd_cb]:
            fd.addRow("", cb)
        lay.addWidget(debug_g)
        lay.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _scroll_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        return scroll, layout

    def _info_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color:{COLORS['text_secondary']};font-size:12px;"
            f"background:{COLORS['bg_card']};border-radius:6px;padding:10px;"
        )
        return lbl

    # ─────────────────────────────────────────────────────────────────────────
    # Load / Save
    # ─────────────────────────────────────────────────────────────────────────

    def _load_values(self):
        s = self.settings
        # General
        self._auto_validate_cb.setChecked(s.get("auto_validate_on_import", True))
        self._auto_queue_cb.setChecked(s.get("auto_queue_valid_projects", False))
        self._skip_completed_cb.setChecked(s.get("skip_completed_projects", True))
        self._overwrite_cb.setChecked(s.get("overwrite_existing", False))
        self._reopen_cb.setChecked(s.get("reopen_last_workspace", True))
        self._auto_open_cb.setChecked(s.get("auto_open_output", False))
        self._recursive_cb.setChecked(s.get("recursive_scan", True))
        self._max_depth_spin.setValue(s.get("max_scan_depth", 5))
        # Performance
        self._threads_spin.setValue(s.get("ffmpeg_threads", 0))
        self._concurrent_spin.setValue(s.get("max_concurrent_jobs", 1))
        self._gpu_cb.setChecked(s.get("enable_gpu", False))
        self._whisper_model_combo.setCurrentText(s.get("whisper_model", "small"))
        self._whisper_device_combo.setCurrentText(s.get("whisper_device", "cpu"))
        lang = s.get("whisper_language", "auto")
        self._whisper_lang_edit.setText("" if lang == "auto" else lang)
        # Files & naming
        self._output_folder_edit.setText(s.get("default_output_folder", ""))
        self._name_template_edit.setText(s.get("output_name_template", "{project_name}_{date}"))
        self._pref_audio_edit.setText(s.get("preferred_audio_name", ""))
        self._pref_audio_kw_edit.setText(s.get("preferred_audio_keywords", "narration,voiceover,audio,voice"))
        self._pref_script_edit.setText(s.get("preferred_script_name", ""))
        self._pref_script_kw_edit.setText(s.get("preferred_script_keywords", "script,transcript,narration,text"))
        # Subtitles
        self._sub_font_edit.setText(s.get("sub_font", "Arial"))
        self._sub_size_spin.setValue(s.get("sub_font_size", 72))
        self._sub_bold_cb.setChecked(s.get("sub_bold", True))
        self._sub_text_color_btn.set_color(s.get("sub_primary_color", "#FFFFFF"))
        self._sub_outline_color_btn.set_color(s.get("sub_outline_color", "#000000"))
        self._sub_outline_spin.setValue(s.get("sub_outline_width", 3.0))
        self._sub_shadow_spin.setValue(s.get("sub_shadow", 1.5))
        self._sub_margin_spin.setValue(s.get("sub_margin_v", 80))
        # sub_mode stored as lowercase; combo items are Title-case
        mode_val = s.get("sub_mode", "phrase")
        # Block BOTH widgets during load so signal chains don't interfere.
        # Set combo text silently, then set the checkbox directly from saved value.
        self._sub_mode_combo.blockSignals(True)
        self._sub_mode_combo.setCurrentText(mode_val.replace("_", " ").title())
        self._sub_mode_combo.blockSignals(False)
        self._kara_enable_cb.blockSignals(True)
        self._kara_enable_cb.setChecked(mode_val == "karaoke")
        self._kara_enable_cb.blockSignals(False)
        self._sub_karaoke_color_btn.set_color(s.get("sub_karaoke_color", "#FFFF00"))
        self._sub_maxchars_spin.setValue(s.get("sub_max_chars", 42))
        # Advanced
        self._ffmpeg_path_edit.setText(s.get("ffmpeg_path", ""))
        self._debug_cb.setChecked(s.get("debug_mode", False))
        self._log_ffmpeg_cb.setChecked(s.get("log_ffmpeg_output", True))
        self._show_cmd_cb.setChecked(s.get("show_ffmpeg_commands", False))
        self._update_sub_preview()

    def _save(self):
        s = self.settings

        # Convert hex color → ASS &HAABBGGRR format
        def hex_to_ass(h: str) -> str:
            h = h.lstrip("#")
            if len(h) == 6:
                r, g, b = h[0:2], h[2:4], h[4:6]
                return f"&H00{b}{g}{r}".upper()
            return "&H00FFFFFF"

        s.set_many({
            # General
            "auto_validate_on_import":  self._auto_validate_cb.isChecked(),
            "auto_queue_valid_projects": self._auto_queue_cb.isChecked(),
            "skip_completed_projects":  self._skip_completed_cb.isChecked(),
            "overwrite_existing":       self._overwrite_cb.isChecked(),
            "reopen_last_workspace":    self._reopen_cb.isChecked(),
            "auto_open_output":         self._auto_open_cb.isChecked(),
            "recursive_scan":           self._recursive_cb.isChecked(),
            "max_scan_depth":           self._max_depth_spin.value(),
            # Performance
            "ffmpeg_threads":           self._threads_spin.value(),
            "max_concurrent_jobs":      self._concurrent_spin.value(),
            "enable_gpu":               self._gpu_cb.isChecked(),
            "whisper_model":            self._whisper_model_combo.currentText(),
            "whisper_device":           self._whisper_device_combo.currentText(),
            "whisper_language":         self._whisper_lang_edit.text().strip() or "auto",
            # Files & naming
            "default_output_folder":    self._output_folder_edit.text().strip(),
            "output_name_template":     self._name_template_edit.text().strip() or "{project_name}_{date}",
            "preferred_audio_name":     self._pref_audio_edit.text().strip(),
            "preferred_audio_keywords": self._pref_audio_kw_edit.text().strip(),
            "preferred_script_name":    self._pref_script_edit.text().strip(),
            "preferred_script_keywords":self._pref_script_kw_edit.text().strip(),
            # Subtitles — store sub_mode as lowercase for backward compat
            "sub_font":                 self._sub_font_edit.text().strip() or "Arial",
            "sub_font_size":            self._sub_size_spin.value(),
            "sub_bold":                 self._sub_bold_cb.isChecked(),
            "sub_primary_color":        self._sub_text_color_btn.get_color(),
            "sub_outline_color":        self._sub_outline_color_btn.get_color(),
            "sub_outline_width":        self._sub_outline_spin.value(),
            "sub_shadow":               self._sub_shadow_spin.value(),
            "sub_margin_v":             self._sub_margin_spin.value(),
            "sub_mode":                 self._sub_mode_combo.currentText().lower(),
            "sub_karaoke_color":        self._sub_karaoke_color_btn.get_color(),
            "sub_max_chars":            self._sub_maxchars_spin.value(),
            # Advanced
            "ffmpeg_path":              self._ffmpeg_path_edit.text().strip(),
            "debug_mode":               self._debug_cb.isChecked(),
            "log_ffmpeg_output":        self._log_ffmpeg_cb.isChecked(),
            "show_ffmpeg_commands":     self._show_cmd_cb.isChecked(),
        })

        # Apply subtitle settings to the default profile
        profile = s.get_default_profile()
        profile.subtitle_font         = self._sub_font_edit.text().strip() or "Arial"
        profile.subtitle_font_size    = self._sub_size_spin.value()
        profile.subtitle_bold         = self._sub_bold_cb.isChecked()
        profile.subtitle_primary_color= hex_to_ass(self._sub_text_color_btn.get_color())
        profile.subtitle_outline_color= hex_to_ass(self._sub_outline_color_btn.get_color())
        profile.subtitle_outline_width= self._sub_outline_spin.value()
        profile.subtitle_shadow       = self._sub_shadow_spin.value()
        profile.subtitle_margin_v     = self._sub_margin_spin.value()
        from app.core.project import SubtitleMode
        try:
            profile.subtitle_mode = SubtitleMode(self._sub_mode_combo.currentText().lower())
        except ValueError:
            pass
        # Apply karaoke highlight colour → ASS format
        profile.subtitle_karaoke_color = hex_to_ass(self._sub_karaoke_color_btn.get_color())
        profile.subtitle_max_chars = self._sub_maxchars_spin.value()
        s.set("default_profile", profile.to_dict())

        ffmpeg_path = self._ffmpeg_path_edit.text().strip()
        if ffmpeg_path:
            self.ffmpeg_path_changed.emit(ffmpeg_path)

        self.settings_changed.emit()
        self.accept()

    def _reset(self):
        if QMessageBox.question(
            self, "Reset Settings", "Reset all settings to factory defaults?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.settings.reset_to_defaults()
            self._load_values()

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ffmpeg.exe", "",
            "Executable (ffmpeg.exe ffmpeg);;All Files (*)"
        )
        if path:
            self._ffmpeg_path_edit.setText(path)

    def _browse_output_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Default Output Folder")
        if path:
            self._output_folder_edit.setText(path)

    def _test_ffmpeg(self):
        from app.utils.ffmpeg_utils import invalidate_ffmpeg_cache, check_ffmpeg_ready
        from app.utils import ffmpeg_utils
        custom = self._ffmpeg_path_edit.text().strip()
        invalidate_ffmpeg_cache()
        if custom:
            ffmpeg_utils._ffmpeg_path = custom
        ok, msg = check_ffmpeg_ready(force=True)
        if ok:
            self._ffmpeg_status_lbl.setText(f"✅ {msg}")
            self._ffmpeg_status_lbl.setStyleSheet(f"color:{COLORS['success']};")
        else:
            self._ffmpeg_status_lbl.setText(f"❌ {msg}")
            self._ffmpeg_status_lbl.setStyleSheet(f"color:{COLORS['error']};")
