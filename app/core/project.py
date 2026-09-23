"""
Project model: represents a single video-generation project (one folder).
Immutable after creation; state changes happen through the database/queue.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional
import json
import time


class ProjectStatus(Enum):
    DISCOVERED = "discovered"     # Found by scanner, not yet validated
    VALID = "valid"               # Passed validation
    INVALID = "invalid"           # Failed validation
    QUEUED = "queued"             # In the render queue
    PROCESSING = "processing"     # Currently rendering
    COMPLETED = "completed"       # Successfully rendered
    FAILED = "failed"             # Render failed
    CANCELLED = "cancelled"       # Cancelled by user
    SKIPPED = "skipped"           # Skipped (output already exists)


class TransitionType(str, Enum):
    FADE = "fade"
    WIPE_LEFT = "wipeleft"
    WIPE_RIGHT = "wiperight"
    SLIDE_LEFT = "slideleft"
    SLIDE_RIGHT = "slideright"
    SLIDE_UP = "slideup"
    SLIDE_DOWN = "slidedown"
    CIRCLECROP = "circlecrop"
    DISSOLVE = "dissolve"
    PIXELIZE = "pixelize"
    RADIAL = "radial"
    HBLUR = "hblur"
    SQUEEZE_V = "squeezev"
    SQUEEZE_H = "squeezeh"
    ZOOM_IN = "zoomin"
    NONE = "none"


class MotionType(str, Enum):
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"
    KEN_BURNS = "ken_burns"
    NONE = "none"


class FitMode(str, Enum):
    COVER = "cover"       # Fill frame, crop overflow
    CONTAIN = "contain"   # Letterbox/pillarbox
    BLUR_BG = "blur_bg"   # Blurred background fill
    STRETCH = "stretch"   # Stretch to fill (not recommended)


class SubtitleMode(str, Enum):
    CLASSIC = "classic"         # Full sentences, 1-2 lines
    PHRASE = "phrase"           # Short phrase chunks
    VIRAL = "viral"             # Short-form social style, large
    WORD = "word"               # One word at a time (highlight)
    KARAOKE = "karaoke"         # Moving word highlight (viral + highlight current word)


class AspectRatio(str, Enum):
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    SQUARE = "1:1"
    INSTAGRAM = "4:5"
    CUSTOM = "custom"


@dataclass
class RenderProfile:
    """All rendering settings for a project. Can be from a preset or per-project override."""
    # Output
    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    video_bitrate: str = "4M"
    audio_bitrate: str = "192k"
    crf: int = 23
    preset_name: str = "medium"  # FFmpeg encoding preset
    output_format: str = "mp4"

    # Layout
    aspect_ratio: str = "16:9"
    fit_mode: FitMode = FitMode.COVER

    # Motion
    motion_type: MotionType = MotionType.KEN_BURNS
    motion_intensity: float = 1.0  # 0.0 to 2.0

    # Transitions
    transition_type: TransitionType = TransitionType.FADE
    transition_duration: float = 0.6

    # Subtitles
    subtitle_enabled: bool = True
    subtitle_mode: SubtitleMode = SubtitleMode.PHRASE
    subtitle_font: str = "Arial"
    subtitle_font_size: int = 72
    subtitle_primary_color: str = "&H00FFFFFF"   # ASS format: AABBGGRR
    subtitle_outline_color: str = "&H00000000"
    subtitle_back_color: str = "&H80000000"
    subtitle_bold: bool = True
    subtitle_outline_width: float = 3.0
    subtitle_shadow: float = 1.5
    subtitle_margin_v: int = 80     # Vertical margin from bottom
    subtitle_max_chars: int = 42    # Max chars per line
    subtitle_max_lines: int = 2
    subtitle_karaoke_color: str = "&H0000FFFF"  # Highlight colour for karaoke mode (ASS AABBGGRR: yellow)
    subtitle_karaoke_outline: str = "&H00000000" # Outline of the highlight word

    # Watermark / Branding
    watermark_enabled: bool = False
    watermark_path: str = ""
    watermark_position: str = "top_right"  # top_left, top_right, bottom_left, bottom_right
    watermark_opacity: float = 0.7
    watermark_scale: float = 0.1   # Fraction of output width

    # Intro / Outro
    intro_enabled: bool = False
    intro_image: str = ""
    intro_duration: float = 2.0
    outro_enabled: bool = False
    outro_image: str = ""
    outro_duration: float = 2.0

    # Audio
    normalize_audio: bool = True
    audio_fade_in: float = 0.5
    audio_fade_out: float = 1.0

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Enum):
                d[k] = v.value
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RenderProfile":
        obj = cls()
        for k, v in data.items():
            if hasattr(obj, k):
                attr = getattr(obj, k)
                if isinstance(attr, Enum):
                    try:
                        setattr(obj, k, type(attr)(v))
                    except ValueError:
                        pass
                else:
                    setattr(obj, k, v)
        return obj

    def resolution_str(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass
class ValidationResult:
    valid: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def add_error(self, msg: str, fix: str = ""):
        self.issues.append(msg)
        if fix:
            self.suggestions.append(fix)

    def add_warning(self, msg: str):
        self.warnings.append(msg)


@dataclass
class RenderMetrics:
    """Statistics collected during and after rendering."""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    render_time_seconds: Optional[float] = None
    output_size_bytes: int = 0
    ffmpeg_command: str = ""
    progress_pct: float = 0.0
    subtitle_count: int = 0
    frame_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class Project:
    """
    A single project: one folder with images, audio, and transcript.
    This is the central data object; all processing references it.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    folder: Path = field(default_factory=Path)
    name: str = ""

    # Detected files
    audio_path: Optional[Path] = None
    transcript_path: Optional[Path] = None
    image_paths: list[Path] = field(default_factory=list)

    # Detected metadata
    audio_duration: Optional[float] = None
    transcript_text: Optional[str] = None
    transcript_word_count: int = 0

    # Status
    status: ProjectStatus = ProjectStatus.DISCOVERED
    validation: ValidationResult = field(default_factory=ValidationResult)

    # Settings
    profile: RenderProfile = field(default_factory=RenderProfile)

    # Output
    output_folder: Optional[Path] = None
    output_path: Optional[Path] = None

    # Metrics
    metrics: RenderMetrics = field(default_factory=RenderMetrics)

    # Housekeeping
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: str = ""
    notes: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = self.folder.name if self.folder else "Untitled"

    @property
    def image_count(self) -> int:
        return len(self.image_paths)

    @property
    def is_ready(self) -> bool:
        return self.status in (ProjectStatus.VALID, ProjectStatus.QUEUED)

    @property
    def duration_str(self) -> str:
        if self.audio_duration is None:
            return "?"
        m = int(self.audio_duration // 60)
        s = int(self.audio_duration % 60)
        return f"{m}:{s:02d}"

    @property
    def status_display(self) -> str:
        return self.status.value.capitalize()

    @property
    def health_score(self) -> int:
        """0–100 health score for display."""
        if self.status == ProjectStatus.COMPLETED:
            return 100
        if self.status == ProjectStatus.FAILED:
            return 0
        if not self.validation.valid:
            return max(0, 30 - len(self.validation.issues) * 10)
        score = 100
        score -= len(self.validation.warnings) * 5
        return max(0, score)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "folder": str(self.folder),
            "name": self.name,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "transcript_path": str(self.transcript_path) if self.transcript_path else None,
            "image_paths": [str(p) for p in self.image_paths],
            "audio_duration": self.audio_duration,
            "transcript_text": self.transcript_text,
            "transcript_word_count": self.transcript_word_count,
            "status": self.status.value,
            "profile": self.profile.to_dict(),
            "output_folder": str(self.output_folder) if self.output_folder else None,
            "output_path": str(self.output_path) if self.output_path else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_message": self.error_message,
            "notes": self.notes,
            "validation_issues": self.validation.issues,
            "validation_warnings": self.validation.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        p = cls()
        p.id = data.get("id", str(uuid.uuid4()))
        p.folder = Path(data.get("folder", ""))
        p.name = data.get("name", "")
        p.audio_path = Path(data["audio_path"]) if data.get("audio_path") else None
        p.transcript_path = Path(data["transcript_path"]) if data.get("transcript_path") else None
        p.image_paths = [Path(x) for x in data.get("image_paths", [])]
        p.audio_duration = data.get("audio_duration")
        p.transcript_text = data.get("transcript_text")
        p.transcript_word_count = data.get("transcript_word_count", 0)
        p.status = ProjectStatus(data.get("status", ProjectStatus.DISCOVERED.value))
        if "profile" in data:
            p.profile = RenderProfile.from_dict(data["profile"])
        p.output_folder = Path(data["output_folder"]) if data.get("output_folder") else None
        p.output_path = Path(data["output_path"]) if data.get("output_path") else None
        p.created_at = data.get("created_at", time.time())
        p.updated_at = data.get("updated_at", time.time())
        p.error_message = data.get("error_message", "")
        p.notes = data.get("notes", "")
        p.validation.issues = data.get("validation_issues", [])
        p.validation.warnings = data.get("validation_warnings", [])
        p.validation.valid = not p.validation.issues
        return p
