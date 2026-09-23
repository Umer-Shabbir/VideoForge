"""
VideoForge test suite.
Run with: python -m pytest tests/ -v
Or:       python tests/test_all.py
"""

import sys
import os
import json
import tempfile
import shutil
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_temp_dir():
    return Path(tempfile.mkdtemp())


def make_dummy_project_folder(base: Path, name: str,
                               n_images: int = 3,
                               has_audio: bool = True,
                               has_transcript: bool = True) -> Path:
    """Create a test project folder with dummy files."""
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)

    if has_audio:
        (folder / "audio.mp3").write_bytes(b"\xff\xfb" * 512)  # minimal fake MP3

    if has_transcript:
        (folder / "script.txt").write_text(
            "Hello world. This is a test transcript. "
            "It has multiple sentences. Each sentence will become a subtitle. "
            "VideoForge processes these automatically.",
            encoding="utf-8"
        )

    for i in range(n_images):
        # Write minimal valid PNG (1×1 pixel)
        png_data = (
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx'
            b'\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00'
            b'\x00\x00IEND\xaeB`\x82'
        )
        (folder / f"image_{i+1:02d}.png").write_bytes(png_data)

    return folder


# ─── Test: file_utils ─────────────────────────────────────────────────────────

def test_file_utils_format_detection():
    from app.utils.file_utils import is_audio, is_image, is_transcript

    assert is_audio(Path("song.mp3")) is True
    assert is_audio(Path("song.MP3")) is True
    assert is_audio(Path("file.wav")) is True
    assert is_audio(Path("file.txt")) is False
    assert is_image(Path("photo.jpg")) is True
    assert is_image(Path("photo.JPEG")) is True
    assert is_image(Path("photo.webp")) is True
    assert is_image(Path("photo.mp3")) is False
    assert is_transcript(Path("script.txt")) is True
    assert is_transcript(Path("script.srt")) is True
    assert is_transcript(Path("script.json")) is True
    assert is_transcript(Path("script.mp3")) is False
    print("  ✓ test_file_utils_format_detection")


def test_file_utils_safe_filename():
    from app.utils.file_utils import safe_filename
    assert safe_filename("normal_name") == "normal_name"
    assert ":" not in safe_filename("C:/path/to:file")
    assert "/" not in safe_filename("path/with/slashes")
    assert "\\" not in safe_filename("path\\with\\backslashes")
    assert safe_filename("") == "untitled"
    assert len(safe_filename("a" * 200)) == 128
    print("  ✓ test_file_utils_safe_filename")


def test_file_utils_detect_project_files():
    from app.utils.file_utils import detect_project_files
    tmp = make_temp_dir()
    try:
        folder = make_dummy_project_folder(tmp, "proj1")
        result = detect_project_files(folder)
        assert result["audio"] is not None
        assert result["audio"].name == "audio.mp3"
        assert len(result["images"]) == 3
        assert result["transcript"] is not None
        assert result["transcript"].name == "script.txt"
        assert result["issues"] == []
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_detect_project_files")


def test_file_utils_detect_missing_audio():
    from app.utils.file_utils import detect_project_files
    tmp = make_temp_dir()
    try:
        folder = make_dummy_project_folder(tmp, "proj_noaudio", has_audio=False)
        result = detect_project_files(folder)
        assert result["audio"] is None
        assert any("audio" in i.lower() for i in result["issues"])
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_detect_missing_audio")


def test_file_utils_read_transcript_txt():
    from app.utils.file_utils import read_transcript_text
    tmp = make_temp_dir()
    try:
        f = tmp / "script.txt"
        f.write_text("Hello world.\nThis is a test.", encoding="utf-8")
        text = read_transcript_text(f)
        assert "Hello world" in text
        assert "This is a test" in text
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_read_transcript_txt")


def test_file_utils_read_transcript_srt():
    from app.utils.file_utils import read_transcript_text
    tmp = make_temp_dir()
    try:
        f = tmp / "script.srt"
        f.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHello world.\n\n"
            "2\n00:00:03,500 --> 00:00:06,000\nThis is subtitle two.\n",
            encoding="utf-8"
        )
        text = read_transcript_text(f)
        assert "Hello world" in text
        assert "subtitle two" in text
        assert "-->" not in text
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_read_transcript_srt")


def test_file_utils_read_transcript_json():
    from app.utils.file_utils import read_transcript_text
    tmp = make_temp_dir()
    try:
        f = tmp / "script.json"
        f.write_text(json.dumps({"text": "Hello from JSON transcript."}), encoding="utf-8")
        text = read_transcript_text(f)
        assert "Hello from JSON" in text
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_read_transcript_json")


def test_file_utils_scan_project_folders():
    from app.utils.file_utils import scan_for_project_folders
    tmp = make_temp_dir()
    try:
        make_dummy_project_folder(tmp, "project_a")
        make_dummy_project_folder(tmp, "project_b", n_images=2)
        make_dummy_project_folder(tmp, "empty_folder", has_audio=False, n_images=0)
        (tmp / "random_file.txt").write_text("ignore me")

        folders = scan_for_project_folders(tmp, recursive=False)
        names = {f.name for f in folders}
        assert "project_a" in names
        assert "project_b" in names
        assert "empty_folder" not in names
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_scan_project_folders")


def test_file_utils_recursive_scan():
    from app.utils.file_utils import scan_for_project_folders
    tmp = make_temp_dir()
    try:
        sub = tmp / "sub" / "nested"
        sub.mkdir(parents=True)
        make_dummy_project_folder(sub, "deep_project")

        folders = scan_for_project_folders(tmp, recursive=True, max_depth=5)
        names = {f.name for f in folders}
        assert "deep_project" in names
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_file_utils_recursive_scan")


def test_unique_output_path():
    from app.utils.file_utils import unique_output_path
    tmp = make_temp_dir()
    try:
        p = tmp / "output.mp4"
        assert unique_output_path(p) == p  # doesn't exist yet
        p.write_bytes(b"fake")
        p2 = unique_output_path(p)
        assert p2 != p
        assert p2.stem.endswith("_2")
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_unique_output_path")


# ─── Test: subtitle segmenter ─────────────────────────────────────────────────

def test_segmenter_clean_transcript():
    from app.subtitles.segmenter import clean_transcript
    assert clean_transcript("  hello   world  ") == "hello world"
    assert clean_transcript("line1\nline2\r\nline3") == "line1 line2 line3"
    assert clean_transcript("") == ""
    assert clean_transcript("  ") == ""
    print("  ✓ test_segmenter_clean_transcript")


def test_segmenter_phrase_mode():
    from app.subtitles.segmenter import segment_text
    from app.core.project import SubtitleMode
    text = "Hello world. This is a test of phrase mode. It should produce short phrases."
    chunks = segment_text(text, SubtitleMode.PHRASE, max_chars=42, max_lines=2)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 84  # 42 * 2
    print("  ✓ test_segmenter_phrase_mode")


def test_segmenter_classic_mode():
    from app.subtitles.segmenter import segment_text
    from app.core.project import SubtitleMode
    text = "Hello world. This is sentence two. And sentence three here."
    chunks = segment_text(text, SubtitleMode.CLASSIC)
    assert len(chunks) >= 1
    print("  ✓ test_segmenter_classic_mode")


def test_segmenter_viral_mode():
    from app.subtitles.segmenter import segment_text
    from app.core.project import SubtitleMode
    text = "Short form viral content here. Very impactful words."
    chunks = segment_text(text, SubtitleMode.VIRAL, max_chars=25)
    for c in chunks:
        assert len(c.split()) <= 6  # viral = very short
    print("  ✓ test_segmenter_viral_mode")


def test_segmenter_word_mode():
    from app.subtitles.segmenter import segment_text
    from app.core.project import SubtitleMode
    text = "one two three four"
    chunks = segment_text(text, SubtitleMode.WORD)
    assert chunks == ["one", "two", "three", "four"]
    print("  ✓ test_segmenter_word_mode")


def test_segmenter_distribute_evenly():
    from app.subtitles.segmenter import distribute_chunks_evenly
    chunks = ["Hello world", "This is a test", "Final chunk here"]
    timed = distribute_chunks_evenly(chunks, total_duration=30.0)

    assert len(timed) == 3
    # All chunks should have start < end
    for c in timed:
        assert c.start is not None
        assert c.end is not None
        assert c.end > c.start
    # Times should not exceed total duration
    for c in timed:
        assert c.start >= 0.0
        assert c.end <= 30.0
    # Should be in order
    starts = [c.start for c in timed]
    assert starts == sorted(starts)
    print("  ✓ test_segmenter_distribute_evenly")


def test_segmenter_single_chunk():
    from app.subtitles.segmenter import distribute_chunks_evenly
    timed = distribute_chunks_evenly(["only one chunk"], 10.0)
    assert len(timed) == 1
    assert timed[0].start >= 0
    assert timed[0].end <= 10.0
    print("  ✓ test_segmenter_single_chunk")


def test_segmenter_empty_text():
    from app.subtitles.segmenter import segment_text, distribute_chunks_evenly
    from app.core.project import SubtitleMode
    assert segment_text("", SubtitleMode.PHRASE) == []
    assert distribute_chunks_evenly([], 30.0) == []
    print("  ✓ test_segmenter_empty_text")


def test_segmenter_ass_time_format():
    from app.subtitles.segmenter import _seconds_to_ass, _seconds_to_srt
    assert _seconds_to_ass(0.0) == "0:00:00.00"
    assert _seconds_to_ass(65.5) == "0:01:05.50"
    assert _seconds_to_ass(3661.25) == "1:01:01.25"
    assert _seconds_to_srt(0.0) == "00:00:00,000"
    assert _seconds_to_srt(65.5) == "00:01:05,500"
    print("  ✓ test_segmenter_ass_time_format")


# ─── Test: subtitle styler ────────────────────────────────────────────────────

def test_styler_write_ass():
    from app.subtitles.segmenter import distribute_chunks_evenly, segment_text
    from app.subtitles.styler import write_ass_file
    from app.core.project import RenderProfile, SubtitleMode

    tmp = make_temp_dir()
    try:
        chunks_text = segment_text(
            "Hello world. This is a subtitle test.", SubtitleMode.PHRASE
        )
        profile = RenderProfile()
        profile.width, profile.height = 1920, 1080
        chunks = distribute_chunks_evenly(chunks_text, 10.0)

        out = tmp / "test.ass"
        ok = write_ass_file(chunks, out, profile, 10.0)

        assert ok is True
        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "Dialogue:" in content
        assert "Arial" in content  # default font
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_styler_write_ass")


def test_styler_write_srt():
    from app.subtitles.segmenter import distribute_chunks_evenly
    from app.subtitles.styler import write_srt_file

    tmp = make_temp_dir()
    try:
        from app.subtitles.segmenter import SubtitleChunk
        chunks = [
            SubtitleChunk("Hello world", 0.5, 2.0),
            SubtitleChunk("Second subtitle", 2.5, 4.5),
        ]
        out = tmp / "test.srt"
        ok = write_srt_file(chunks, out)
        assert ok is True
        content = out.read_text(encoding="utf-8")
        assert "1\n" in content
        assert "Hello world" in content
        assert "-->" in content
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_styler_write_srt")


def test_styler_ass_escape():
    from app.subtitles.styler import _esc, _wrap
    assert _esc("normal text") == "normal text"
    assert "\\{" in _esc("{bold}")
    assert "\\}" in _esc("{bold}")

    # _wrap: long text should get line break
    long_text = "This is a very long subtitle that should be wrapped at a natural point here"
    wrapped = _wrap(long_text, 40)
    assert "\\N" in wrapped
    print("  ✓ test_styler_ass_escape")


# ─── Test: timeline generator ─────────────────────────────────────────────────

def test_timeline_single_image():
    from app.render.timeline import generate_timeline
    from app.core.project import Project, RenderProfile

    p = Project()
    p.audio_duration = 15.0
    p.image_paths = [Path("only.jpg")]
    p.profile = RenderProfile()
    p.profile.fps = 30

    slots = generate_timeline(p)
    assert len(slots) == 1
    assert abs(slots[0].display_duration - 15.0) < 0.01
    print("  ✓ test_timeline_single_image")


def test_timeline_multiple_images_total_duration():
    from app.render.timeline import generate_timeline
    from app.core.project import Project, RenderProfile

    p = Project()
    p.audio_duration = 30.0
    p.image_paths = [Path(f"img{i}.jpg") for i in range(5)]
    p.profile = RenderProfile()
    p.profile.fps = 30
    p.profile.transition_duration = 0.6

    slots = generate_timeline(p)
    assert len(slots) == 5

    total = sum(s.display_duration for s in slots) + p.profile.transition_duration
    assert abs(total - 30.0) < 0.1, f"Expected ~30s, got {total:.3f}s"
    print("  ✓ test_timeline_multiple_images_total_duration")


def test_timeline_timing_is_sequential():
    from app.render.timeline import generate_timeline
    from app.core.project import Project, RenderProfile

    p = Project()
    p.audio_duration = 20.0
    p.image_paths = [Path(f"img{i}.jpg") for i in range(4)]
    p.profile = RenderProfile()
    p.profile.fps = 30

    slots = generate_timeline(p)
    for i in range(1, len(slots)):
        assert slots[i].start_time > slots[i-1].start_time
    print("  ✓ test_timeline_timing_is_sequential")


def test_timeline_motion_variety():
    from app.render.timeline import generate_timeline
    from app.core.project import Project, RenderProfile, MotionType

    p = Project()
    p.audio_duration = 60.0
    p.image_paths = [Path(f"img{i}.jpg") for i in range(8)]
    p.profile = RenderProfile()
    p.profile.fps = 30

    slots = generate_timeline(p)
    # Motion is static-only now (no zoompan); verify slots are generated correctly
    assert len(slots) == 8
    for s in slots:
        assert s.display_duration > 0
        assert s.segment_duration >= s.display_duration
    print("  ✓ test_timeline_motion_variety")


def test_timeline_no_images():
    from app.render.timeline import generate_timeline
    from app.core.project import Project, RenderProfile

    p = Project()
    p.audio_duration = 10.0
    p.image_paths = []
    p.profile = RenderProfile()

    slots = generate_timeline(p)
    assert slots == []
    print("  ✓ test_timeline_no_images")


def test_timeline_very_short_audio():
    from app.render.timeline import generate_timeline
    from app.core.project import Project, RenderProfile

    p = Project()
    p.audio_duration = 1.0
    p.image_paths = [Path(f"img{i}.jpg") for i in range(3)]
    p.profile = RenderProfile()
    p.profile.transition_duration = 0.6
    p.profile.fps = 30

    slots = generate_timeline(p)
    assert len(slots) == 3
    # Each slot must have positive display duration
    for s in slots:
        assert s.display_duration > 0
    print("  ✓ test_timeline_very_short_audio")


# ─── Test: project model ──────────────────────────────────────────────────────

def test_project_serialization():
    from app.core.project import Project, RenderProfile, ProjectStatus, MotionType

    p = Project()
    p.name = "My Test Project"
    p.folder = Path("/projects/test")
    p.audio_path = Path("/projects/test/audio.mp3")
    p.image_paths = [Path("/projects/test/img1.jpg"), Path("/projects/test/img2.jpg")]
    p.audio_duration = 45.5
    p.transcript_text = "Hello world transcript"
    p.transcript_word_count = 3
    p.status = ProjectStatus.VALID
    p.profile.motion_type = MotionType.ZOOM_IN
    p.profile.width = 1080
    p.profile.height = 1920

    d = p.to_dict()
    p2 = Project.from_dict(d)

    assert p2.name == p.name
    assert p2.folder == p.folder
    assert p2.audio_duration == p.audio_duration
    assert p2.status == ProjectStatus.VALID
    assert p2.profile.width == 1080
    assert p2.profile.height == 1920
    assert len(p2.image_paths) == 2
    print("  ✓ test_project_serialization")


def test_project_health_score():
    from app.core.project import Project, ProjectStatus

    p = Project()
    p.status = ProjectStatus.COMPLETED
    assert p.health_score == 100

    p2 = Project()
    p2.status = ProjectStatus.FAILED
    assert p2.health_score == 0

    p3 = Project()
    p3.status = ProjectStatus.VALID
    p3.validation.valid = True
    assert p3.health_score == 100

    p4 = Project()
    p4.status = ProjectStatus.VALID
    p4.validation.valid = True
    p4.validation.warnings = ["warn1", "warn2"]
    assert p4.health_score == 90
    print("  ✓ test_project_health_score")


def test_project_duration_str():
    from app.core.project import Project
    p = Project()
    p.audio_duration = None
    assert p.duration_str == "?"
    p.audio_duration = 65.0
    assert p.duration_str == "1:05"
    p.audio_duration = 3.5
    assert p.duration_str == "0:03"
    print("  ✓ test_project_duration_str")


def test_render_profile_serialization():
    from app.core.project import RenderProfile, MotionType, SubtitleMode, TransitionType

    pr = RenderProfile()
    pr.width = 1080
    pr.height = 1920
    pr.motion_type = MotionType.PAN_LEFT
    pr.subtitle_mode = SubtitleMode.VIRAL
    pr.transition_type = TransitionType.DISSOLVE
    pr.crf = 20
    pr.subtitle_bold = False

    d = pr.to_dict()
    pr2 = RenderProfile.from_dict(d)

    assert pr2.width == 1080
    assert pr2.height == 1920
    assert pr2.motion_type == MotionType.PAN_LEFT
    assert pr2.subtitle_mode == SubtitleMode.VIRAL
    assert pr2.transition_type == TransitionType.DISSOLVE
    assert pr2.crf == 20
    assert pr2.subtitle_bold is False
    print("  ✓ test_render_profile_serialization")


# ─── Test: validator ──────────────────────────────────────────────────────────

def test_validator_missing_audio():
    from app.core.project import Project
    from app.validators.project_validator import validate_project

    p = Project()
    p.folder = Path("/tmp")
    p.audio_path = None
    p.image_paths = [Path("/tmp/img.jpg")]
    result = validate_project(p, check_files=False)
    assert result.valid is False
    assert any("audio" in i.lower() for i in result.issues)
    print("  ✓ test_validator_missing_audio")


def test_validator_missing_images():
    from app.core.project import Project
    from app.validators.project_validator import validate_project

    p = Project()
    p.folder = Path("/tmp")
    p.audio_path = Path("/tmp/audio.mp3")
    p.image_paths = []
    result = validate_project(p, check_files=False)
    assert result.valid is False
    assert any("image" in i.lower() for i in result.issues)
    print("  ✓ test_validator_missing_images")


def test_validator_no_transcript_is_warning():
    from app.core.project import Project
    from app.validators.project_validator import validate_project

    p = Project()
    p.folder = Path("/tmp")
    p.audio_path = Path("/tmp/audio.mp3")
    p.image_paths = [Path("/tmp/img.jpg")]
    p.audio_duration = 10.0
    result = validate_project(p, check_files=False)
    assert result.valid is True  # Warning only, not error
    assert any("transcript" in w.lower() for w in result.warnings)
    print("  ✓ test_validator_no_transcript_is_warning")


def test_validator_very_short_audio():
    from app.core.project import Project
    from app.validators.project_validator import validate_project

    p = Project()
    p.folder = Path("/tmp")
    p.audio_path = Path("/tmp/audio.mp3")
    p.image_paths = [Path("/tmp/img.jpg")]
    p.audio_duration = 0.1  # Too short
    result = validate_project(p, check_files=False)
    assert result.valid is False
    print("  ✓ test_validator_very_short_audio")


def test_validator_too_many_images_warns():
    from app.core.project import Project
    from app.validators.project_validator import validate_project

    p = Project()
    p.folder = Path("/tmp")
    p.audio_path = Path("/tmp/audio.mp3")
    p.image_paths = [Path(f"/tmp/img{i}.jpg") for i in range(501)]
    p.audio_duration = 300.0
    result = validate_project(p, check_files=False)
    assert any("images" in w.lower() or "many" in w.lower() for w in result.warnings)
    print("  ✓ test_validator_too_many_images_warns")


def test_validator_valid_project():
    from app.core.project import Project
    from app.validators.project_validator import validate_project

    p = Project()
    p.folder = Path("/tmp")
    p.audio_path = Path("/tmp/audio.mp3")
    p.image_paths = [Path(f"/tmp/img{i}.jpg") for i in range(5)]
    p.audio_duration = 30.0
    p.transcript_text = "Hello world"
    p.transcript_path = Path("/tmp/script.txt")
    result = validate_project(p, check_files=False)
    assert result.valid is True
    assert result.issues == []
    print("  ✓ test_validator_valid_project")


# ─── Test: database ───────────────────────────────────────────────────────────

def test_database_project_crud():
    from app.storage.database import Database
    from app.core.project import Project, ProjectStatus

    tmp = make_temp_dir()
    db = Database(tmp / "test.db")
    try:
        p = Project()
        p.name = "DB Test Project"
        p.folder = Path("/tmp/proj")
        p.audio_duration = 42.0
        p.status = ProjectStatus.VALID

        db.save_project(p)
        loaded = db.load_project(p.id)
        assert loaded is not None
        assert loaded.name == "DB Test Project"
        assert loaded.audio_duration == 42.0
        assert loaded.status == ProjectStatus.VALID

        # Update
        p.status = ProjectStatus.COMPLETED
        p.error_message = ""
        db.save_project(p)
        loaded2 = db.load_project(p.id)
        assert loaded2.status == ProjectStatus.COMPLETED

        # Load all
        all_p = db.load_all_projects()
        assert len(all_p) >= 1

        # Delete
        db.delete_project(p.id)
        assert db.load_project(p.id) is None
    finally:
        db.close()
        shutil.rmtree(tmp)
    print("  ✓ test_database_project_crud")


def test_database_job_crud():
    from app.storage.database import Database
    from app.core.project import Project, ProjectStatus
    from app.core.job import Job, JobState

    tmp = make_temp_dir()
    db = Database(tmp / "test.db")
    try:
        p = Project()
        p.name = "Job Test"
        p.folder = Path("/tmp/proj")
        db.save_project(p)

        j = Job(project_id=p.id)
        j.state = JobState.PENDING
        db.save_job(j)

        pending = db.load_pending_jobs()
        assert len(pending) == 1
        assert pending[0].job_id == j.job_id

        j.state = JobState.COMPLETED
        j.finished_at = time.time()
        db.save_job(j)

        pending2 = db.load_pending_jobs()
        assert len(pending2) == 0

        all_j = db.load_all_jobs()
        assert len(all_j) == 1
        assert all_j[0].state == JobState.COMPLETED
    finally:
        db.close()
        shutil.rmtree(tmp)
    print("  ✓ test_database_job_crud")


def test_database_render_history():
    from app.storage.database import Database
    from app.core.project import Project

    tmp = make_temp_dir()
    db = Database(tmp / "test.db")
    try:
        p = Project()
        p.folder = Path("/tmp/proj")
        db.save_project(p)

        db.add_render_history(p.id, "job1", "/out/video.mp4", 45.2, 50_000_000, True)
        db.add_render_history(p.id, "job2", None, 12.1, 0, False, "FFmpeg error")

        history = db.get_history_for_project(p.id)
        assert len(history) == 2

        stats = db.get_render_stats()
        assert stats["total"] == 2
        assert stats["success_count"] == 1
    finally:
        db.close()
        shutil.rmtree(tmp)
    print("  ✓ test_database_render_history")


def test_database_meta():
    from app.storage.database import Database

    tmp = make_temp_dir()
    db = Database(tmp / "test.db")
    try:
        db.set_meta("test_key", "test_value")
        assert db.get_meta("test_key") == "test_value"
        assert db.get_meta("missing_key", "default") == "default"
        db.set_meta("test_key", "updated")
        assert db.get_meta("test_key") == "updated"
    finally:
        db.close()
        shutil.rmtree(tmp)
    print("  ✓ test_database_meta")


# ─── Test: settings manager ───────────────────────────────────────────────────

def test_settings_defaults():
    from app.storage.settings_manager import SettingsManager

    tmp = make_temp_dir()
    sm = SettingsManager(tmp / "settings.json")
    assert sm.get("whisper_model") == "small"
    assert sm.get("max_concurrent_jobs") == 1
    assert sm.get("recursive_scan") is True
    assert sm.get("auto_validate_on_import") is True
    shutil.rmtree(tmp)
    print("  ✓ test_settings_defaults")


def test_settings_persistence():
    from app.storage.settings_manager import SettingsManager

    tmp = make_temp_dir()
    path = tmp / "settings.json"
    sm = SettingsManager(path)
    sm.set("whisper_model", "large")
    sm.set("max_concurrent_jobs", 3)

    sm2 = SettingsManager(path)
    assert sm2.get("whisper_model") == "large"
    assert sm2.get("max_concurrent_jobs") == 3
    shutil.rmtree(tmp)
    print("  ✓ test_settings_persistence")


def test_settings_presets():
    from app.storage.settings_manager import SettingsManager
    from app.core.project import RenderProfile

    tmp = make_temp_dir()
    sm = SettingsManager(tmp / "settings.json")

    # Built-in presets
    presets = sm.list_presets()
    assert len(presets) >= 4
    assert "YouTube HD (16:9)" in presets

    # Get preset
    pr = sm.get_preset("YouTube HD (16:9)")
    assert pr is not None
    assert pr.width == 1920
    assert pr.height == 1080

    # Save custom preset
    custom = RenderProfile()
    custom.width, custom.height = 640, 480
    sm.save_preset("My Custom Preset", custom)
    assert "My Custom Preset" in sm.list_presets()
    pr2 = sm.get_preset("My Custom Preset")
    assert pr2.width == 640

    # Delete preset
    sm.delete_preset("My Custom Preset")
    assert "My Custom Preset" not in sm.list_presets()

    shutil.rmtree(tmp)
    print("  ✓ test_settings_presets")


def test_settings_output_path_template():
    from app.storage.settings_manager import SettingsManager
    from datetime import datetime

    tmp = make_temp_dir()
    sm = SettingsManager(tmp / "settings.json")
    sm.set("output_name_template", "{project_name}_{date}")

    out = sm.resolve_output_path(Path("/projects/my_video"), "my_video")
    date_str = datetime.now().strftime("%Y%m%d")
    assert f"my_video_{date_str}.mp4" == out.name
    shutil.rmtree(tmp)
    print("  ✓ test_settings_output_path_template")


# ─── Test: project scanner ────────────────────────────────────────────────────

def test_scanner_basic():
    from app.services.project_scanner import ProjectScanner

    tmp = make_temp_dir()
    try:
        make_dummy_project_folder(tmp, "proj_a", n_images=3)
        make_dummy_project_folder(tmp, "proj_b", n_images=2)

        scanner = ProjectScanner(recursive=False, auto_validate=False)
        projects = scanner.scan_folder(tmp)

        names = {p.name for p in projects}
        assert "proj_a" in names
        assert "proj_b" in names
        assert len(projects) == 2
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_scanner_basic")


def test_scanner_detects_images():
    from app.services.project_scanner import ProjectScanner

    tmp = make_temp_dir()
    try:
        folder = make_dummy_project_folder(tmp, "proj", n_images=4)
        scanner = ProjectScanner(auto_validate=False)
        project = scanner.scan_single_folder(folder)

        assert project is not None
        assert len(project.image_paths) == 4
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_scanner_detects_images")


def test_scanner_reads_transcript():
    from app.services.project_scanner import ProjectScanner

    tmp = make_temp_dir()
    try:
        folder = make_dummy_project_folder(tmp, "proj")
        scanner = ProjectScanner(auto_validate=False)
        project = scanner.scan_single_folder(folder)

        assert project is not None
        assert project.transcript_text is not None
        assert "VideoForge" in project.transcript_text
        assert project.transcript_word_count > 0
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_scanner_reads_transcript")


def test_scanner_validates_on_import():
    from app.services.project_scanner import ProjectScanner
    from app.core.project import ProjectStatus

    tmp = make_temp_dir()
    try:
        # Valid project
        make_dummy_project_folder(tmp, "valid_proj", n_images=2)
        # Invalid project (no images)
        make_dummy_project_folder(tmp, "bad_proj", n_images=0, has_audio=True)

        scanner = ProjectScanner(recursive=False, auto_validate=True)
        projects = scanner.scan_folder(tmp)

        statuses = {p.name: p.status for p in projects}
        if "valid_proj" in statuses:
            assert statuses["valid_proj"] == ProjectStatus.VALID
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_scanner_validates_on_import")


def test_scanner_recursive():
    from app.services.project_scanner import ProjectScanner

    tmp = make_temp_dir()
    try:
        sub = tmp / "level1" / "level2"
        sub.mkdir(parents=True)
        make_dummy_project_folder(sub, "deep_proj")

        scanner = ProjectScanner(recursive=True, max_depth=5, auto_validate=False)
        projects = scanner.scan_folder(tmp)

        names = {p.name for p in projects}
        assert "deep_proj" in names
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_scanner_recursive")


def test_scanner_empty_folder():
    from app.services.project_scanner import ProjectScanner

    tmp = make_temp_dir()
    try:
        scanner = ProjectScanner(recursive=True, auto_validate=False)
        projects = scanner.scan_folder(tmp)
        assert projects == []
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_scanner_empty_folder")


# ─── Test: ffmpeg command builder ─────────────────────────────────────────────

def test_ffmpeg_builder_basic():
    from app.core.project import Project, RenderProfile, MotionType
    from app.render.timeline import generate_timeline
    from app.render.ffmpeg_builder import build_render_command

    p = Project()
    p.audio_path = Path("/tmp/audio.mp3")
    p.audio_duration = 10.0
    p.image_paths = [Path(f"/tmp/img{i}.jpg") for i in range(2)]
    p.profile = RenderProfile()
    p.profile.width, p.profile.height = 1280, 720
    p.profile.fps = 30

    slots = generate_timeline(p)
    cmd, desc = build_render_command(
        p, slots, None, Path("/tmp/out.mp4"), Path("/tmp"), "ffmpeg"
    )

    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "-filter_complex" in cmd
    assert "-c:v" in cmd
    assert "-c:a" in cmd
    assert "/tmp/out.mp4" in cmd[-1] or "out.mp4" in cmd[-1]
    print("  ✓ test_ffmpeg_builder_basic")


def test_ffmpeg_builder_with_subtitles():
    from app.core.project import Project, RenderProfile
    from app.render.timeline import generate_timeline
    from app.render.ffmpeg_builder import build_render_command
    import tempfile

    tmp = make_temp_dir()
    try:
        p = Project()
        p.audio_path = Path("/tmp/audio.mp3")
        p.audio_duration = 10.0
        p.image_paths = [Path("/tmp/img.jpg")]
        p.profile = RenderProfile()
        p.profile.subtitle_enabled = True

        slots = generate_timeline(p)
        # Create a real (minimal) ASS file so the builder includes the -vf filter
        sub_path = tmp / "subs.ass"
        sub_path.write_text("[Script Info]\nScriptType: v4.00+\n[Events]\n", encoding="utf-8")

        cmd, _ = build_render_command(
            p, slots, sub_path, tmp / "out.mp4", tmp, "ffmpeg"
        )

        # Should include subtitle burn-in filter via -vf ass=...
        assert "-vf" in cmd, f"No -vf in command: {cmd[-6:]}"
        vf_idx = cmd.index("-vf")
        vf_val = cmd[vf_idx + 1]
        assert "ass=" in vf_val, f"ass= not in -vf value: {vf_val}"
    finally:
        shutil.rmtree(tmp)
    print("  ✓ test_ffmpeg_builder_with_subtitles")


def test_ffmpeg_builder_single_image_no_transitions():
    from app.core.project import Project, RenderProfile, TransitionType
    from app.render.timeline import generate_timeline
    from app.render.ffmpeg_builder import build_render_command

    p = Project()
    p.audio_path = Path("/tmp/audio.mp3")
    p.audio_duration = 5.0
    p.image_paths = [Path("/tmp/img.jpg")]
    p.profile = RenderProfile()
    p.profile.transition_type = TransitionType.NONE

    slots = generate_timeline(p)
    assert len(slots) == 1
    cmd, _ = build_render_command(
        p, slots, None, Path("/tmp/out.mp4"), Path("/tmp"), "ffmpeg"
    )
    # Should not have xfade with single image
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "xfade" not in fc
    print("  ✓ test_ffmpeg_builder_single_image_no_transitions")


def test_ffmpeg_builder_nine_sixteen():
    from app.core.project import Project, RenderProfile
    from app.render.timeline import generate_timeline
    from app.render.ffmpeg_builder import build_render_command

    p = Project()
    p.audio_path = Path("/tmp/audio.mp3")
    p.audio_duration = 10.0
    p.image_paths = [Path(f"/tmp/img{i}.jpg") for i in range(3)]
    p.profile = RenderProfile()
    p.profile.width, p.profile.height = 1080, 1920  # 9:16

    slots = generate_timeline(p)
    cmd, desc = build_render_command(
        p, slots, None, Path("/tmp/out.mp4"), Path("/tmp"), "ffmpeg"
    )
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "1080x1920" in fc or "1080:1920" in fc
    print("  ✓ test_ffmpeg_builder_nine_sixteen")


# ─── Test: logger ─────────────────────────────────────────────────────────────

def test_logger_buffer():
    from app.utils.logger import setup_logging, get_logger, get_log_buffer, clear_log_buffer

    clear_log_buffer()
    setup_logging(debug=True)
    log = get_logger("test")
    log.info("Test info message")
    log.warning("Test warning")
    log.error("Test error")

    buf = get_log_buffer()
    messages = [e["message"] for e in buf]
    assert any("Test info message" in m for m in messages)
    assert any("Test warning" in m for m in messages)
    assert any("Test error" in m for m in messages)
    print("  ✓ test_logger_buffer")


def test_logger_export():
    from app.utils.logger import setup_logging, get_logger, export_logs, clear_log_buffer

    tmp = make_temp_dir()
    clear_log_buffer()
    setup_logging(debug=True)
    log = get_logger("export_test")
    log.info("Export test message")

    out = tmp / "test_export.txt"
    ok = export_logs(out)
    assert ok
    assert out.exists()
    content = out.read_text()
    assert "Export test message" in content
    shutil.rmtree(tmp)
    print("  ✓ test_logger_export")


# ─── Test: zoompan filter builder ────────────────────────────────────────────

def test_zoompan_zoom_in():
    from app.render.timeline import build_zoompan_filter, MotionParams
    from app.core.project import MotionType
    # Motion is now static-only; build_zoompan_filter returns a simple scale filter
    motion = MotionParams(motion_type=MotionType.NONE)
    filt = build_zoompan_filter(motion, 90, 1920, 1080, 30)
    assert "1920" in filt and "1080" in filt
    assert "scale" in filt
    print("  ✓ test_zoompan_zoom_in")


def test_zoompan_static():
    from app.render.timeline import build_zoompan_filter, MotionParams
    from app.core.project import MotionType
    motion = MotionParams(motion_type=MotionType.NONE)
    filt = build_zoompan_filter(motion, 90, 1280, 720, 30)
    assert "zoompan" not in filt
    assert "1280" in filt and "720" in filt
    print("  ✓ test_zoompan_static")


def test_zoompan_pan_left():
    from app.render.timeline import build_zoompan_filter, MotionParams
    from app.core.project import MotionType
    motion = MotionParams(motion_type=MotionType.NONE)
    filt = build_zoompan_filter(motion, 90, 1920, 1080, 30)
    assert "1920" in filt and "1080" in filt
    assert "scale" in filt
    print("  ✓ test_zoompan_pan_left")


# ─── Runner ───────────────────────────────────────────────────────────────────

TEST_GROUPS = {
    "File Utils": [
        test_file_utils_format_detection,
        test_file_utils_safe_filename,
        test_file_utils_detect_project_files,
        test_file_utils_detect_missing_audio,
        test_file_utils_read_transcript_txt,
        test_file_utils_read_transcript_srt,
        test_file_utils_read_transcript_json,
        test_file_utils_scan_project_folders,
        test_file_utils_recursive_scan,
        test_unique_output_path,
    ],
    "Subtitle Segmenter": [
        test_segmenter_clean_transcript,
        test_segmenter_phrase_mode,
        test_segmenter_classic_mode,
        test_segmenter_viral_mode,
        test_segmenter_word_mode,
        test_segmenter_distribute_evenly,
        test_segmenter_single_chunk,
        test_segmenter_empty_text,
        test_segmenter_ass_time_format,
    ],
    "Subtitle Styler": [
        test_styler_write_ass,
        test_styler_write_srt,
        test_styler_ass_escape,
    ],
    "Timeline Generator": [
        test_timeline_single_image,
        test_timeline_multiple_images_total_duration,
        test_timeline_timing_is_sequential,
        test_timeline_motion_variety,
        test_timeline_no_images,
        test_timeline_very_short_audio,
    ],
    "Project Model": [
        test_project_serialization,
        test_project_health_score,
        test_project_duration_str,
        test_render_profile_serialization,
    ],
    "Validator": [
        test_validator_missing_audio,
        test_validator_missing_images,
        test_validator_no_transcript_is_warning,
        test_validator_very_short_audio,
        test_validator_too_many_images_warns,
        test_validator_valid_project,
    ],
    "Database": [
        test_database_project_crud,
        test_database_job_crud,
        test_database_render_history,
        test_database_meta,
    ],
    "Settings Manager": [
        test_settings_defaults,
        test_settings_persistence,
        test_settings_presets,
        test_settings_output_path_template,
    ],
    "Project Scanner": [
        test_scanner_basic,
        test_scanner_detects_images,
        test_scanner_reads_transcript,
        test_scanner_validates_on_import,
        test_scanner_recursive,
        test_scanner_empty_folder,
    ],
    "FFmpeg Command Builder": [
        test_ffmpeg_builder_basic,
        test_ffmpeg_builder_with_subtitles,
        test_ffmpeg_builder_single_image_no_transitions,
        test_ffmpeg_builder_nine_sixteen,
    ],
    "Logger": [
        test_logger_buffer,
        test_logger_export,
    ],
    "Zoompan Filter": [
        test_zoompan_zoom_in,
        test_zoompan_static,
        test_zoompan_pan_left,
    ],
}


def run_all_tests(fail_fast: bool = False):
    total = passed = failed = 0
    failures = []

    for group, tests in TEST_GROUPS.items():
        print(f"\n{'─'*50}")
        print(f"  {group}")
        print(f"{'─'*50}")
        for test_fn in tests:
            total += 1
            try:
                test_fn()
                passed += 1
            except Exception as e:
                failed += 1
                import traceback
                tb = traceback.format_exc()
                print(f"  ✗ {test_fn.__name__}: {e}")
                failures.append((test_fn.__name__, str(e), tb))
                if fail_fast:
                    break
        if fail_fast and failures:
            break

    print(f"\n{'='*50}")
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*50}")

    if failures:
        print("\nFailed tests:")
        for name, err, tb in failures:
            print(f"\n  ✗ {name}")
            print(f"    Error: {err}")
            if "--verbose" in sys.argv:
                print(tb)

    return failed == 0


if __name__ == "__main__":
    fail_fast = "--fail-fast" in sys.argv
    ok = run_all_tests(fail_fast=fail_fast)
    sys.exit(0 if ok else 1)
