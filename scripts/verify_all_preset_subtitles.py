"""
End-to-end verification script:
Generates ASS subtitle files for all 11 presets and validates their styling,
typography, uppercase handling, and kinetic animation tags.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.project import Project, RenderProfile
from app.subtitles.segmenter import SubtitleChunk
from app.services.project_scanner import sync_project_preset_styling
from app.subtitles.styler import write_ass_file
from app.storage.settings_manager import SettingsManager

PRESET_EXPECTATIONS = {
    "blueprint": {
        "font": "Consolas",
        "size": 52,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H0000E6FF",
        "spacing": 1.5,
    },
    "clay": {
        "font": "Trebuchet MS",
        "size": 54,
        "uppercase": False,
        "animation": "bounce",
        "karaoke_color": "&H00907BFF",
        "spacing": 0.5,
    },
    "cobalt_impact": {
        "font": "Impact",
        "size": 62,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H0000A2FF",
        "spacing": 1.0,
    },
    "cutout_collage": {
        "font": "Courier New",
        "size": 50,
        "uppercase": False,
        "animation": "box",
        "karaoke_color": "&H002828E6",
        "spacing": 0.8,
    },
    "glass_node": {
        "font": "Segoe UI",
        "size": 52,
        "uppercase": False,
        "animation": "glow",
        "karaoke_color": "&H00FFF000",
        "spacing": 1.2,
    },
    "line_graphic": {
        "font": "Bahnschrift",
        "size": 52,
        "uppercase": False,
        "animation": "pop",
        "karaoke_color": "&H0003B7FF",
        "spacing": 1.2,
    },
    "paint_blast": {
        "font": "Impact",
        "size": 60,
        "uppercase": True,
        "animation": "bounce",
        "karaoke_color": "&H0000FFF4",
        "spacing": 0.5,
    },
    "paper_glass": {
        "font": "Franklin Gothic Medium",
        "size": 52,
        "uppercase": True,
        "animation": "glow",
        "karaoke_color": "&H0042B8E5",
        "spacing": 1.8,
    },
    "phosphor_terminal": {
        "font": "Lucida Console",
        "size": 50,
        "uppercase": True,
        "animation": "glow",
        "karaoke_color": "&H00E8FFE0",
        "spacing": 1.5,
    },
    "punk_zine": {
        "font": "Impact",
        "size": 64,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H002A2AFF",
        "spacing": 0.5,
    },
    "money_chuck": {
        "font": "Impact",
        "size": 60,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H0076E600",
        "spacing": 1.0,
    },
    "bradikinin": {
        "font": "Lucida Console",
        "size": 50,
        "uppercase": True,
        "animation": "glow",
        "karaoke_color": "&H0000FF66",
        "spacing": 1.2,
    },
    "final_sight": {
        "font": "Bahnschrift",
        "size": 54,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H0033FF00",
        "spacing": 1.0,
    },
    "cast_venk": {
        "font": "Georgia",
        "size": 52,
        "uppercase": False,
        "animation": "glow",
        "karaoke_color": "&H002E4BFF",
        "spacing": 0.8,
    },
    "rainbow_yoga": {
        "font": "Trebuchet MS",
        "size": 54,
        "uppercase": False,
        "animation": "bounce",
        "karaoke_color": "&H0033B3FF",
        "spacing": 0.6,
    },
    "pov_wealth": {
        "font": "Franklin Gothic Medium",
        "size": 52,
        "uppercase": False,
        "animation": "pop",
        "karaoke_color": "&H0027BD4D",
        "spacing": 1.0,
    },
    "genius_history": {
        "font": "Cinzel",
        "size": 58,
        "uppercase": True,
        "animation": "pop",
        "karaoke_color": "&H0016B8FF",
        "spacing": 1.2,
    },
    "ink_explainer": {
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

}

def verify():
    repo_root = Path(__file__).resolve().parent.parent
    settings_candidates = [
        repo_root / "settings.json",
    ]
    from app.storage.settings_manager import get_app_data_dir
    settings_candidates.append(get_app_data_dir() / "settings.json")

    chosen_settings = next((p for p in settings_candidates if p.is_file()), get_app_data_dir() / "settings.json")
    settings = SettingsManager(chosen_settings)
    sample_chunks = [
        SubtitleChunk(
            text="Unlocking the secret to unstoppable momentum",
            start=0.5,
            end=3.5,
            words=["Unlocking", "the", "secret", "to", "unstoppable", "momentum"],
            word_starts=[0.5, 1.0, 1.2, 1.8, 2.0, 2.8],
            word_ends=[1.0, 1.2, 1.8, 2.0, 2.8, 3.5],
        )
    ]

    out_dir = repo_root / "_test_subtitles"
    out_dir.mkdir(parents=True, exist_ok=True)

    passed_all = True
    print("=" * 70)
    print("VERIFYING UNIQUE SUBTITLE STYLES FOR ALL 17 PRESETS")
    print("=" * 70)

    for slug, expected in PRESET_EXPECTATIONS.items():
        proj = Project(folder=out_dir / f"dummy_{slug}", name=f"test_{slug}")
        proj.preset_name = slug
        synced = sync_project_preset_styling(proj, settings)
        if not synced:
            print(f"[FAIL] {slug}: sync_project_preset_styling returned False!")
            passed_all = False
            continue

        pr = proj.profile
        ass_path = out_dir / f"{slug}_subtitles.ass"
        write_ass_file(sample_chunks, ass_path, pr, total_duration=5.0)

        if not ass_path.exists():
            print(f"[FAIL] {slug}: ASS file was not created!")
            passed_all = False
            continue

        content = ass_path.read_text(encoding="utf-8")
        errors = []

        # Check Font
        if expected["font"] not in content:
            errors.append(f"Font '{expected['font']}' missing from ASS file")

        # Check Font Size
        if f",{expected['size']}," not in content:
            errors.append(f"Font size '{expected['size']}' missing from ASS Style line")

        # Check Spacing
        spacing_tag = f",{expected['spacing']:.1f},"
        if spacing_tag not in content:
            errors.append(f"Letter spacing '{expected['spacing']}' missing from ASS Style line")

        # Check Uppercase
        if expected["uppercase"]:
            if "UNLOCKING" not in content or "MOMENTUM" not in content:
                errors.append("Expected uppercase text in dialogue events")
        else:
            if "Unlocking" not in content:
                errors.append("Expected preserved case text in dialogue events")

        # Check Animation tags
        anim = expected["animation"]
        if anim == "pop" and r"\fscx118" not in content:
            errors.append("Pop animation tag r'\\fscx118' missing")
        elif anim == "bounce" and r"\fscy125" not in content:
            errors.append("Bounce animation tag r'\\fscy125' missing")
        elif anim == "glow" and r"\bord4.5" not in content:
            errors.append("Glow animation tag r'\\bord4.5' missing")
        elif anim == "box" and r"\fscx112" not in content:
            errors.append("Box animation tag r'\\fscx112' missing")

        # Check Karaoke Highlight Color
        # Note: ASS hex colors can be &H00BBGGRR or &HBBGGRR
        exp_col = expected["karaoke_color"].upper().replace("&H00", "").replace("&H", "")
        if exp_col not in content.upper():
            errors.append(f"Karaoke color '{expected['karaoke_color']}' missing from ASS events")

        if errors:
            print(f"[FAIL] {slug}:")
            for err in errors:
                print(f"    - {err}")
            passed_all = False
        else:
            print(f"[PASS] {slug:<18} -> Font: {expected['font']:<22} Size: {expected['size']}pt  Anim: {expected['animation']:<6} Upper: {str(expected['uppercase']):<5} Color: {expected['karaoke_color']}")

    print("=" * 70)
    if passed_all:
        print("ALL 17 PRESETS VALIDATED SUCCESSFULLY! Unique styles fully verified.")
    else:
        print("SOME PRESET CHECKS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    verify()
