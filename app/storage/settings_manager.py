"""
Settings manager: persists app-level configuration to a JSON file.
Supports presets (named render profiles) and global preferences.
"""

import json
import os
import logging
from pathlib import Path
from typing import Optional, Any
from copy import deepcopy

from app.core.project import RenderProfile, SubtitleMode, TransitionType, MotionType, FitMode

log = logging.getLogger("videoforge.settings")

DEFAULT_SETTINGS = {
    # Paths
    "ffmpeg_path": "",
    "default_output_folder": "",
    "last_import_folder": "",
    "workspace_folder": "",

    # Processing
    "max_concurrent_jobs": 1,
    "auto_validate_on_import": True,
    "auto_queue_valid_projects": False,
    "overwrite_existing": False,
    "recursive_scan": True,
    "max_scan_depth": 5,
    "skip_completed_projects": True,

    # Output naming
    "output_name_template": "{project_name}_{date}",
    "output_subfolder_template": "",  # empty = same as input folder

    # UI
    "theme": "dark",
    "window_geometry": {},
    "last_active_tab": 0,
    "show_ffmpeg_commands": False,
    "confirm_delete": True,
    "auto_open_output": False,

    # Defaults (used when creating new projects without a preset)
    "default_profile": RenderProfile().to_dict(),

    # Subtitle
    "whisper_model": "small",     # tiny, base, small, medium, large
    "whisper_device": "cpu",      # cpu or cuda
    "whisper_language": "auto",   # auto or ISO language code

    # Performance
    "enable_gpu": False,
    "ffmpeg_threads": 0,          # 0 = auto (uses all CPU cores)
    "ffmpeg_cpu_limit": 0,        # 0 = no limit; >0 = max % of CPU ffmpeg uses

    # File naming defaults (used when a project has multiple audio/script files)
    "preferred_audio_name": "",   # exact filename to prefer, e.g. "narration.mp3"
    "preferred_script_name": "",  # exact filename to prefer, e.g. "script.txt"
    "preferred_audio_keywords": "narration,voiceover,audio,voice",  # comma-separated priority keywords
    "preferred_script_keywords": "script,transcript,narration,text",

    # Subtitle style defaults
    "sub_font": "Arial",
    "sub_font_size": 72,
    "sub_bold": True,
    "sub_primary_color": "#FFFFFF",    # hex color
    "sub_outline_color": "#000000",
    "sub_outline_width": 3.0,
    "sub_shadow": 1.5,
    "sub_margin_v": 80,
    "sub_mode": "phrase",              # phrase / classic / viral / word / karaoke
    "sub_max_chars": 42,
    "sub_position": "bottom_center",   # bottom_center / bottom_left / center
    "sub_karaoke_color": "#FFFF00",    # highlight colour for karaoke mode (yellow)

    # Debug
    "debug_mode": False,
    "log_ffmpeg_output": True,

    # Session
    "reopen_last_workspace": True,
}


class SettingsManager:
    def __init__(self, settings_path: Path):
        self.settings_path = Path(settings_path)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = {}
        self._presets: dict[str, dict] = {}
        self.load()

    # ─── Core Settings ────────────────────────────────────────────────────────

    def load(self):
        """Load settings from disk, filling missing keys with defaults."""
        self._data = deepcopy(DEFAULT_SETTINGS)
        self._presets = self._default_presets()   # always start with defaults
        if self.settings_path.exists():
            try:
                text = self.settings_path.read_text(encoding="utf-8").strip()
                if text:
                    raw = json.loads(text)
                    self._deep_update(self._data, raw.get("settings", {}))
                    saved_presets = raw.get("presets", {})
                    if saved_presets:
                        self._presets = saved_presets
                log.debug(f"Settings loaded from {self.settings_path}")
            except Exception as e:
                log.error(f"Failed to load settings, using defaults: {e}")
                # keep default presets already set above
        else:
            self.save()

    def save(self):
        """Persist settings and presets to disk."""
        try:
            data = {"settings": self._data, "presets": self._presets}
            self.settings_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            log.error(f"Failed to save settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULT_SETTINGS.get(key, default))

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()

    def set_many(self, updates: dict):
        self._data.update(updates)
        self.save()

    def reset_to_defaults(self):
        self._data = deepcopy(DEFAULT_SETTINGS)
        self.save()

    def get_default_profile(self) -> RenderProfile:
        try:
            return RenderProfile.from_dict(self._data.get("default_profile", {}))
        except Exception:
            return RenderProfile()

    def set_default_profile(self, profile: RenderProfile):
        self._data["default_profile"] = profile.to_dict()
        self.save()

    # ─── Presets ──────────────────────────────────────────────────────────────

    def list_presets(self) -> list[str]:
        return list(self._presets.keys())

    def get_preset(self, name: str) -> Optional[RenderProfile]:
        if name not in self._presets:
            return None
        try:
            return RenderProfile.from_dict(self._presets[name])
        except Exception:
            return None

    def save_preset(self, name: str, profile: RenderProfile):
        self._presets[name] = profile.to_dict()
        self.save()

    def delete_preset(self, name: str):
        self._presets.pop(name, None)
        self.save()

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        if old_name not in self._presets or new_name in self._presets:
            return False
        self._presets[new_name] = self._presets.pop(old_name)
        self.save()
        return True

    def export_presets(self, path: Path) -> bool:
        try:
            path.write_text(json.dumps(self._presets, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            log.error(f"Export presets failed: {e}")
            return False

    def import_presets(self, path: Path, overwrite: bool = False) -> int:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            count = 0
            for name, profile_dict in data.items():
                if not overwrite and name in self._presets:
                    continue
                self._presets[name] = profile_dict
                count += 1
            self.save()
            return count
        except Exception as e:
            log.error(f"Import presets failed: {e}")
            return 0

    # ─── Output Path Resolution ────────────────────────────────────────────────

    def resolve_output_path(self, project_folder: Path, project_name: str) -> Path:
        """
        Determine where to write the output file for a given project.
        Uses the template from settings.
        """
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        name = self.get("output_name_template", "{project_name}_{date}")
        name = name.replace("{project_name}", project_name)
        name = name.replace("{date}", date_str)
        name = name.replace("{folder}", project_folder.name)

        # Sanitize
        from app.utils.file_utils import safe_filename
        name = safe_filename(name)

        output_folder_setting = self.get("default_output_folder", "")
        subfolder_tmpl = self.get("output_subfolder_template", "")

        if output_folder_setting:
            base = Path(output_folder_setting)
        else:
            base = project_folder

        if subfolder_tmpl:
            subfolder = subfolder_tmpl.replace("{project_name}", project_name)
            subfolder = subfolder.replace("{date}", date_str)
            base = base / subfolder

        return base / f"{name}.mp4"

    # ─── Utilities ────────────────────────────────────────────────────────────

    @staticmethod
    def _deep_update(base: dict, updates: dict):
        for k, v in updates.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                SettingsManager._deep_update(base[k], v)
            else:
                base[k] = v

    @staticmethod
    def _default_presets() -> dict:
        """Built-in presets shipped with the application."""
        presets = {}

        # YouTube / 16:9 HD
        p = RenderProfile()
        p.width, p.height = 1920, 1080
        p.fps = 30
        p.video_bitrate = "6M"
        p.crf = 20
        p.subtitle_mode = SubtitleMode.CLASSIC
        p.subtitle_font_size = 64
        p.transition_type = TransitionType.FADE
        p.motion_type = MotionType.KEN_BURNS
        presets["YouTube HD (16:9)"] = p.to_dict()

        # Reels / Shorts 9:16
        p2 = RenderProfile()
        p2.width, p2.height = 1080, 1920
        p2.fps = 30
        p2.video_bitrate = "4M"
        p2.subtitle_mode = SubtitleMode.VIRAL
        p2.subtitle_font_size = 80
        p2.subtitle_margin_v = 200
        p2.transition_type = TransitionType.FADE
        p2.motion_type = MotionType.KEN_BURNS
        presets["Reels / Shorts (9:16)"] = p2.to_dict()

        # Square Instagram
        p3 = RenderProfile()
        p3.width, p3.height = 1080, 1080
        p3.fps = 30
        p3.subtitle_mode = SubtitleMode.PHRASE
        p3.transition_type = TransitionType.DISSOLVE
        presets["Instagram Square (1:1)"] = p3.to_dict()

        # Fast preview
        p4 = RenderProfile()
        p4.width, p4.height = 1280, 720
        p4.fps = 24
        p4.video_bitrate = "2M"
        p4.crf = 28
        p4.preset_name = "ultrafast"
        p4.motion_type = MotionType.NONE
        p4.subtitle_mode = SubtitleMode.CLASSIC
        presets["Fast Preview (720p)"] = p4.to_dict()

        # High quality
        p5 = RenderProfile()
        p5.width, p5.height = 1920, 1080
        p5.fps = 30
        p5.video_bitrate = "10M"
        p5.crf = 16
        p5.preset_name = "slow"
        p5.motion_type = MotionType.KEN_BURNS
        p5.motion_intensity = 1.5
        presets["High Quality Archive"] = p5.to_dict()

        return presets


def get_app_data_dir() -> Path:
    """Return platform-appropriate app data directory."""
    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        return Path(base) / "VideoForge"
    else:
        return Path.home() / ".videoforge"
