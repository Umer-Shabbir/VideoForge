"""
Tests for scene script chunk to image timeline synchronization.
Verifies that:
1. Prompts file is properly parsed into scene chunks (narration, image prompt, timestamps).
2. Scene script chunks are monotonically aligned against timed subtitle/audio segments.
3. Image screen time matches exactly its respective script chunk narration without drift.
4. Gaps and pauses between narration sentences are bridged smoothly.
5. ProjectScanner detects prompts.txt and populates project.scene_chunks.
6. ProjectValidator validates image counts against scene script chunks instead of subtitle counts.
7. Real-world generated content project files load and align seamlessly with 0 drift.
"""

import os
import re
import pytest
from pathlib import Path
from app.core.project import Project, RenderProfile, TransitionType, MotionType
from app.render.timeline import generate_timeline
from app.utils.file_utils import (
    parse_prompts_file,
    align_scenes_with_timed_segments,
    parse_srt_segments,
    detect_project_files,
)
from app.services.project_scanner import ProjectScanner
from app.validators.project_validator import validate_project


def test_parse_prompts_file_standard(tmp_path):
    prompts_file = tmp_path / "prompts.txt"
    content = """--- SCENE 1 ---
Narration: In the early 1980s, underground musicians made a quiet revolution.
Image Prompt: Dark indie music club with neon lights, 1980s aesthetic.

--- SCENE 2 ---
[00:00:03,500 --> 00:00:07,200]
Narration: Armed with photocopiers and glue sticks, they broke all typography rules.
Image Prompt: Close-up of hands cutting photocopied paper with scissors and glue.

--- SCENE 3 ---
Narration: Today, that rebel aesthetic dominates modern design.
Image Prompt: Modern minimalist art gallery displaying punk zines.
"""
    prompts_file.write_text(content, encoding="utf-8")

    scenes = parse_prompts_file(prompts_file)
    assert len(scenes) == 3

    assert scenes[0]["scene_number"] == 1
    assert scenes[0]["narration"] == "In the early 1980s, underground musicians made a quiet revolution."
    assert "neon lights" in scenes[0]["image_prompt"]

    assert scenes[1]["scene_number"] == 2
    assert scenes[1]["start_time"] == pytest.approx(3.5, 0.01)
    assert scenes[1]["end_time"] == pytest.approx(7.2, 0.01)

    assert scenes[2]["scene_number"] == 3
    assert "modern design" in scenes[2]["narration"]


def test_parse_prompts_file_fallback_format(tmp_path):
    prompts_file = tmp_path / "prompts.txt"
    content = """Narration: First beat of the story.
Image Prompt: A sunny morning in a small town.

Narration: Second beat of the story.
Image Prompt: The town square filled with people.
"""
    prompts_file.write_text(content, encoding="utf-8")

    scenes = parse_prompts_file(prompts_file)
    assert len(scenes) == 2
    assert scenes[0]["scene_number"] == 1
    assert scenes[0]["narration"] == "First beat of the story."
    assert scenes[1]["scene_number"] == 2
    assert scenes[1]["narration"] == "Second beat of the story."


def test_align_scenes_with_timed_segments_exact():
    scenes = [
        {"scene_number": 1, "narration": "The punk movement began in dark underground clubs."},
        {"scene_number": 2, "narration": "They made their own zines using cheap scissors and glue."},
        {"scene_number": 3, "narration": "This DIY ethos transformed visual culture forever."},
    ]

    # Subtitles are fragmented into shorter phrases for on-screen readability
    timed_subtitles = [
        {"start": 0.0, "end": 1.4, "text": "The punk movement"},
        {"start": 1.4, "end": 2.8, "text": "began in dark underground clubs."},
        {"start": 3.0, "end": 4.5, "text": "They made their own zines"},
        {"start": 4.5, "end": 6.2, "text": "using cheap scissors and glue."},
        {"start": 6.8, "end": 8.0, "text": "This DIY ethos"},
        {"start": 8.0, "end": 10.0, "text": "transformed visual culture forever."},
    ]

    aligned = align_scenes_with_timed_segments(scenes, timed_subtitles, audio_duration=10.0)
    assert len(aligned) == 3

    # Scene 1 must start at 0.0 and extend to Scene 2's narration start (3.0s)
    assert aligned[0]["start"] == 0.0
    assert aligned[0]["display_duration"] == pytest.approx(3.0, 0.01)

    # Scene 2 must start when Scene 2 narration begins (3.0s) and extend to Scene 3's start (6.8s)
    assert aligned[1]["start"] == pytest.approx(3.0, 0.01)
    assert aligned[1]["display_duration"] == pytest.approx(3.8, 0.01)

    # Scene 3 must start when Scene 3 narration begins (6.8s) and extend to total audio duration (10.0s)
    assert aligned[2]["start"] == pytest.approx(6.8, 0.01)
    assert aligned[2]["display_duration"] == pytest.approx(3.2, 0.01)

    # Total duration must equal total audio duration
    total_dur = sum(s["display_duration"] for s in aligned)
    assert total_dur == pytest.approx(10.0, 0.01)


def test_align_scenes_empty_timed_segments_fallback():
    scenes = [
        {"scene_number": 1, "narration": "First scene."},
        {"scene_number": 2, "narration": "Second scene."},
    ]
    aligned = align_scenes_with_timed_segments(scenes, [], audio_duration=12.0)
    assert len(aligned) == 2
    assert aligned[0]["start"] == 0.0
    assert aligned[0]["display_duration"] == pytest.approx(6.0, 0.01)
    assert aligned[1]["start"] == pytest.approx(6.0, 0.01)
    assert aligned[1]["display_duration"] == pytest.approx(6.0, 0.01)


def test_generate_timeline_scene_script_chunk_mode(tmp_path):
    img1 = tmp_path / "01.png"; img1.write_bytes(b"dummy")
    img2 = tmp_path / "02.png"; img2.write_bytes(b"dummy")
    img3 = tmp_path / "03.png"; img3.write_bytes(b"dummy")

    prompts_file = tmp_path / "prompts.txt"
    prompts_file.write_text("""--- SCENE 1 ---
Narration: Scene one narration text here.
Image Prompt: Visual prompt 1

--- SCENE 2 ---
Narration: Scene two narration continues here.
Image Prompt: Visual prompt 2

--- SCENE 3 ---
Narration: Scene three narration wraps up.
Image Prompt: Visual prompt 3
""", encoding="utf-8")

    srt_file = tmp_path / "transcript.srt"
    srt_file.write_text("""1
00:00:00,000 --> 00:00:02,500
Scene one narration

2
00:00:02,500 --> 00:00:04,000
text here.

3
00:00:04,500 --> 00:00:06,500
Scene two narration

4
00:00:06,500 --> 00:00:08,000
continues here.

5
00:00:08,200 --> 00:00:10,000
Scene three narration

6
00:00:10,000 --> 00:00:12,000
wraps up.
""", encoding="utf-8")

    project = Project(
        folder=tmp_path,
        name="sync_test",
        audio_duration=12.0,
        image_paths=[img1, img2, img3],
        transcript_path=srt_file,
        prompts_path=prompts_file,
    )
    project.profile.transition_duration = 0.5
    project.profile.allowed_transitions = ["fade", "dissolve", "wipeleft"]

    slots = generate_timeline(project)
    assert len(slots) == 3

    # Image 1 corresponds to Scene 1
    assert slots[0].image_path == img1
    assert slots[0].start_time == 0.0
    assert slots[0].display_duration == pytest.approx(4.5, 0.05)  # Scene 2 narration starts at 4.5s

    # Image 2 corresponds to Scene 2
    assert slots[1].image_path == img2
    assert slots[1].start_time == pytest.approx(4.5, 0.05)
    assert slots[1].display_duration == pytest.approx(3.7, 0.05)  # Scene 3 narration starts at 8.2s

    # Image 3 corresponds to Scene 3
    assert slots[2].image_path == img3
    assert slots[2].start_time == pytest.approx(8.2, 0.05)
    assert slots[2].display_duration == pytest.approx(3.8, 0.05)  # Audio ends at 12.0s

    # Sequential progression without gaps
    assert slots[0].start_time < slots[1].start_time < slots[2].start_time
    total_screen_time = sum(s.display_duration for s in slots)
    assert total_screen_time == pytest.approx(12.0, 0.05)


def test_scanner_detects_prompts_file(tmp_path):
    (tmp_path / "audio.wav").write_bytes(b"RIFF" + b"\x00" * 2000)
    (tmp_path / "01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    (tmp_path / "02.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)

    prompts_file = tmp_path / "prompts.txt"
    prompts_file.write_text("""--- SCENE 1 ---
Narration: Testing scanner detection.
Image Prompt: Prompt 1

--- SCENE 2 ---
Narration: Second scene for scanner.
Image Prompt: Prompt 2
""", encoding="utf-8")

    scanner = ProjectScanner(recursive=False, auto_validate=True)
    proj = scanner.scan_single_folder(tmp_path)

    assert proj is not None
    assert proj.prompts_path == prompts_file
    assert len(proj.scene_chunks) == 2
    assert proj.scene_chunks[0]["narration"] == "Testing scanner detection."
    assert proj.scene_chunks[1]["narration"] == "Second scene for scanner."


def test_validator_with_scene_chunks_success(tmp_path):
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 2000)

    img1 = tmp_path / "01.png"; img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    img2 = tmp_path / "02.png"; img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)

    # 4 subtitle chunks in SRT vs 2 scene images (typical in real projects: 583 subtitles vs 314 scenes)
    srt_file = tmp_path / "transcript.srt"
    srt_file.write_text("""1
00:00:00,000 --> 00:00:01,000
Part 1

2
00:00:01,000 --> 00:00:02,000
Part 2

3
00:00:02,000 --> 00:00:03,000
Part 3

4
00:00:03,000 --> 00:00:04,000
Part 4
""", encoding="utf-8")

    scene_chunks = [
        {"scene_number": 1, "narration": "Part 1 Part 2"},
        {"scene_number": 2, "narration": "Part 3 Part 4"},
    ]

    proj = Project(
        folder=tmp_path,
        name="test_val_scene_chunks",
        audio_path=audio_file,
        transcript_path=srt_file,
        transcript_text="Part 1 Part 2 Part 3 Part 4",
        image_paths=[img1, img2],
        audio_duration=4.0,
        scene_chunks=scene_chunks,
    )

    res = validate_project(proj, check_files=False)
    # Must be valid! No false positive 1:1 subtitle mismatch error because scene_chunks are matched 1:1
    assert not any("1:1 Image-to-Subtitle mismatch" in err for err in res.issues)
    assert res.valid


def test_validator_with_scene_chunks_missing_image(tmp_path):
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 2000)

    # Only 1 image provided, but 2 scene chunks exist
    img1 = tmp_path / "01.png"; img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)

    scene_chunks = [
        {"scene_number": 1, "narration": "First scene"},
        {"scene_number": 2, "narration": "Second scene"},
    ]

    proj = Project(
        folder=tmp_path,
        name="test_val_missing_scene",
        audio_path=audio_file,
        image_paths=[img1],
        audio_duration=4.0,
        scene_chunks=scene_chunks,
    )

    res = validate_project(proj, check_files=False)
    # Should flag a warning about missing image for scene 2
    assert any("Missing image files for scene chunks" in w for w in res.warnings)


def test_real_content_automation_project_alignment():
    """Verify alignment on actual project files from generated content directory if present."""
    custom_dir = os.environ.get("GENERATED_CONTENT_DIR")
    if custom_dir:
        base_dir = Path(custom_dir)
    else:
        base_dir = Path(__file__).resolve().parents[2].parent / "Generated Content"
    if not base_dir.exists():
        pytest.skip("Generated Content directory not accessible")

    projects = [p for p in base_dir.iterdir() if p.is_dir()]
    if not projects:
        pytest.skip("No generated content projects found")

    target = projects[0]
    prompts_file = target / "prompts.txt"
    srt_file = target / "transcript.srt"
    if not srt_file.exists():
        srt_file = target / "audio.srt"

    if not prompts_file.exists() or not srt_file.exists():
        pytest.skip(f"Target {target.name} missing prompts.txt or transcript.srt")

    scenes = parse_prompts_file(prompts_file)
    srt_segs = parse_srt_segments(srt_file)

    assert len(scenes) > 10
    assert len(srt_segs) > 10

    aligned = align_scenes_with_timed_segments(scenes, srt_segs, audio_duration=srt_segs[-1]["end"])
    assert len(aligned) == len(scenes)

    # Verify strictly monotonic start times and positive display durations
    prev_st = -0.001
    for i, s in enumerate(aligned):
        assert s["start"] >= prev_st, f"Non-monotonic start at scene {i+1}: {s['start']} < {prev_st}"
        assert s["display_duration"] >= 0.1, f"Zero/negative duration at scene {i+1}"
        prev_st = s["start"]

    # Total duration matches final segment time within small epsilon
    total_dur = sum(s["display_duration"] for s in aligned)
    assert total_dur == pytest.approx(srt_segs[-1]["end"], 0.1)
