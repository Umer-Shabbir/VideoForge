"""
Settings dialog — all application-level settings.
Tabs: General | FFmpeg & Performance | Output & Files | Subtitles | Advanced
"""

import os
import json
from copy import deepcopy
from pathlib import Path
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
from app.core.project import RenderProfile, SubtitleMode


def ass_to_hex(color_str: str) -> str:
    """Convert ASS &HAABBGGRR or &HBBGGRR or #RRGGBB to #RRGGBB hex."""
    if not color_str:
        return "#FFFFFF"
    s = color_str.strip()
    if s.startswith("#"):
        return s[:7].upper()
    if s.startswith("&H") or s.startswith("&h"):
        raw = s[2:].rstrip("&")
        if len(raw) == 8:
            b, g, r = raw[2:4], raw[4:6], raw[6:8]
            return f"#{r}{g}{b}".upper()
        elif len(raw) == 6:
            b, g, r = raw[0:2], raw[2:4], raw[4:6]
            return f"#{r}{g}{b}".upper()
    return "#FFFFFF"


def hex_to_ass(hex_str: str, alpha: str = "00") -> str:
    """Convert #RRGGBB or &HAABBGGRR to &HAABBGGRR."""
    if not hex_str:
        return f"&H{alpha}FFFFFF"
    s = hex_str.strip()
    if s.startswith("&H") or s.startswith("&h"):
        raw = s[2:].rstrip("&")
        if len(raw) == 8:
            return f"&H{raw}".upper()
        if len(raw) == 6:
            return f"&H{alpha}{raw}".upper()
        return f"&H{alpha}FFFFFF"
    if s.startswith("#"):
        s = s[1:]
    if len(s) >= 6:
        r, g, b = s[0:2], s[2:4], s[4:6]
        return f"&H{alpha}{b}{g}{r}".upper()
    return f"&H{alpha}FFFFFF"


PRESET_DISPLAY_NAMES = {
    "blueprint": "📐 Blueprint",
    "clay": "🏺 Clay",
    "cobalt_impact": "💥 Cobalt Impact",
    "cutout_collage": "✂️ Cutout Collage",
    "glass_node": "🔷 Glass Node",
    "line_graphic": "📏 Line Graphic",
    "paint_blast": "🎨 Paint Blast",
    "paper_glass": "📜 Paper Glass",
    "phosphor_terminal": "📟 Phosphor Terminal",
    "punk_zine": "⚡ Punk Zine",
    "money_chuck": "💰 Money Chuck",
    "bradikinin": "📼 Bradikinin",
    "final_sight": "📹 Final Sight",
    "cast_venk": "👁️ CastVenk",
    "rainbow_yoga": "🌈 Rainbow Yoga",
    "pov_wealth": "📈 POV Wealth",
    "genius_history": "⚔️ Genius History",
    "ink_explainer": "🖋️ Ink Explainer",
    "built_on_you": "🏢 Built On You",
    "terrain_walk": "🗺️ Terrain Walk",
    "go_documentaries": "🏗️ Go Documentaries",
    "nostalgia_rock": "🎸 Nostalgia Rock",
    "psych_toons": "🧠 Psych Toons",

    "Fast Preview (720p)": "⚡ Fast Preview (720p)",
    "High Quality Archive": "🏆 High Quality Archive",
}


# ── Preset Subtitle Card ──────────────────────────────────────────────────────

class PresetSubtitleCard(QFrame):
    """Visual preview and metadata card for a single preset's subtitle style."""
    edit_requested = Signal(str)             # emits preset_name
    apply_as_default_requested = Signal(str) # emits preset_name
    reset_requested = Signal(str)            # emits preset_name

    def __init__(self, preset_name: str, display_name: str, profile_dict: dict, parent=None):
        super().__init__(parent)
        self.preset_name = preset_name
        self.display_name = display_name
        self._profile_dict = profile_dict
        self._setup_ui()
        self.update_data(profile_dict)

    def _setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"PresetSubtitleCard {{ background-color: {COLORS['bg_card']}; "
            f"border: 1px solid #2B303C; border-radius: 8px; margin-bottom: 6px; }}"
            f"PresetSubtitleCard:hover {{ border: 1px solid {COLORS['accent']}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # Header: Icon + Title + Badges + Action Buttons
        top = QHBoxLayout()
        top.setSpacing(8)
        self._title_lbl = QLabel(self.display_name)
        self._title_lbl.setStyleSheet("font-weight: 700; font-size: 14px; color: #FFFFFF;")
        top.addWidget(self._title_lbl)

        self._mode_badge = QLabel("KARAOKE")
        self._mode_badge.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: #000000; "
            f"font-size: 10px; font-weight: 800; border-radius: 3px; padding: 2px 6px;"
        )
        top.addWidget(self._mode_badge)

        self._pos_badge = QLabel("80px")
        self._pos_badge.setStyleSheet(
            "background-color: #1E232E; color: #8A92A6; font-size: 10px; font-weight: 600; "
            "border-radius: 3px; padding: 2px 6px;"
        )
        top.addWidget(self._pos_badge)

        top.addStretch()

        btn_edit = QPushButton("✏️ Edit Style")
        btn_edit.setFixedHeight(26)
        btn_edit.setStyleSheet(
            f"QPushButton {{ background-color: #232834; color: {COLORS['text_primary']}; "
            f"border: 1px solid #3A4150; border-radius: 4px; padding: 0 10px; font-size: 11px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {COLORS['accent']}; color: #000000; }}"
        )
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.preset_name))
        top.addWidget(btn_edit)

        btn_default = QPushButton("⭐ Set as Default")
        btn_default.setFixedHeight(26)
        btn_default.setStyleSheet(
            "QPushButton { background-color: #232834; color: #8A92A6; "
            "border: 1px solid #3A4150; border-radius: 4px; padding: 0 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: #2E3545; color: #FFFFFF; }"
        )
        btn_default.setToolTip("Copy this preset's font & colors to the global default")
        btn_default.clicked.connect(lambda: self.apply_as_default_requested.emit(self.preset_name))
        top.addWidget(btn_default)

        btn_reset = QPushButton("🔄 Reset")
        btn_reset.setFixedHeight(26)
        btn_reset.setStyleSheet(
            "QPushButton { background-color: transparent; color: #6C7280; "
            "border: 1px solid #2B303C; border-radius: 4px; padding: 0 6px; font-size: 11px; }"
            "QPushButton:hover { color: #E5E7EB; border-color: #4B5563; }"
        )
        btn_reset.setToolTip("Reset this preset's subtitle styling to master registry default")
        btn_reset.clicked.connect(lambda: self.reset_requested.emit(self.preset_name))
        top.addWidget(btn_reset)

        lay.addLayout(top)

        # Visual Subtitle Preview Swatch
        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(Qt.AlignCenter)
        self._preview_lbl.setFixedHeight(54)
        self._preview_lbl.setWordWrap(True)
        lay.addWidget(self._preview_lbl)

        # Specifications & Swatches Row
        spec_row = QHBoxLayout()
        spec_row.setSpacing(12)
        self._font_spec_lbl = QLabel()
        self._font_spec_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        spec_row.addWidget(self._font_spec_lbl)

        self._color_swatches_lbl = QLabel()
        self._color_swatches_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        spec_row.addWidget(self._color_swatches_lbl)

        self._transitions_lbl = QLabel()
        self._transitions_lbl.setStyleSheet("color: #6C7280; font-size: 10px;")
        spec_row.addWidget(self._transitions_lbl, 1)

        lay.addLayout(spec_row)

    def update_data(self, profile_dict: dict):
        self._profile_dict = profile_dict
        font = profile_dict.get("subtitle_font", "Arial")
        font_size = profile_dict.get("subtitle_font_size", 72)
        bold = profile_dict.get("subtitle_bold", True)
        pri_hex = ass_to_hex(profile_dict.get("subtitle_primary_color", "&H00FFFFFF"))
        kara_hex = ass_to_hex(profile_dict.get("subtitle_karaoke_color", "&H0000FFFF"))
        out_hex = ass_to_hex(profile_dict.get("subtitle_outline_color", "&H00000000"))
        out_width = profile_dict.get("subtitle_outline_width", 3.0)
        mode = profile_dict.get("subtitle_mode", "karaoke")
        mode_str = mode.value if hasattr(mode, "value") else str(mode)
        margin_v = profile_dict.get("subtitle_margin_v", 80)
        transitions = profile_dict.get("allowed_transitions", [])

        self._mode_badge.setText(mode_str.upper())
        self._pos_badge.setText(f"Margin: {margin_v}px")

        # Scaled font size for preview
        pv_size = max(13, min(font_size // 3, 20))
        weight_str = "bold" if bold else "normal"

        # Thematic background color for preset preview
        bg_color = "#0B0E14"
        if "terminal" in self.preset_name.lower():
            bg_color = "#040A05"
        elif "blueprint" in self.preset_name.lower():
            bg_color = "#091322"
        elif "clay" in self.preset_name.lower():
            bg_color = "#1B1716"
        elif "cobalt" in self.preset_name.lower():
            bg_color = "#061020"
        elif "bradikinin" in self.preset_name.lower():
            bg_color = "#070F08"
        elif "final_sight" in self.preset_name.lower():
            bg_color = "#0B0E0C"
        elif "cast_venk" in self.preset_name.lower():
            bg_color = "#13171F"
        elif "rainbow_yoga" in self.preset_name.lower():
            bg_color = "#2E1A47"
        elif "pov_wealth" in self.preset_name.lower():
            bg_color = "#102117"
        elif "genius_history" in self.preset_name.lower():
            bg_color = "#1B130E"

        self._preview_lbl.setStyleSheet(
            f"background-color: {bg_color}; border: 1px solid #1F2430; border-radius: 6px; padding: 4px 10px;"
        )

        sample_name = self.preset_name.replace('_', ' ').title()
        html = (
            f'<div style="text-align:center; font-family:\'{font}\', sans-serif; '
            f'font-size:{pv_size}px; font-weight:{weight_str}; color:{pri_hex};">'
            f'Creating {sample_name} video with '
            f'<span style="color:{kara_hex}; font-weight:bold; text-decoration: underline;">karaoke</span>'
            f' subtitle animation'
            f'</div>'
        )
        self._preview_lbl.setText(html)

        self._font_spec_lbl.setText(f"🔤 <b>{font}</b> ({font_size}px{' Bold' if bold else ''})")
        self._color_swatches_lbl.setText(
            f'🎨 Text: <span style="color:{pri_hex};">■</span> <code>{pri_hex}</code> &nbsp;|&nbsp; '
            f'🌟 Karaoke: <span style="color:{kara_hex};">■</span> <code>{kara_hex}</code> &nbsp;|&nbsp; '
            f'🔲 Outline: <span style="color:{out_hex};">■</span> <code>{out_hex}</code> ({out_width}px)'
        )
        if transitions:
            t_str = ", ".join(transitions[:4])
            if len(transitions) > 4:
                t_str += f" +{len(transitions)-4}"
            self._transitions_lbl.setText(f"Transitions: {t_str}")
        else:
            self._transitions_lbl.setText("")


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
        self.setMinimumSize(820, 680)
        self.setModal(True)
        self._active_target = "global"
        self._global_sub_cache = {}
        self._presets_cache = {}
        self._cards_map = {}
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
            f"System: {psutil.cpu_count(logical=False) or 2} physical cores "
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
        self._sub_tab_scroll_widget = w

        # Header description
        header = QLabel("Subtitle & Karaoke Styles")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        lay.addWidget(header)

        desc = QLabel(
            "Configure global subtitle defaults and customize individual typography, colors, and karaoke "
            "highlighting for all 10 visual presets in the suite. Projects automatically adopt their detected "
            "preset styling during video rendering."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-bottom: 4px;")
        lay.addWidget(desc)

        # ── Target Selector Bar ───────────────────────────────────────────────
        selector_frame = QFrame()
        selector_frame.setStyleSheet(
            f"background-color: {COLORS['bg_card']}; border: 1px solid #2B303C; "
            f"border-radius: 6px; padding: 6px 12px;"
        )
        sel_lay = QHBoxLayout(selector_frame)
        sel_lay.setContentsMargins(6, 4, 6, 4)
        sel_lay.setSpacing(10)

        sel_lbl = QLabel("Style to Edit:")
        sel_lbl.setStyleSheet("font-weight: 600; font-size: 12px; color: #E5E7EB;")
        sel_lay.addWidget(sel_lbl)

        self._sub_target_combo = QComboBox()
        self._sub_target_combo.setMinimumWidth(230)
        self._sub_target_combo.currentIndexChanged.connect(self._on_target_changed)
        sel_lay.addWidget(self._sub_target_combo)

        btn_copy_global = QPushButton("⭐ Set as Default")
        btn_copy_global.setToolTip("Set current editor styling as the global default for all new projects")
        btn_copy_global.clicked.connect(self._copy_current_to_global)
        sel_lay.addWidget(btn_copy_global)

        btn_reset_preset = QPushButton("🔄 Reset Current Preset")
        btn_reset_preset.setToolTip("Restore currently selected preset to master registry default")
        btn_reset_preset.clicked.connect(self._reset_current_preset)
        sel_lay.addWidget(btn_reset_preset)

        sel_lay.addStretch()

        btn_reload_all = QPushButton("🔄 Reload All from Registry")
        btn_reload_all.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['accent']}; color: #000000; "
            f"font-weight: 700; border-radius: 4px; padding: 5px 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: #FFD54F; }}"
        )
        btn_reload_all.setToolTip("Re-sync all 10 presets from master_presets_registry.json")
        btn_reload_all.clicked.connect(self._reload_all_from_registry)
        sel_lay.addWidget(btn_reload_all)

        lay.addWidget(selector_frame)

        # ── Active Subtitle Style Editor ──────────────────────────────────────
        self._editor_group = QGroupBox("Active Subtitle Style Editor — ★ Global Default")
        f = QFormLayout(self._editor_group); f.setSpacing(10)

        # Enable subtitles checkbox
        self._sub_enabled_cb = QCheckBox("Enable subtitles")
        self._sub_enabled_cb.setStyleSheet(f"font-weight: 600; color: {COLORS['text_primary']};")
        self._sub_enabled_cb.setToolTip(
            "When checked, subtitles will be burned into the video by default."
        )
        f.addRow("", self._sub_enabled_cb)

        # Font
        self._sub_font_edit = QLineEdit()
        self._sub_font_edit.setFixedWidth(220)
        self._sub_font_edit.setPlaceholderText("Arial")
        self._sub_font_edit.setToolTip("Any font installed on Windows (e.g. Consolas, Arial Rounded MT Bold, Impact, Segoe UI)")
        f.addRow("Font family:", self._sub_font_edit)

        # Size
        self._sub_size_spin = QSpinBox()
        self._sub_size_spin.setRange(24, 150)
        self._sub_size_spin.setSuffix(" px")
        self._sub_size_spin.setFixedWidth(90)
        f.addRow("Font size:", self._sub_size_spin)

        # Bold
        self._sub_bold_cb = QCheckBox("Bold text")
        f.addRow("", self._sub_bold_cb)

        # Colors row: Text, Karaoke Highlight, Outline
        text_row = QHBoxLayout()
        text_row.setSpacing(12)
        self._sub_text_color_btn  = ColorButton("#FFFFFF")
        self._sub_karaoke_color_btn = ColorButton("#FFFF00")
        self._sub_outline_color_btn = ColorButton("#000000")

        text_row.addWidget(QLabel("Text:"))
        text_row.addWidget(self._sub_text_color_btn)
        text_row.addSpacing(8)
        text_row.addWidget(QLabel("Karaoke Highlight:"))
        text_row.addWidget(self._sub_karaoke_color_btn)
        text_row.addSpacing(8)
        text_row.addWidget(QLabel("Outline:"))
        text_row.addWidget(self._sub_outline_color_btn)
        text_row.addStretch()
        f.addRow("Colors:", text_row)

        # Outline width & shadow
        dim_row = QHBoxLayout()
        dim_row.setSpacing(14)
        self._sub_outline_spin = QDoubleSpinBox()
        self._sub_outline_spin.setRange(0.0, 8.0)
        self._sub_outline_spin.setSingleStep(0.5)
        self._sub_outline_spin.setSuffix(" px")
        self._sub_outline_spin.setFixedWidth(90)
        dim_row.addWidget(QLabel("Outline width:"))
        dim_row.addWidget(self._sub_outline_spin)

        self._sub_shadow_spin = QDoubleSpinBox()
        self._sub_shadow_spin.setRange(0.0, 6.0)
        self._sub_shadow_spin.setSingleStep(0.5)
        self._sub_shadow_spin.setSuffix(" px")
        self._sub_shadow_spin.setFixedWidth(90)
        dim_row.addWidget(QLabel("Shadow depth:"))
        dim_row.addWidget(self._sub_shadow_spin)
        dim_row.addStretch()
        f.addRow("Geometry:", dim_row)

        # Vertical margin
        self._sub_margin_spin = QSpinBox()
        self._sub_margin_spin.setRange(0, 500)
        self._sub_margin_spin.setSuffix(" px from bottom")
        self._sub_margin_spin.setFixedWidth(160)
        self._sub_margin_spin.setToolTip(
            "Distance from the bottom edge. Increase this for 9:16 vertical videos."
        )
        f.addRow("Vertical position:", self._sub_margin_spin)

        # Mode
        mode_row = QHBoxLayout()
        self._sub_mode_combo = QComboBox()
        self._sub_mode_combo.addItems(["Phrase", "Classic", "Viral", "Word", "Karaoke"])
        self._sub_mode_combo.setFixedWidth(160)
        self._sub_mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._sub_mode_combo)

        self._kara_enable_cb = QCheckBox("Enable word-by-word karaoke highlight")
        self._kara_enable_cb.setStyleSheet(f"font-weight: 600; color: {COLORS['accent_text']};")
        self._kara_enable_cb.stateChanged.connect(self._on_kara_enable_changed)
        mode_row.addWidget(self._kara_enable_cb)
        mode_row.addStretch()
        f.addRow("Subtitle mode:", mode_row)

        # Max chars per line
        self._sub_maxchars_spin = QSpinBox()
        self._sub_maxchars_spin.setRange(10, 120)
        self._sub_maxchars_spin.setSuffix(" chars")
        self._sub_maxchars_spin.setFixedWidth(110)
        f.addRow("Max chars per line:", self._sub_maxchars_spin)

        # Top live preview box
        self._sub_preview = QLabel()
        self._sub_preview.setAlignment(Qt.AlignCenter)
        self._sub_preview.setFixedHeight(64)
        self._sub_preview.setWordWrap(True)
        self._sub_preview.setStyleSheet(
            "background:#0C0F17; border-radius:6px; border:1px solid #232733; padding: 4px;"
        )
        f.addRow("Live Preview:", self._sub_preview)

        lay.addWidget(self._editor_group)

        # Connect all editor widgets to live preview & card sync
        for widget in [self._sub_text_color_btn, self._sub_outline_color_btn,
                       self._sub_karaoke_color_btn, self._sub_font_edit,
                       self._sub_size_spin, self._sub_bold_cb, self._sub_outline_spin,
                       self._sub_shadow_spin, self._sub_margin_spin, self._sub_maxchars_spin,
                       self._sub_enabled_cb]:
            if hasattr(widget, "color_changed"):
                widget.color_changed.connect(self._on_editor_changed)
            elif hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._on_editor_changed)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._on_editor_changed)
            elif hasattr(widget, "stateChanged"):
                widget.stateChanged.connect(self._on_editor_changed)

        # ── ALL PRESET SUBTITLE STYLES GALLERY ────────────────────────────────
        gallery_group = QGroupBox("All Preset Subtitle Styles (11 Master Presets)")
        gallery_group.setStyleSheet(
            f"QGroupBox {{ font-size: 13px; font-weight: 700; color: {COLORS['accent_text']}; "
            f"border: 1px solid #3A4150; border-radius: 8px; margin-top: 14px; padding-top: 16px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; top: -8px; "
            f"padding: 0 6px; background-color: {COLORS['bg_primary']}; color: {COLORS['accent_text']}; }}"
        )
        g_lay = QVBoxLayout(gallery_group)
        g_lay.setContentsMargins(12, 14, 12, 12)
        g_lay.setSpacing(10)

        info_lbl = QLabel(
            "Below are the active subtitle styles tailored for each preset in the suite. "
            "Click 'Edit Style' on any card to customize it in the editor above:"
        )
        info_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        g_lay.addWidget(info_lbl)

        # Card container
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(8)
        g_lay.addLayout(self._cards_layout)

        lay.addWidget(gallery_group)
        lay.addStretch()
        return w

    def _on_mode_changed(self, mode: str):
        """Sync the karaoke enable checkbox when the mode combo changes."""
        is_karaoke = mode.lower() == "karaoke"
        self._kara_enable_cb.blockSignals(True)
        self._kara_enable_cb.setChecked(is_karaoke)
        self._kara_enable_cb.blockSignals(False)
        if is_karaoke:
            self._sub_enabled_cb.setChecked(True)
        self._on_editor_changed()

    def _on_kara_enable_changed(self, state):
        """Sync the mode combo when the karaoke checkbox changes."""
        checked = self._kara_enable_cb.isChecked()
        self._sub_mode_combo.blockSignals(True)
        if checked:
            self._sub_mode_combo.setCurrentText("Karaoke")
            self._sub_enabled_cb.setChecked(True)
        else:
            if self._sub_mode_combo.currentText().lower() == "karaoke":
                self._sub_mode_combo.setCurrentText("Phrase")
        self._sub_mode_combo.blockSignals(False)
        self._on_editor_changed()

    def _update_sub_preview(self, *_):
        color = self._sub_text_color_btn.get_color()
        kara_color = self._sub_karaoke_color_btn.get_color()
        size  = max(13, min(self._sub_size_spin.value() // 3, 22))
        bold  = "bold" if self._sub_bold_cb.isChecked() else "normal"
        font  = self._sub_font_edit.text().strip() or "Arial"
        mode  = self._sub_mode_combo.currentText().lower()

        target_name = "Global Default"
        if self._active_target != "global":
            target_name = PRESET_DISPLAY_NAMES.get(self._active_target, self._active_target)

        highlight_word = "KARAOKE" if mode == "karaoke" else "ACTIVE"
        html = (
            f'<div style="text-align:center; font-family:\'{font}\', sans-serif; '
            f'font-size:{size}px; font-weight:{bold}; color:{color}; padding: 6px;">'
            f'[{target_name}] Preview: Timed words with '
            f'<span style="color:{kara_color}; font-weight:bold; text-decoration: underline;">{highlight_word}</span>'
            f' subtitle burn-in'
            f'</div>'
        )
        self._sub_preview.setText(html)

    # ─────────────────────────────────────────────────────────────────────────
    # Subtitle Preset Handlers & Synchronization
    # ─────────────────────────────────────────────────────────────────────────

    def _load_preset_caches(self):
        """Load all presets into _presets_cache."""
        self._presets_cache = {}
        for name in self.settings.list_presets():
            prof = self.settings.get_preset(name)
            if prof:
                self._presets_cache[name] = prof.to_dict()

    def _refresh_cards_gallery(self):
        """Build or refresh cards in the All Preset Subtitle Styles gallery."""
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards_map = {}

        master_order = ["blueprint", "clay", "cobalt_impact", "cutout_collage",
                        "glass_node", "line_graphic", "money_chuck", "paint_blast", "paper_glass",
                        "phosphor_terminal", "punk_zine", "bradikinin", "final_sight",
                        "cast_venk", "rainbow_yoga", "pov_wealth", "genius_history",
                        "ink_explainer", "built_on_you", "terrain_walk", "go_documentaries",
                        "nostalgia_rock", "psych_toons"]

        # Add master presets first in canonical order
        for name in master_order:
            if name in self._presets_cache:
                disp = PRESET_DISPLAY_NAMES.get(name, name.replace("_", " ").title())
                card = PresetSubtitleCard(name, disp, self._presets_cache[name])
                card.edit_requested.connect(self._select_preset_for_edit)
                card.apply_as_default_requested.connect(self._apply_preset_as_default)
                card.reset_requested.connect(self._reset_preset_from_registry)
                self._cards_layout.addWidget(card)
                self._cards_map[name] = card

        # Add any other presets
        for name in self._presets_cache:
            if name not in master_order and name not in ["Fast Preview (720p)", "High Quality Archive"]:
                disp = PRESET_DISPLAY_NAMES.get(name, name)
                card = PresetSubtitleCard(name, disp, self._presets_cache[name])
                card.edit_requested.connect(self._select_preset_for_edit)
                card.apply_as_default_requested.connect(self._apply_preset_as_default)
                card.reset_requested.connect(self._reset_preset_from_registry)
                self._cards_layout.addWidget(card)
                self._cards_map[name] = card

    def _load_target_into_editor(self, target_key: str):
        """Populate the editor form widgets with data from active target."""
        if target_key == "global":
            data = self._global_sub_cache
            title = "Active Subtitle Style Editor — ★ Global Default"
        else:
            data = self._presets_cache.get(target_key, {})
            disp = PRESET_DISPLAY_NAMES.get(target_key, target_key.replace("_", " ").title())
            title = f"Active Subtitle Style Editor — {disp}"

        self._editor_group.setTitle(title)

        widgets = [self._sub_enabled_cb, self._sub_font_edit, self._sub_size_spin,
                   self._sub_bold_cb, self._sub_outline_spin, self._sub_shadow_spin,
                   self._sub_margin_spin, self._sub_mode_combo, self._kara_enable_cb,
                   self._sub_maxchars_spin]
        for w in widgets:
            w.blockSignals(True)

        mode_val = data.get("subtitle_mode", data.get("sub_mode", "karaoke"))
        if hasattr(mode_val, "value"):
            mode_val = mode_val.value
        mode_val = str(mode_val).lower()

        is_sub_enabled = data.get("subtitle_enabled", data.get("sub_enabled", True))
        self._sub_enabled_cb.setChecked(bool(is_sub_enabled or mode_val == "karaoke"))
        self._sub_font_edit.setText(str(data.get("subtitle_font", data.get("sub_font", "Arial"))))
        self._sub_size_spin.setValue(int(data.get("subtitle_font_size", data.get("sub_font_size", 72))))
        self._sub_bold_cb.setChecked(bool(data.get("subtitle_bold", data.get("sub_bold", True))))

        pri_col = str(data.get("subtitle_primary_color", data.get("sub_primary_color", "#FFFFFF")))
        self._sub_text_color_btn.set_color(ass_to_hex(pri_col))

        out_col = str(data.get("subtitle_outline_color", data.get("sub_outline_color", "#000000")))
        self._sub_outline_color_btn.set_color(ass_to_hex(out_col))

        kara_col = str(data.get("subtitle_karaoke_color", data.get("sub_karaoke_color", "#FFFF00")))
        self._sub_karaoke_color_btn.set_color(ass_to_hex(kara_col))

        self._sub_outline_spin.setValue(float(data.get("subtitle_outline_width", data.get("sub_outline_width", 3.0))))
        self._sub_shadow_spin.setValue(float(data.get("subtitle_shadow", data.get("sub_shadow", 1.5))))
        self._sub_margin_spin.setValue(int(data.get("subtitle_margin_v", data.get("sub_margin_v", 80))))

        self._sub_mode_combo.setCurrentText(mode_val.replace("_", " ").title())
        self._kara_enable_cb.setChecked(mode_val == "karaoke")

        self._sub_maxchars_spin.setValue(int(data.get("subtitle_max_chars", data.get("sub_max_chars", 42))))

        for w in widgets:
            w.blockSignals(False)

        self._update_sub_preview()

    def _save_editor_to_target(self, target_key: str):
        """Save current widget state into the specified target's cache."""
        if not target_key:
            return
        is_karaoke = self._kara_enable_cb.isChecked() or (self._sub_mode_combo.currentText().lower() == "karaoke")
        mode = "karaoke" if is_karaoke else self._sub_mode_combo.currentText().lower()
        sub_enabled = self._sub_enabled_cb.isChecked() or is_karaoke

        pri_hex = self._sub_text_color_btn.get_color()
        out_hex = self._sub_outline_color_btn.get_color()
        kara_hex = self._sub_karaoke_color_btn.get_color()

        if target_key == "global":
            self._global_sub_cache.update({
                "sub_enabled": sub_enabled,
                "sub_font": self._sub_font_edit.text().strip() or "Arial",
                "sub_font_size": self._sub_size_spin.value(),
                "sub_bold": self._sub_bold_cb.isChecked(),
                "sub_primary_color": pri_hex,
                "sub_outline_color": out_hex,
                "sub_outline_width": self._sub_outline_spin.value(),
                "sub_shadow": self._sub_shadow_spin.value(),
                "sub_margin_v": self._sub_margin_spin.value(),
                "sub_mode": mode,
                "sub_karaoke_color": kara_hex,
                "sub_max_chars": self._sub_maxchars_spin.value(),
            })
        else:
            if target_key in self._presets_cache:
                p = self._presets_cache[target_key]
                p["subtitle_enabled"] = sub_enabled
                p["subtitle_font"] = self._sub_font_edit.text().strip() or "Arial"
                p["subtitle_font_size"] = self._sub_size_spin.value()
                p["subtitle_bold"] = self._sub_bold_cb.isChecked()
                p["subtitle_primary_color"] = hex_to_ass(pri_hex)
                p["subtitle_outline_color"] = hex_to_ass(out_hex)
                p["subtitle_karaoke_color"] = hex_to_ass(kara_hex)
                p["subtitle_outline_width"] = self._sub_outline_spin.value()
                p["subtitle_shadow"] = self._sub_shadow_spin.value()
                p["subtitle_margin_v"] = self._sub_margin_spin.value()
                p["subtitle_mode"] = mode
                p["subtitle_max_chars"] = self._sub_maxchars_spin.value()

    def _on_target_changed(self, index: int):
        """Triggered when user selects a different target in the combo box."""
        new_target = self._sub_target_combo.itemData(index)
        if not new_target or new_target == self._active_target:
            return
        self._save_editor_to_target(self._active_target)
        self._active_target = new_target
        self._load_target_into_editor(new_target)

    def _on_editor_changed(self, *_):
        """Live update: write editor values to cache, update preview, and update card."""
        self._save_editor_to_target(self._active_target)
        self._update_sub_preview()
        if self._active_target != "global" and self._active_target in self._cards_map:
            self._cards_map[self._active_target].update_data(self._presets_cache[self._active_target])

    def _select_preset_for_edit(self, preset_name: str):
        """Select a preset from a card click and scroll to editor."""
        for i in range(self._sub_target_combo.count()):
            if self._sub_target_combo.itemData(i) == preset_name:
                self._sub_target_combo.setCurrentIndex(i)
                if hasattr(self, "_sub_tab_scroll_widget") and self._sub_tab_scroll_widget:
                    self._sub_tab_scroll_widget.verticalScrollBar().setValue(0)
                break

    def _copy_current_to_global(self):
        """Copy currently edited styling to global default."""
        self._save_editor_to_target(self._active_target)
        pri_hex = self._sub_text_color_btn.get_color()
        out_hex = self._sub_outline_color_btn.get_color()
        kara_hex = self._sub_karaoke_color_btn.get_color()
        is_karaoke = self._kara_enable_cb.isChecked() or (self._sub_mode_combo.currentText().lower() == "karaoke")
        mode = "karaoke" if is_karaoke else self._sub_mode_combo.currentText().lower()

        self._global_sub_cache.update({
            "sub_enabled": self._sub_enabled_cb.isChecked() or is_karaoke,
            "sub_font": self._sub_font_edit.text().strip() or "Arial",
            "sub_font_size": self._sub_size_spin.value(),
            "sub_bold": self._sub_bold_cb.isChecked(),
            "sub_primary_color": pri_hex,
            "sub_outline_color": out_hex,
            "sub_outline_width": self._sub_outline_spin.value(),
            "sub_shadow": self._sub_shadow_spin.value(),
            "sub_margin_v": self._sub_margin_spin.value(),
            "sub_mode": mode,
            "sub_karaoke_color": kara_hex,
            "sub_max_chars": self._sub_maxchars_spin.value(),
        })
        target_name = PRESET_DISPLAY_NAMES.get(self._active_target, self._active_target)
        QMessageBox.information(
            self, "Default Updated",
            f"Successfully applied styling from '{target_name}' as the Global Default."
        )

    def _reset_current_preset(self):
        """Reset the currently active preset to registry defaults."""
        if self._active_target == "global":
            QMessageBox.information(self, "Global Default", "To reset all settings to defaults, use 'Reset All' at the bottom.")
            return
        self._reset_preset_from_registry(self._active_target)

    def _reset_preset_from_registry(self, preset_name: str):
        """Restore preset subtitle styling from master_presets_registry.json."""
        from app.storage.settings_manager import get_master_presets_registry_path
        registry_path = get_master_presets_registry_path()
        if not registry_path or not registry_path.exists():
            return
        try:
            reg = json.loads(registry_path.read_text(encoding="utf-8"))
            if preset_name in reg:
                vf = reg[preset_name].get("video_forge", {})
                if preset_name in self._presets_cache:
                    p = self._presets_cache[preset_name]
                    p["subtitle_font"] = vf.get("subtitle_font", "Arial")
                    p["subtitle_font_size"] = vf.get("subtitle_font_size", 72)
                    p["subtitle_bold"] = vf.get("subtitle_bold", True)
                    p["subtitle_primary_color"] = vf.get("subtitle_primary_color", "&H00FFFFFF")
                    p["subtitle_karaoke_color"] = vf.get("subtitle_karaoke_color", "&H0000FFFF")
                    p["subtitle_outline_color"] = vf.get("subtitle_outline_color", "&H00000000")
                    p["subtitle_back_color"] = vf.get("subtitle_back_color", "&H80000000")
                    p["subtitle_outline_width"] = float(vf.get("subtitle_outline_width", 3.0))
                    p["subtitle_shadow"] = float(vf.get("subtitle_shadow", 2.0))
                    p["subtitle_margin_v"] = int(vf.get("subtitle_margin_v", 80))
                    p["subtitle_mode"] = vf.get("sub_mode", "karaoke")
                    if "allowed_transitions" in vf:
                        p["allowed_transitions"] = vf["allowed_transitions"]

                    if preset_name in self._cards_map:
                        self._cards_map[preset_name].update_data(p)

                    if self._active_target == preset_name:
                        self._load_target_into_editor(preset_name)
                    disp = PRESET_DISPLAY_NAMES.get(preset_name, preset_name)
                    QMessageBox.information(self, "Preset Reset", f"'{disp}' subtitle style reset to registry defaults.")
        except Exception as e:
            QMessageBox.warning(self, "Reset Error", f"Could not reset preset: {e}")

    def _apply_preset_as_default(self, preset_name: str):
        """Set a preset card's style directly as the global default."""
        if preset_name not in self._presets_cache:
            return
        p = self._presets_cache[preset_name]
        font = p.get("subtitle_font", "Arial")
        font_size = p.get("subtitle_font_size", 72)
        bold = p.get("subtitle_bold", True)
        pri_hex = ass_to_hex(p.get("subtitle_primary_color", "&H00FFFFFF"))
        kara_hex = ass_to_hex(p.get("subtitle_karaoke_color", "&H0000FFFF"))
        out_hex = ass_to_hex(p.get("subtitle_outline_color", "&H00000000"))
        out_width = p.get("subtitle_outline_width", 3.0)
        shadow = p.get("subtitle_shadow", 1.5)
        margin_v = p.get("subtitle_margin_v", 80)
        mode = p.get("subtitle_mode", "karaoke")
        mode_str = mode.value if hasattr(mode, "value") else str(mode)

        self._global_sub_cache.update({
            "sub_enabled": True,
            "sub_font": font,
            "sub_font_size": font_size,
            "sub_bold": bold,
            "sub_primary_color": pri_hex,
            "sub_outline_color": out_hex,
            "sub_outline_width": out_width,
            "sub_shadow": shadow,
            "sub_margin_v": margin_v,
            "sub_mode": mode_str,
            "sub_karaoke_color": kara_hex,
        })
        if self._active_target == "global":
            self._load_target_into_editor("global")
        disp = PRESET_DISPLAY_NAMES.get(preset_name, preset_name)
        QMessageBox.information(
            self, "Default Updated",
            f"Successfully set '{disp}' subtitle styling as Global Default."
        )

    def _reload_all_from_registry(self):
        """Reload all 10 presets from master_presets_registry.json."""
        self.settings.reload_master_presets()
        self._load_preset_caches()
        self._refresh_cards_gallery()
        if self._active_target != "global":
            self._load_target_into_editor(self._active_target)
        QMessageBox.information(
            self, "Reloaded",
            "All master preset subtitle styles have been reloaded from master_presets_registry.json!"
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
        # Subtitles — initialize global cache and preset caches
        self._global_sub_cache = {
            "sub_enabled": s.get("sub_enabled", True),
            "sub_font": s.get("sub_font", "Arial"),
            "sub_font_size": s.get("sub_font_size", 72),
            "sub_bold": s.get("sub_bold", True),
            "sub_primary_color": s.get("sub_primary_color", "#FFFFFF"),
            "sub_outline_color": s.get("sub_outline_color", "#000000"),
            "sub_outline_width": s.get("sub_outline_width", 3.0),
            "sub_shadow": s.get("sub_shadow", 1.5),
            "sub_margin_v": s.get("sub_margin_v", 80),
            "sub_mode": s.get("sub_mode", "phrase"),
            "sub_karaoke_color": s.get("sub_karaoke_color", "#FFFF00"),
            "sub_max_chars": s.get("sub_max_chars", 42),
        }

        self._load_preset_caches()

        # Populate target combo
        self._sub_target_combo.blockSignals(True)
        self._sub_target_combo.clear()
        self._sub_target_combo.addItem("★ Global Default (All Projects)", "global")

        master_order = ["blueprint", "clay", "cobalt_impact", "cutout_collage",
                        "glass_node", "line_graphic", "money_chuck", "paint_blast", "paper_glass",
                        "phosphor_terminal", "punk_zine", "bradikinin", "final_sight",
                        "cast_venk", "rainbow_yoga", "pov_wealth", "genius_history",
                        "ink_explainer", "built_on_you", "terrain_walk", "go_documentaries",
                        "nostalgia_rock", "psych_toons"]
        for p in master_order:
            if p in self._presets_cache:
                disp = PRESET_DISPLAY_NAMES.get(p, p.replace("_", " ").title())
                self._sub_target_combo.addItem(disp, p)
        for p in self._presets_cache:
            if p not in master_order and p not in ["Fast Preview (720p)", "High Quality Archive"]:
                disp = PRESET_DISPLAY_NAMES.get(p, p)
                self._sub_target_combo.addItem(disp, p)
        self._sub_target_combo.blockSignals(False)

        # Build cards gallery
        self._refresh_cards_gallery()

        # Set default active target
        self._active_target = "global"
        self._sub_target_combo.setCurrentIndex(0)
        self._load_target_into_editor("global")

        # Advanced
        self._ffmpeg_path_edit.setText(s.get("ffmpeg_path", ""))
        self._debug_cb.setChecked(s.get("debug_mode", False))
        self._log_ffmpeg_cb.setChecked(s.get("log_ffmpeg_output", True))
        self._show_cmd_cb.setChecked(s.get("show_ffmpeg_commands", False))

    def _save(self):
        s = self.settings

        # Commit current editor fields into active target cache
        self._save_editor_to_target(self._active_target)

        g = self._global_sub_cache
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
            # Subtitles — store global settings
            "sub_enabled":              g.get("sub_enabled", True),
            "sub_font":                 g.get("sub_font", "Arial"),
            "sub_font_size":            g.get("sub_font_size", 72),
            "sub_bold":                 g.get("sub_bold", True),
            "sub_primary_color":        g.get("sub_primary_color", "#FFFFFF"),
            "sub_outline_color":        g.get("sub_outline_color", "#000000"),
            "sub_outline_width":        g.get("sub_outline_width", 3.0),
            "sub_shadow":               g.get("sub_shadow", 1.5),
            "sub_margin_v":             g.get("sub_margin_v", 80),
            "sub_mode":                 g.get("sub_mode", "phrase"),
            "sub_karaoke_color":        g.get("sub_karaoke_color", "#FFFF00"),
            "sub_max_chars":            g.get("sub_max_chars", 42),
            # Advanced
            "ffmpeg_path":              self._ffmpeg_path_edit.text().strip(),
            "debug_mode":               self._debug_cb.isChecked(),
            "log_ffmpeg_output":        self._log_ffmpeg_cb.isChecked(),
            "show_ffmpeg_commands":     self._show_cmd_cb.isChecked(),
        })

        # Apply global subtitle settings to default profile
        profile = s.get_default_profile()
        profile.subtitle_enabled       = g.get("sub_enabled", True)
        profile.subtitle_font          = g.get("sub_font", "Arial")
        profile.subtitle_font_size     = g.get("sub_font_size", 72)
        profile.subtitle_bold          = g.get("sub_bold", True)
        profile.subtitle_primary_color = hex_to_ass(g.get("sub_primary_color", "#FFFFFF"))
        profile.subtitle_outline_color = hex_to_ass(g.get("sub_outline_color", "#000000"))
        profile.subtitle_outline_width = g.get("sub_outline_width", 3.0)
        profile.subtitle_shadow        = g.get("sub_shadow", 1.5)
        profile.subtitle_margin_v      = g.get("sub_margin_v", 80)
        try:
            profile.subtitle_mode = SubtitleMode(g.get("sub_mode", "phrase").lower())
        except ValueError:
            pass
        profile.subtitle_karaoke_color = hex_to_ass(g.get("sub_karaoke_color", "#FFFF00"))
        profile.subtitle_max_chars     = g.get("sub_max_chars", 42)
        s.set("default_profile", profile.to_dict())

        # Save all presets to settings
        for name, p_dict in self._presets_cache.items():
            s._presets[name] = p_dict
        s.save()

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
