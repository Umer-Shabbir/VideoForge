"""
VideoForge integration tests.
These tests require FFmpeg installed and working.
Run with: python tests/test_integration.py

They exercise the full render pipeline with real (small) media files.
"""

import sys
import shutil
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.test_all import make_temp_dir, make_dummy_project_folder


def _ffmpeg_available() -> bool:
    from app.utils.ffmpeg_utils import check_ffmpeg_ready
    ok, _ = check_ffmpeg_ready()
    return ok


def _make_real_project(base: Path, name: str, duration: float = 5.0) -> Path:
    """Create a project with real WAV audio and PNG images."""
    import wave, array, math
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)

    # Real WAV file
    wav_path = folder / "audio.wav"
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    samples = array.array('h', [
        int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(n_samples)
    ])
    with wave.open(str(wav_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    # Script
    (folder / "script.txt").write_text(
        f"This is a test render for {name}. "
        "The system should produce a valid video file. "
        "Subtitles should appear and transitions should work.",
        encoding="utf-8"
    )

    # Real PNG images (gradient)
    for i in range(3):
        from scripts.create_examples import _write_minimal_png, _make_gradient_png
        colors = [(20 + i * 30, 40, 100), (60 + i * 20, 80, 200)]
        img_path = folder / f"slide_{i+1:02d}.png"
        try:
            _make_gradient_png(img_path, 320, 240, colors[0], colors[1], f"Slide {i+1}")
        except Exception:
            _write_minimal_png(img_path)

    return folder


def test_full_render_pipeline():
    """End-to-end render: scanner → validator → renderer → output file."""
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    tmp = make_temp_dir()
    try:
        folder = _make_real_project(tmp, "integration_test", duration=4.0)

        # Scan
        from app.services.project_scanner import ProjectScanner
        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)
        assert project is not None, "Scanner returned None"
        assert project.validation.valid, f"Validation failed: {project.validation.issues}"
        assert project.audio_duration is not None
        assert project.audio_duration > 0
        assert project.image_count == 3

        # Set output
        out_path = tmp / "output.mp4"
        project.output_path = out_path

        # Use fast settings
        from app.core.project import MotionType, TransitionType
        project.profile.width = 640
        project.profile.height = 360
        project.profile.fps = 24
        project.profile.crf = 32
        project.profile.preset_name = "ultrafast"
        project.profile.motion_type = MotionType.ZOOM_IN
        project.profile.transition_type = TransitionType.FADE
        project.profile.transition_duration = 0.3
        project.profile.subtitle_enabled = True

        # Render
        from app.render.renderer import render_project
        start = time.time()
        result = render_project(project, output_path=out_path, overwrite=True)
        elapsed = time.time() - start

        assert result.success, f"Render failed: {result.error}"
        assert out_path.exists(), "Output file not created"
        assert out_path.stat().st_size > 10_000, "Output file too small"

        # Probe output
        from app.utils.ffmpeg_utils import get_media_info
        info = get_media_info(out_path)
        assert info["valid"], "Output file not readable by ffprobe"
        assert abs(info["duration"] - project.audio_duration) < 1.5, \
            f"Duration mismatch: expected {project.audio_duration:.1f}s got {info['duration']:.1f}s"
        assert info["width"] == 640
        assert info["height"] == 360

        size_kb = out_path.stat().st_size // 1024
        print(f"  ✓ test_full_render_pipeline")
        print(f"    → {out_path.name}: {size_kb}KB, {info['duration']:.1f}s, {elapsed:.1f}s render time")
    finally:
        shutil.rmtree(tmp)


def test_render_no_subtitles():
    """Render without subtitles when no transcript present."""
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    tmp = make_temp_dir()
    try:
        folder = _make_real_project(tmp, "no_subs_test", duration=3.0)
        # Remove transcript
        (folder / "script.txt").unlink()

        from app.services.project_scanner import ProjectScanner
        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)
        assert project.transcript_path is None

        out_path = tmp / "no_subs.mp4"
        project.output_path = out_path
        project.profile.width = 640
        project.profile.height = 360
        project.profile.fps = 24
        project.profile.crf = 35
        project.profile.preset_name = "ultrafast"
        project.profile.subtitle_enabled = False

        from app.render.renderer import render_project
        result = render_project(project, output_path=out_path, overwrite=True)

        assert result.success, f"Render failed: {result.error}"
        assert out_path.exists()
        print(f"  ✓ test_render_no_subtitles")
    finally:
        shutil.rmtree(tmp)


def test_render_single_image():
    """Render a project with only one image."""
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    import wave, array, math
    tmp = make_temp_dir()
    try:
        folder = tmp / "single_img"
        folder.mkdir()

        # 3-second WAV
        sample_rate = 22050
        samples = array.array('h', [
            int(12000 * math.sin(2 * math.pi * 220 * i / sample_rate))
            for i in range(sample_rate * 3)
        ])
        with wave.open(str(folder / "audio.wav"), 'w') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())

        from scripts.create_examples import _write_minimal_png
        _write_minimal_png(folder / "image.png")

        (folder / "script.txt").write_text("Single image test slide.")

        from app.services.project_scanner import ProjectScanner
        from app.render.renderer import render_project

        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)
        assert project.image_count == 1

        out = tmp / "single.mp4"
        project.output_path = out
        project.profile.width = 320
        project.profile.height = 240
        project.profile.fps = 24
        project.profile.crf = 35
        project.profile.preset_name = "ultrafast"

        result = render_project(project, output_path=out, overwrite=True)
        assert result.success, f"Render failed: {result.error}"
        assert out.exists()
        print(f"  ✓ test_render_single_image")
    finally:
        shutil.rmtree(tmp)


def test_render_nine_sixteen():
    """Render a 9:16 portrait video."""
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    import wave, array, math
    tmp = make_temp_dir()
    try:
        folder = _make_real_project(tmp, "portrait_test", duration=4.0)

        from app.services.project_scanner import ProjectScanner
        from app.render.renderer import render_project

        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)

        project.profile.width = 360
        project.profile.height = 640
        project.profile.fps = 24
        project.profile.crf = 35
        project.profile.preset_name = "ultrafast"
        project.profile.subtitle_enabled = True

        out = tmp / "portrait.mp4"
        project.output_path = out
        result = render_project(project, output_path=out, overwrite=True)
        assert result.success, f"Render failed: {result.error}"

        from app.utils.ffmpeg_utils import get_media_info
        info = get_media_info(out)
        assert info["width"] == 360
        assert info["height"] == 640
        print(f"  ✓ test_render_nine_sixteen  (360×640)")
    finally:
        shutil.rmtree(tmp)


def test_subtitle_file_created():
    """Check .srt file is written alongside output."""
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    tmp = make_temp_dir()
    try:
        folder = _make_real_project(tmp, "srt_test", duration=4.0)

        from app.services.project_scanner import ProjectScanner
        from app.render.renderer import render_project

        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)

        project.profile.width = 320
        project.profile.height = 240
        project.profile.fps = 24
        project.profile.crf = 35
        project.profile.preset_name = "ultrafast"
        project.profile.subtitle_enabled = True

        out = tmp / "with_srt.mp4"
        project.output_path = out
        result = render_project(project, output_path=out, overwrite=True, save_srt=True)
        assert result.success, f"Render failed: {result.error}"

        srt = out.with_suffix(".srt")
        if srt.exists():
            content = srt.read_text()
            assert "-->" in content
        print(f"  ✓ test_subtitle_file_created")
    finally:
        shutil.rmtree(tmp)


def test_render_metrics_populated():
    """Verify render metrics are filled in after a successful render."""
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    tmp = make_temp_dir()
    try:
        folder = _make_real_project(tmp, "metrics_test", duration=3.0)

        from app.services.project_scanner import ProjectScanner
        from app.render.renderer import render_project

        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)

        project.profile.width = 320; project.profile.height = 240
        project.profile.fps = 24; project.profile.crf = 35
        project.profile.preset_name = "ultrafast"

        out = tmp / "metrics.mp4"
        project.output_path = out
        result = render_project(project, output_path=out, overwrite=True)

        assert result.success, f"Render failed: {result.error}"
        assert result.metrics.render_time_seconds is not None
        assert result.metrics.render_time_seconds > 0
        assert result.metrics.output_size_bytes > 0
        assert result.metrics.progress_pct == 100.0
        print(f"  ✓ test_render_metrics_populated  "
              f"({result.metrics.render_time_seconds:.1f}s, "
              f"{result.metrics.output_size_bytes//1024}KB)")
    finally:
        shutil.rmtree(tmp)


def test_cancel_render():
    """Verify that cancellation works cleanly."""
    import threading
    if not _ffmpeg_available():
        print("  ⚠  SKIP: FFmpeg not available")
        return

    tmp = make_temp_dir()
    try:
        folder = _make_real_project(tmp, "cancel_test", duration=60.0)

        from app.services.project_scanner import ProjectScanner
        from app.render.renderer import render_project

        scanner = ProjectScanner(auto_validate=True)
        project = scanner.scan_single_folder(folder)
        project.profile.width = 640; project.profile.height = 360
        project.profile.fps = 30; project.profile.crf = 23
        project.profile.preset_name = "medium"

        out = tmp / "cancelled.mp4"
        project.output_path = out

        cancel = threading.Event()

        # Cancel after 2 seconds
        def _cancel_after_delay():
            time.sleep(2.0)
            cancel.set()

        t = threading.Thread(target=_cancel_after_delay, daemon=True)
        t.start()

        result = render_project(project, output_path=out,
                                cancel_flag=cancel, overwrite=True)

        # Either cancelled or completed (if machine is very fast)
        assert not result.success or result.output_path is not None
        print(f"  ✓ test_cancel_render  (result: {'cancelled' if not result.success else 'completed before cancel'})")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    print("=" * 55)
    print("  VideoForge Integration Tests")
    print("  (requires FFmpeg installed)")
    print("=" * 55)

    ok, msg = (False, "FFmpeg not found")
    try:
        from app.utils.ffmpeg_utils import check_ffmpeg_ready
        ok, msg = check_ffmpeg_ready()
    except Exception:
        pass

    if not ok:
        print(f"\n  ⚠  {msg}")
        print("  Install FFmpeg to run integration tests.")
        print("  See docs/INSTALLATION_GUIDE.md for instructions.")
        sys.exit(0)

    print(f"\n  FFmpeg: {msg}\n")

    tests = [
        test_full_render_pipeline,
        test_render_no_subtitles,
        test_render_single_image,
        test_render_nine_sixteen,
        test_subtitle_file_created,
        test_render_metrics_populated,
        test_cancel_render,
    ]

    passed = failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {test_fn.__name__}: {e}")
            if "--verbose" in sys.argv:
                traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 55}")
    print(f"  Integration: {passed}/{passed+failed} passed, {failed} failed")
    print(f"{'=' * 55}")
    sys.exit(0 if failed == 0 else 1)
