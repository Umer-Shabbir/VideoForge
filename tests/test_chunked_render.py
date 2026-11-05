"""
Tests for chunked slideshow rendering.
Verifies that projects with > 20 images render properly without hitting
Windows command-line length limits or FFmpeg version errors.
"""

from pathlib import Path
from app.render.renderer import _get_slot_chunks, _get_non_overlapping_chunks, render_project
from app.utils.ffmpeg_utils import check_ffmpeg_ready, find_ffmpeg
from tests.test_all import make_temp_dir


def test_get_slot_chunks_partitioning():
    # <= chunk_size should be 1 chunk
    assert _get_slot_chunks(1, 20) == [(0, 0)]
    assert _get_slot_chunks(5, 20) == [(0, 4)]
    assert _get_slot_chunks(20, 20) == [(0, 19)]
    assert _get_slot_chunks(21, 20) == [(0, 20)]

    # 22 slots -> (0, 21) because remaining 1 slot is merged
    assert _get_slot_chunks(22, 20) == [(0, 21)]

    # 23 slots -> [(0, 20), (20, 22)]
    c23 = _get_slot_chunks(23, 20)
    assert len(c23) == 2
    assert c23[0] == (0, 20)
    assert c23[1] == (20, 22)

    # 109 slots
    c109 = _get_slot_chunks(109, 20)
    assert c109[0] == (0, 20)
    assert c109[-1] == (100, 108)
    for i in range(len(c109) - 1):
        assert c109[i][1] == c109[i + 1][0]  # overlap by 1 boundary slot


def test_get_non_overlapping_chunks_partitioning():
    # <= chunk_size should be 1 chunk
    assert _get_non_overlapping_chunks(1, 20) == [(0, 0)]
    assert _get_non_overlapping_chunks(5, 20) == [(0, 4)]
    assert _get_non_overlapping_chunks(20, 20) == [(0, 19)]
    assert _get_non_overlapping_chunks(21, 20) == [(0, 20)]

    # 22 slots -> [(0, 19), (20, 21)]
    c22 = _get_non_overlapping_chunks(22, 20)
    assert len(c22) == 2
    assert c22[0] == (0, 19)
    assert c22[1] == (20, 21)

    # 23 slots -> [(0, 19), (20, 22)]
    c23 = _get_non_overlapping_chunks(23, 20)
    assert len(c23) == 2
    assert c23[0] == (0, 19)
    assert c23[1] == (20, 22)

    # 218 slots (user's project)
    c218 = _get_non_overlapping_chunks(218, 20)
    assert len(c218) == 11
    assert c218[0] == (0, 19)
    assert c218[-1] == (200, 217)
    # verify non-overlapping and contiguous
    for i in range(len(c218) - 1):
        assert c218[i][1] + 1 == c218[i + 1][0]
    total_slots = sum(end - start + 1 for start, end in c218)
    assert total_slots == 218


def test_chunked_render_integration():
    ok, _ = check_ffmpeg_ready()
    if not ok:
        return

    import wave, array, math
    from scripts.create_examples import _write_minimal_png
    from app.services.project_scanner import ProjectScanner
    from app.core.project import TransitionType

    tmp = make_temp_dir()
    proj_dir = tmp / "chunked_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # Audio file (3 seconds)
    wav_path = proj_dir / "audio.wav"
    sample_rate = 16000
    n_samples = int(sample_rate * 3.0)
    samples = array.array('h', [
        int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(n_samples)
    ])
    with wave.open(str(wav_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    # Create 22 images to force chunking with chunk_size=20
    img_dir = proj_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i in range(23):
        _write_minimal_png(img_dir / f"img_{i:03d}.png")

    scanner = ProjectScanner(auto_validate=True)
    project = scanner.scan_single_folder(proj_dir)
    assert project is not None
    assert project.image_count == 23

    out_file = tmp / "chunked_output.mp4"
    project.profile.width = 320
    project.profile.height = 240
    project.profile.fps = 15
    project.profile.crf = 35
    project.profile.preset_name = "ultrafast"
    project.profile.transition_type = TransitionType.FADE
    project.profile.transition_duration = 0.05
    project.profile.subtitle_enabled = False

    result = render_project(project, output_path=out_file, overwrite=True)
    assert result.success, f"Render failed: {result.error}"
    assert out_file.exists()
    assert out_file.stat().st_size > 1024


def test_chunked_render_with_subtitles():
    ok, _ = check_ffmpeg_ready()
    if not ok:
        return

    import wave, array, math
    from scripts.create_examples import _write_minimal_png
    from app.services.project_scanner import ProjectScanner
    from app.core.project import TransitionType

    tmp = make_temp_dir()
    proj_dir = tmp / "chunked_proj_sub"
    proj_dir.mkdir(parents=True, exist_ok=True)

    wav_path = proj_dir / "audio.wav"
    sample_rate = 16000
    n_samples = int(sample_rate * 3.0)
    samples = array.array('h', [
        int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(n_samples)
    ])
    with wave.open(str(wav_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    (proj_dir / "script.txt").write_text("Hello chunked rendering with subtitles", encoding="utf-8")

    img_dir = proj_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i in range(23):
        _write_minimal_png(img_dir / f"img_{i:03d}.png")

    scanner = ProjectScanner(auto_validate=True)
    project = scanner.scan_single_folder(proj_dir)
    assert project is not None
    assert project.image_count == 23

    out_file = tmp / "chunked_output_sub.mp4"
    project.profile.width = 320
    project.profile.height = 240
    project.profile.fps = 15
    project.profile.crf = 35
    project.profile.preset_name = "ultrafast"
    project.profile.transition_type = TransitionType.FADE
    project.profile.transition_duration = 0.05
    project.profile.subtitle_enabled = True

    result = render_project(project, output_path=out_file, overwrite=True)
    assert result.success, f"Render failed: {result.error}"
    assert out_file.exists()
    assert out_file.stat().st_size > 1024


def test_chunked_render_no_transitions():
    """
    Verify that rendering >20 images with transition_duration=0 (or TransitionType.NONE)
    uses non-overlapping chunks and the concat filter without hanging or erroring.
    """
    ok, _ = check_ffmpeg_ready()
    if not ok:
        return

    import wave, array, math
    from scripts.create_examples import _write_minimal_png
    from app.services.project_scanner import ProjectScanner
    from app.core.project import TransitionType

    tmp = make_temp_dir()
    proj_dir = tmp / "chunked_proj_notrans"
    proj_dir.mkdir(parents=True, exist_ok=True)

    wav_path = proj_dir / "audio.wav"
    sample_rate = 16000
    n_samples = int(sample_rate * 3.0)
    samples = array.array('h', [
        int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(n_samples)
    ])
    with wave.open(str(wav_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    img_dir = proj_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i in range(23):
        _write_minimal_png(img_dir / f"img_{i:03d}.png")

    scanner = ProjectScanner(auto_validate=True)
    project = scanner.scan_single_folder(proj_dir)
    assert project is not None
    assert project.image_count == 23

    out_file = tmp / "chunked_output_notrans.mp4"
    project.profile.width = 320
    project.profile.height = 240
    project.profile.fps = 15
    project.profile.crf = 35
    project.profile.preset_name = "ultrafast"
    project.profile.transition_type = TransitionType.NONE
    project.profile.transition_duration = 0.0
    project.profile.subtitle_enabled = False

    result = render_project(project, output_path=out_file, overwrite=True)
    assert result.success, f"Render failed: {result.error}"
    assert out_file.exists()
    assert out_file.stat().st_size > 1024


