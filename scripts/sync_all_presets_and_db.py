r"""
Synchronize master preset subtitle styles into:
1. Local settings.json (if present)
2. %APPDATA%\VideoForge\settings.json
3. %APPDATA%\VideoForge\videoforge.db (all 11 existing projects)

Ensures every preset receives its unique, professional subtitle typography and ASS styling.
"""

import os
import sys
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage.settings_manager import get_master_presets_registry_path, get_app_data_dir

def run_sync():
    # 1. Load Master Presets Registry
    registry_path = get_master_presets_registry_path()
    if not registry_path:
        print("ERROR: master_presets_registry.json not found!")
        return

    print(f"Loading master presets registry from {registry_path}...")
    reg_data = json.loads(registry_path.read_text(encoding="utf-8"))

    # Map presets to profile dictionaries
    preset_profiles = {}
    for slug, item in reg_data.items():
        vf = item.get("video_forge", {})
        sub_mode = vf.get("sub_mode", "karaoke").lower()
        if sub_mode == "phrase":
            sm = "phrase"
        elif sub_mode == "viral":
            sm = "viral"
        elif sub_mode == "karaoke":
            sm = "karaoke"
        else:
            sm = "classic"

        sub_pos = vf.get("sub_position", "bottom_center")
        if sub_pos == "center":
            margin_v = int(vf.get("subtitle_margin_v", 500))
            alignment = 5
        else:
            margin_v = int(vf.get("subtitle_margin_v", 80))
            alignment = 2

        preset_profiles[slug] = {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "libx264",
            "crf": 20,
            "video_bitrate": "6M",
            "preset_name": "medium",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "normalize_audio": True,
            "audio_fade_in": 0.5,
            "audio_fade_out": 1.0,
            "transition_type": vf.get("allowed_transitions", ["fade"])[0],
            "transition_duration": 0.6,
            "motion_type": "ken_burns",
            "motion_intensity": 1.0,
            "fit_mode": "cover",
            "subtitle_enabled": True,
            "subtitle_mode": sm,
            "subtitle_font": vf.get("subtitle_font", "Arial"),
            "subtitle_font_size": int(vf.get("subtitle_font_size", 54)),
            "subtitle_bold": bool(vf.get("subtitle_bold", True)),
            "subtitle_italic": bool(vf.get("subtitle_italic", False)),
            "subtitle_spacing": float(vf.get("subtitle_spacing", 0.0)),
            "subtitle_uppercase": bool(vf.get("subtitle_uppercase", False)),
            "subtitle_animation": vf.get("subtitle_animation", "pop"),
            "subtitle_primary_color": vf.get("subtitle_primary_color", "&H00FFFFFF"),
            "subtitle_karaoke_color": vf.get("subtitle_karaoke_color", "&H0000FFFF"),
            "subtitle_karaoke_outline": vf.get("subtitle_karaoke_outline", ""),
            "subtitle_outline_color": vf.get("subtitle_outline_color", "&H00000000"),
            "subtitle_back_color": vf.get("subtitle_back_color", "&H80000000"),
            "subtitle_outline_width": float(vf.get("subtitle_outline_width", 3.0)),
            "subtitle_shadow": float(vf.get("subtitle_shadow", 2.0)),
            "subtitle_border_style": int(vf.get("subtitle_border_style", 1)),
            "subtitle_margin_v": margin_v,
            "subtitle_alignment": alignment,
            "subtitle_max_chars": int(vf.get("subtitle_max_chars", 36)),
            "allowed_transitions": vf.get("allowed_transitions", ["fade", "dissolve"]),
        }

    # 2. Update settings.json files
    settings_targets = [
        get_app_data_dir() / "settings.json",
        ROOT / "settings.json",
    ]

    for s_path in settings_targets:
        if s_path.exists():
            try:
                data = json.loads(s_path.read_text(encoding="utf-8"))
                presets = data.setdefault("presets", {})
                for name, prof in preset_profiles.items():
                    presets[name] = prof

                # Ensure default_profile in settings has proper transition duration & motion
                def_prof = data.setdefault("settings", {}).setdefault("default_profile", {})
                def_prof["transition_duration"] = 0.6
                def_prof["motion_type"] = "ken_burns"
                def_prof["motion_intensity"] = 1.0

                s_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Updated presets & settings in {s_path}")
            except Exception as e:
                print(f"Error updating {s_path}: {e}")

    # 3. Update videoforge.db projects
    db_path = get_app_data_dir() / "videoforge.db"
    if not db_path.exists():
        print(f"No database found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Reset any interrupted running jobs back to pending, and processing projects back to queued
    c.execute("UPDATE jobs SET state = 'pending' WHERE state = 'running'")
    c.execute("UPDATE projects SET status = 'queued' WHERE status = 'processing'")

    rows = c.execute("SELECT id, name, folder, data_json FROM projects").fetchall()
    updated_count = 0

    for pid, name, folder, data_json in rows:
        p_dict = json.loads(data_json)
        preset_name = p_dict.get("preset_name", "")

        # Try resolve from project.json if missing
        if not preset_name or preset_name.lower() == "default":
            pj = Path(folder) / "project.json"
            if not pj.exists():
                pj = Path(folder) / "metadata.json"
            if pj.exists():
                try:
                    meta = json.loads(pj.read_text(encoding="utf-8"))
                    preset_name = meta.get("preset_name", "")
                except Exception:
                    pass

        if preset_name in preset_profiles:
            p_dict["preset_name"] = preset_name
            profile = p_dict.setdefault("profile", {})
            target_profile = preset_profiles[preset_name]

            # Update all subtitle typography, transitions, and motion styling keys
            for k, v in target_profile.items():
                if k.startswith("subtitle_") or k in (
                    "allowed_transitions", "transition_type", "transition_duration",
                    "motion_type", "motion_intensity", "fit_mode"
                ):
                    profile[k] = v

            c.execute("UPDATE projects SET data_json = ? WHERE id = ?", (json.dumps(p_dict), pid))
            updated_count += 1
            print(f"[OK] Updated project '{name}' -> Preset: {preset_name} (trans: {profile.get('transition_type')} {profile.get('transition_duration')}s, motion: {profile.get('motion_type')}, font: {profile.get('subtitle_font')})")

    conn.commit()
    conn.close()
    print(f"\nDone! Successfully updated {updated_count} projects in database {db_path}.")

if __name__ == "__main__":
    run_sync()
