import sys
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from app.storage.settings_manager import SettingsManager, get_app_data_dir
from app.gui.dialogs.settings_dialog import SettingsDialog, PRESET_DISPLAY_NAMES


@patch("PySide6.QtWidgets.QMessageBox.information")
@patch("PySide6.QtWidgets.QMessageBox.warning")
def test_settings_dialog_presets_display(mock_warn, mock_info):
    # Initialize QApplication if not present
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    sm = SettingsManager(get_app_data_dir() / "settings.json")
    dlg = SettingsDialog(sm)

    # 1. Verify preset cards are created for all 10 master presets
    expected_master_presets = [
        "blueprint", "clay", "cobalt_impact", "cutout_collage",
        "glass_node", "line_graphic", "paint_blast", "paper_glass",
        "phosphor_terminal", "punk_zine"
    ]

    for p in expected_master_presets:
        assert p in dlg._cards_map, f"Preset '{p}' card missing from cards map!"
        card = dlg._cards_map[p]
        assert card is not None
        assert card._preview_lbl.text() != ""
        # Verify font and colors are populated
        font = card._profile_dict.get("subtitle_font")
        assert font is not None and font != "", f"Preset '{p}' has empty font!"
        assert "karaoke" in card._preview_lbl.text().lower()

    # 2. Verify target combo contains global and all master presets
    combo_items = [dlg._sub_target_combo.itemData(i) for i in range(dlg._sub_target_combo.count())]
    assert "global" in combo_items
    for p in expected_master_presets:
        assert p in combo_items

    # 3. Test selecting a preset into editor
    dlg._select_preset_for_edit("blueprint")
    assert dlg._active_target == "blueprint"
    assert dlg._sub_font_edit.text() == dlg._presets_cache["blueprint"]["subtitle_font"]

    # 4. Test editing a preset updates card in real time
    dlg._sub_font_edit.setText("Impact")
    dlg._on_editor_changed()
    assert dlg._presets_cache["blueprint"]["subtitle_font"] == "Impact"
    assert "Impact" in dlg._cards_map["blueprint"]._font_spec_lbl.text()

    # 5. Test resetting preset from registry restores Consolas
    dlg._reset_preset_from_registry("blueprint")
    assert dlg._presets_cache["blueprint"]["subtitle_font"] == "Consolas"
    assert "Consolas" in dlg._cards_map["blueprint"]._font_spec_lbl.text()
    assert dlg._sub_font_edit.text() == "Consolas"

    dlg.close()
