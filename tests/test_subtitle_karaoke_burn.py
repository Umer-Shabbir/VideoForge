"""
Unit tests verifying subtitle burning and karaoke mode fixes.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.core.project import Project, RenderProfile, SubtitleMode, ProjectStatus
from app.core.app_state import AppState
from app.core.queue_manager import _apply_subtitle_defaults
from app.utils.file_utils import parse_srt_segments, detect_project_files
from app.subtitles.aligner import align_subtitles


def test_parse_srt_segments(tmp_path: Path):
    srt_content = (
        "1\n"
        "00:00:01,000 --> 00:00:03,500\n"
        "Hello <i>world</i>!\n\n"
        "2\n"
        "00:00:04,000 --> 00:00:06,250\n"
        "Second subtitle line.\n"
    )
    srt_file = tmp_path / "test.srt"
    srt_file.write_text(srt_content, encoding="utf-8")

    segments = parse_srt_segments(srt_file)
    assert len(segments) == 2
    assert segments[0]["start"] == 1.0
    assert segments[0]["end"] == 3.5
    assert segments[0]["text"] == "Hello world!"
    assert segments[1]["start"] == 4.0
    assert segments[1]["end"] == 6.25
    assert segments[1]["text"] == "Second subtitle line."


def test_detect_project_files_prefers_timed_srt(tmp_path: Path):
    (tmp_path / "audio.wav").write_bytes(b"dummy")
    (tmp_path / "script.txt").write_text("Plain script text", encoding="utf-8")
    (tmp_path / "transcript.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n", encoding="utf-8")
    (tmp_path / "img1.png").write_bytes(b"dummy")

    detected = detect_project_files(tmp_path)
    assert detected["transcript"] is not None
    assert detected["transcript"].name == "transcript.srt"


def test_queue_project_preserves_karaoke_and_enables_subtitles():
    project = Project(
        name="test_proj",
        folder=Path("/dummy"),
        audio_path=Path("/dummy/audio.wav"),
        image_paths=[Path("/dummy/1.png")],
        transcript_text="Test transcript",
    )
    project.status = ProjectStatus.VALID
    project.profile.subtitle_mode = SubtitleMode.KARAOKE
    project.profile.subtitle_enabled = False  # Previously would remain False

    state = AppState.instance()
    state.settings = MagicMock()
    state.settings.get.side_effect = lambda k, d=None: {
        "sub_mode": "phrase",
        "sub_enabled": True,
        "sub_karaoke_color": "#FFFF00",
        "skip_completed_projects": False,
    }.get(k, d)
    state.settings.resolve_output_path.return_value = Path("/dummy/out.mp4")
    state.queue = MagicMock()
    state.queue.add_project.return_value = MagicMock()

    success = state.queue_project(project)
    assert success is True
    assert project.profile.subtitle_mode == SubtitleMode.KARAOKE
    assert project.profile.subtitle_enabled is True


def test_apply_subtitle_defaults_preserves_karaoke():
    project = Project(name="test")
    project.profile.subtitle_mode = SubtitleMode.KARAOKE
    project.profile.subtitle_enabled = False

    settings_mock = MagicMock()
    settings_mock.get.side_effect = lambda k, d="": {
        "sub_mode": "phrase",
        "sub_enabled": True,
        "sub_font": "Arial",
        "sub_karaoke_color": "#FFFF00",
    }.get(k, d)

    _apply_subtitle_defaults(project, settings_mock)
    assert project.profile.subtitle_mode == SubtitleMode.KARAOKE
    assert project.profile.subtitle_enabled is True


def test_align_subtitles_uses_pretimed_srt(tmp_path: Path):
    srt_file = tmp_path / "transcript.srt"
    srt_file.write_text(
        "1\n"
        "00:00:00,000 --> 00:00:02,000\n"
        "Hello world this is a test.\n",
        encoding="utf-8"
    )
    project = Project(
        name="srt_test",
        folder=tmp_path,
        transcript_path=srt_file,
        transcript_text="Hello world this is a test.",
        audio_duration=2.0,
    )
    project.profile.subtitle_mode = SubtitleMode.KARAOKE
    project.profile.subtitle_enabled = True

    chunks = align_subtitles(project)
    assert len(chunks) > 0
    assert chunks[0].start is not None
    assert chunks[0].end is not None
    assert len(chunks[0].word_starts) == len(chunks[0].words)
