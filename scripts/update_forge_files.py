import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Update Video Forge/scripts/update_master_registry.py
registry_script_path = ROOT / "scripts" / "update_master_registry.py"
content = registry_script_path.read_text(encoding="utf-8")

new_preset_styles_block = '''    "ink_explainer": {
        "allowed_transitions": ["dissolve", "fade", "smoothleft", "smoothright", "radial"],
        "video_styling": "Atmospheric primal anthropological storytelling with slow macro drifts",
        "sub_mode": "karaoke",
        "sub_position": "bottom_center",
        "subtitle_font": "Georgia",
        "subtitle_font_size": 52,
        "subtitle_bold": True,
        "subtitle_italic": False,
        "subtitle_spacing": 0.8,
        "subtitle_uppercase": False,
        "subtitle_primary_color": "&H00DDEEF4",
        "subtitle_karaoke_color": "&H0028A0FF",
        "subtitle_karaoke_outline": "&H000F151C",
        "subtitle_outline_color": "&H0015181C",
        "subtitle_back_color": "&HA00D1014",
        "subtitle_outline_width": 2.8,
        "subtitle_shadow": 1.8,
        "subtitle_border_style": 1,
        "subtitle_alignment": 2,
        "subtitle_animation": "glow",
        "subtitle_margin_v": 65,
        "subtitle_max_chars": 36
    },
    "built_on_you": {
        "allowed_transitions": ["fade", "dissolve", "horzopen", "vertopen", "smoothright"],
        "video_styling": "Cinematic archival corporate documentary with 2.5D multi-plane parallax",
        "sub_mode": "karaoke",
        "sub_position": "bottom_center",
        "subtitle_font": "Franklin Gothic Medium",
        "subtitle_font_size": 54,
        "subtitle_bold": True,
        "subtitle_italic": False,
        "subtitle_spacing": 1.0,
        "subtitle_uppercase": False,
        "subtitle_primary_color": "&H00F6F9F9",
        "subtitle_karaoke_color": "&H003BB8E5",
        "subtitle_karaoke_outline": "&H00101418",
        "subtitle_outline_color": "&H00181412",
        "subtitle_back_color": "&H90100D0C",
        "subtitle_outline_width": 3.0,
        "subtitle_shadow": 1.8,
        "subtitle_border_style": 1,
        "subtitle_alignment": 2,
        "subtitle_animation": "pop",
        "subtitle_margin_v": 68,
        "subtitle_max_chars": 36
    },
    "terrain_walk": {
        "allowed_transitions": ["wipeleft", "wiperight", "circlecrop", "fade", "dissolve"],
        "video_styling": "3D topographical tactical military visualization with elevation tracking",
        "sub_mode": "karaoke",
        "sub_position": "bottom_center",
        "subtitle_font": "Consolas",
        "subtitle_font_size": 52,
        "subtitle_bold": True,
        "subtitle_italic": False,
        "subtitle_spacing": 1.5,
        "subtitle_uppercase": True,
        "subtitle_primary_color": "&H00E0FFFF",
        "subtitle_karaoke_color": "&H0000E5FF",
        "subtitle_karaoke_outline": "&H00000000",
        "subtitle_outline_color": "&H00000A05",
        "subtitle_back_color": "&HB0000000",
        "subtitle_outline_width": 3.2,
        "subtitle_shadow": 2.0,
        "subtitle_border_style": 1,
        "subtitle_alignment": 2,
        "subtitle_animation": "pop",
        "subtitle_margin_v": 65,
        "subtitle_max_chars": 34
    },
    "go_documentaries": {
        "allowed_transitions": ["smoothleft", "smoothright", "dissolve", "fade", "horzopen"],
        "video_styling": "Hyper-detailed mega-engineering 3D cutaway and isometric technical motion graphics",
        "sub_mode": "karaoke",
        "sub_position": "bottom_center",
        "subtitle_font": "Bahnschrift",
        "subtitle_font_size": 54,
        "subtitle_bold": True,
        "subtitle_italic": False,
        "subtitle_spacing": 1.2,
        "subtitle_uppercase": False,
        "subtitle_primary_color": "&H00FFFFFF",
        "subtitle_karaoke_color": "&H00FFD400",
        "subtitle_karaoke_outline": "&H000A1A24",
        "subtitle_outline_color": "&H000A141E",
        "subtitle_back_color": "&H90081018",
        "subtitle_outline_width": 2.8,
        "subtitle_shadow": 1.6,
        "subtitle_border_style": 1,
        "subtitle_alignment": 2,
        "subtitle_animation": "glow",
        "subtitle_margin_v": 65,
        "subtitle_max_chars": 36
    },
    "nostalgia_rock": {
        "allowed_transitions": ["dissolve", "fade", "smoothleft", "radial", "pixelize"],
        "video_styling": "Vintage 35mm rock-and-roll analog film retrospective with warm stage lighting",
        "sub_mode": "karaoke",
        "sub_position": "bottom_center",
        "subtitle_font": "Impact",
        "subtitle_font_size": 62,
        "subtitle_bold": True,
        "subtitle_italic": False,
        "subtitle_spacing": 0.6,
        "subtitle_uppercase": True,
        "subtitle_primary_color": "&H00E6F5FF",
        "subtitle_karaoke_color": "&H000077FF",
        "subtitle_karaoke_outline": "&H000A0505",
        "subtitle_outline_color": "&H00100808",
        "subtitle_back_color": "&HB00A0505",
        "subtitle_outline_width": 3.6,
        "subtitle_shadow": 2.5,
        "subtitle_border_style": 1,
        "subtitle_alignment": 2,
        "subtitle_animation": "bounce",
        "subtitle_margin_v": 70,
        "subtitle_max_chars": 32
    },
    "psych_toons": {
        "allowed_transitions": ["smoothleft", "smoothright", "circleopen", "fade", "dissolve"],
        "video_styling": "Clean 2D animated psychological explainer with kinetic character motion",
        "sub_mode": "karaoke",
        "sub_position": "bottom_center",
        "subtitle_font": "Trebuchet MS",
        "subtitle_font_size": 56,
        "subtitle_bold": True,
        "subtitle_italic": False,
        "subtitle_spacing": 0.5,
        "subtitle_uppercase": False,
        "subtitle_primary_color": "&H00FFFFFF",
        "subtitle_karaoke_color": "&H00F755A8",
        "subtitle_karaoke_outline": "&H0024101A",
        "subtitle_outline_color": "&H00201624",
        "subtitle_back_color": "&H80181020",
        "subtitle_outline_width": 3.0,
        "subtitle_shadow": 2.0,
        "subtitle_border_style": 1,
        "subtitle_alignment": 2,
        "subtitle_animation": "bounce",
        "subtitle_margin_v": 65,
        "subtitle_max_chars": 34
    },
'''

if '"ink_explainer":' not in content:
    target = '    "genius_history": {'
    if target in content:
        content = content.replace(target, new_preset_styles_block + target)
        registry_script_path.write_text(content, encoding="utf-8")
        print("Updated update_master_registry.py successfully!")

# 2. Update Video Forge/app/gui/dialogs/settings_dialog.py
dialog_path = ROOT / "app" / "gui" / "dialogs" / "settings_dialog.py"
d_text = dialog_path.read_text(encoding="utf-8")

# PRESET_DISPLAY_NAMES
display_names_insert = '''    "ink_explainer": "🖋️ Ink Explainer",
    "built_on_you": "🏢 Built On You",
    "terrain_walk": "🗺️ Terrain Walk",
    "go_documentaries": "🏗️ Go Documentaries",
    "nostalgia_rock": "🎸 Nostalgia Rock",
    "psych_toons": "🧠 Psych Toons",
'''
if '"ink_explainer":' not in d_text:
    d_text = d_text.replace('    "genius_history": "⚔️ Genius History",', '    "genius_history": "⚔️ Genius History",\n' + display_names_insert)

# master_order
old_order = '["blueprint", "clay", "cobalt_impact", "cutout_collage",\n                        "glass_node", "line_graphic", "money_chuck", "paint_blast", "paper_glass",\n                        "phosphor_terminal", "punk_zine", "bradikinin", "final_sight",\n                        "cast_venk", "rainbow_yoga", "pov_wealth", "genius_history"]'
new_order = '["blueprint", "clay", "cobalt_impact", "cutout_collage",\n                        "glass_node", "line_graphic", "money_chuck", "paint_blast", "paper_glass",\n                        "phosphor_terminal", "punk_zine", "bradikinin", "final_sight",\n                        "cast_venk", "rainbow_yoga", "pov_wealth", "genius_history",\n                        "ink_explainer", "built_on_you", "terrain_walk", "go_documentaries",\n                        "nostalgia_rock", "psych_toons"]'

if old_order in d_text:
    d_text = d_text.replace(old_order, new_order)

# bg_color in PresetSubtitleCard
bg_color_target = '        elif "genius_history" in self.preset_name.lower():\n            bg_color = "#1B130E"\n'
bg_color_insert = '''        elif "ink_explainer" in self.preset_name.lower():
            bg_color = "#141210"
        elif "built_on_you" in self.preset_name.lower():
            bg_color = "#121518"
        elif "terrain_walk" in self.preset_name.lower():
            bg_color = "#0B130E"
        elif "go_documentaries" in self.preset_name.lower():
            bg_color = "#0A121A"
        elif "nostalgia_rock" in self.preset_name.lower():
            bg_color = "#190E08"
        elif "psych_toons" in self.preset_name.lower():
            bg_color = "#161220"
'''

if '"ink_explainer"' not in d_text and bg_color_target in d_text:
    d_text = d_text.replace(bg_color_target, bg_color_target + bg_color_insert)

dialog_path.write_text(d_text, encoding="utf-8")
print("Updated settings_dialog.py successfully!")

# 3. Update Video Forge/scripts/verify_all_preset_subtitles.py
verify_path = ROOT / "scripts" / "verify_all_preset_subtitles.py"
v_text = verify_path.read_text(encoding="utf-8")

verify_insert = '''    "ink_explainer": {
        "font": "Georgia",
        "size": 52,
        "uppercase": False,
        "animation": "glow",
        "karaoke_color": "&H0028A0FF",
        "spacing": 0.8,
    },
    "built_on_you": {
        "font": "Franklin Gothic Medium",
        "size": 54,
        "uppercase": False,
        "animation": "pop",
        "karaoke_color": "&H003BB8E5",
        "spacing": 1.0,
    },
    "terrain_walk": {
        "font": "Consolas",
        "size": 52,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H0000E5FF",
        "spacing": 1.5,
    },
    "go_documentaries": {
        "font": "Bahnschrift",
        "size": 54,
        "uppercase": False,
        "animation": "glow",
        "karaoke_color": "&H00FFD400",
        "spacing": 1.2,
    },
    "nostalgia_rock": {
        "font": "Impact",
        "size": 62,
        "uppercase": True,
        "animation": "bounce",
        "karaoke_color": "&H000077FF",
        "spacing": 0.6,
    },
    "psych_toons": {
        "font": "Trebuchet MS",
        "size": 56,
        "uppercase": False,
        "animation": "bounce",
        "karaoke_color": "&H00F755A8",
        "spacing": 0.5,
    },
'''

if '"ink_explainer":' not in v_text:
    target_v = '    "genius_history": {\n        "font": "Cinzel",\n        "size": 58,\n        "uppercase": True,\n        "animation": "pop",\n        "karaoke_color": "&H0016B8FF",\n        "spacing": 1.2,\n    },'
    if target_v in v_text:
        v_text = v_text.replace(target_v, target_v + "\n" + verify_insert)
        verify_path.write_text(v_text, encoding="utf-8")
        print("Updated verify_all_preset_subtitles.py successfully!")

print("All Video Forge UI & Verification files aligned!")
