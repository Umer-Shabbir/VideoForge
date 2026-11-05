import pytest
from pathlib import Path
from app.core.project import Project, RenderProfile, SubtitleMode, TransitionType
from app.subtitles.segmenter import SubtitleChunk, create_chunks_from_srt_segments, align_whisper_segments
from app.subtitles.styler import write_ass_file, _ass_color_to_bbggrr, _hex_to_ass, _style_line
from app.render.timeline import generate_timeline, build_zoompan_filter
from app.render.renderer import _build_command, _xfade_chain
from app.validators.project_validator import validate_project
from app.storage.settings_manager import SettingsManager

def test_ass_color_conversion_hex_and_ass():
    # Hex format conversions
    assert _ass_color_to_bbggrr("#FFFFFF") == "FFFFFF"
    assert _ass_color_to_bbggrr("#FFFF00") == "00FFFF"  # Yellow in BBGGRR
    assert _ass_color_to_bbggrr("#FF5500") == "0055FF"  # Neon orange
    assert _ass_color_to_bbggrr("#00FFC2") == "C2FF00"  # Mint green

    # ASS format conversions
    assert _ass_color_to_bbggrr("&H00FFFFFF") == "FFFFFF"
    assert _ass_color_to_bbggrr("&H0000FFFF") == "00FFFF"

    # Hex to ASS style header format
    assert _hex_to_ass("#FFFFFF") == "&H00FFFFFF"
    assert _hex_to_ass("#FFFF00") == "&H0000FFFF"
    assert _hex_to_ass("&H00FFFFFF") == "&H00FFFFFF"

def test_karaoke_ass_events_generation(tmp_path):
    chunks = [
        SubtitleChunk(
            text="First subtitle chunk here",
            start=0.5,
            end=2.5,
            words=["First", "subtitle", "chunk", "here"],
            word_starts=[0.5, 1.0, 1.5, 2.0],
            word_ends=[1.0, 1.5, 2.0, 2.5],
        ),
        SubtitleChunk(
            text="Second subtitle chunk here",
            start=2.6,
            end=4.8,
            words=["Second", "subtitle", "chunk", "here"],
            word_starts=[2.6, 3.2, 3.8, 4.3],
            word_ends=[3.2, 3.8, 4.3, 4.8],
        )
    ]
    profile = RenderProfile()
    profile.subtitle_mode = SubtitleMode.KARAOKE
    profile.subtitle_primary_color = "#FFFFFF"
    profile.subtitle_karaoke_color = "#FFFF00"

    ass_file = tmp_path / "test_karaoke.ass"
    success = write_ass_file(chunks, ass_file, profile, total_duration=5.0)
    assert success
    content = ass_file.read_text(encoding="utf-8-sig")

    # Verify karaoke color override tags exist and are distinct
    assert r"{\1c&H00FFFF&}" in content  # Yellow highlight
    assert r"{\1c&HFFFFFF&}" in content  # White normal
    # Verify dialogue events are created per word
    assert content.count("Dialogue: 0,") == 8  # 4 words in chunk 1 + 4 words in chunk 2

def test_create_chunks_from_srt_segments():
    timed_segs = [
        {"start": 0.0, "end": 2.5, "text": "Welcome to the video"},
        {"start": 2.5, "end": 5.0, "text": "This is chunk two"},
        {"start": 5.0, "end": 8.0, "text": "And this is the final chunk"},
    ]
    chunks = create_chunks_from_srt_segments(timed_segs, audio_duration=8.5)
    assert len(chunks) == 3
    assert chunks[0].start == 0.0
    assert chunks[0].end == 2.5
    assert len(chunks[0].words) == 4
    assert len(chunks[0].word_starts) == 4
    # Last chunk stretches to audio duration
    assert chunks[-1].end == 8.5

def test_1_to_1_timeline_synchronization(tmp_path):
    img1 = tmp_path / "1.png"; img1.write_bytes(b"dummy")
    img2 = tmp_path / "2.png"; img2.write_bytes(b"dummy")
    img3 = tmp_path / "3.png"; img3.write_bytes(b"dummy")

    chunks = [
        SubtitleChunk(text="Chunk 1", start=0.0, end=3.0),
        SubtitleChunk(text="Chunk 2", start=3.0, end=7.5),
        SubtitleChunk(text="Chunk 3", start=7.5, end=11.0),
    ]

    project = Project(
        name="test_proj",
        audio_duration=11.0,
        image_paths=[img1, img2, img3]
    )
    project.profile.allowed_transitions = ["fade", "dissolve", "wipeleft"]
    project.profile.transition_duration = 0.5

    slots = generate_timeline(project, sub_chunks=chunks)
    assert len(slots) == 3
    # Check 1:1 image assignment
    assert slots[0].image_path == img1
    assert slots[1].image_path == img2
    assert slots[2].image_path == img3

    # Check timing
    assert slots[0].start_time == 0.0
    assert pytest.approx(slots[0].display_duration, 0.01) == 3.0
    assert slots[1].start_time == 3.0
    assert pytest.approx(slots[1].display_duration, 0.01) == 4.5
    assert slots[2].start_time == 7.5
    assert pytest.approx(slots[2].display_duration, 0.01) == 3.5

    # Check varied transitions across slots
    assert slots[0].transition_out == TransitionType.FADE
    assert slots[1].transition_out == TransitionType.DISSOLVE
    assert slots[2].transition_out == TransitionType.WIPE_LEFT

def test_preset_master_registry_loading():
    presets = SettingsManager._default_presets()
    for preset_name in [
        'blueprint', 'clay', 'cobalt_impact', 'cutout_collage', 'glass_node',
        'line_graphic', 'paint_blast', 'paper_glass', 'phosphor_terminal', 'punk_zine'
    ]:
        assert preset_name in presets
        p_dict = presets[preset_name]
        assert p_dict["subtitle_mode"] == "karaoke"
        assert len(p_dict.get("allowed_transitions", [])) >= 3
        assert p_dict.get("subtitle_primary_color")
        assert p_dict.get("subtitle_karaoke_color")
        assert p_dict.get("subtitle_font")

def test_1_to_1_project_validation(tmp_path):
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 2000)

    # 2 images
    img1 = tmp_path / "1.png"; img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    img2 = tmp_path / "2.png"; img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)

    # SRT with 3 chunks -> mismatch!
    srt_file = tmp_path / "transcript.srt"
    srt_content = """1
00:00:00,000 --> 00:00:02,000
Chunk 1

2
00:00:02,000 --> 00:00:04,000
Chunk 2

3
00:00:04,000 --> 00:00:06,000
Chunk 3
"""
    srt_file.write_text(srt_content, encoding="utf-8")

    proj = Project(
        folder=tmp_path,
        name="test_val",
        audio_path=audio_file,
        transcript_path=srt_file,
        transcript_text="Chunk 1 Chunk 2 Chunk 3",
        image_paths=[img1, img2],
        audio_duration=6.0
    )

    res = validate_project(proj, check_files=False)
    # Should be invalid due to 1:1 image-to-chunk mismatch (2 images vs 3 chunks)
    assert not res.valid
    assert any("1:1 Image-to-Subtitle mismatch" in err for err in res.issues)

    # Now add 3.png
    img3 = tmp_path / "3.png"; img3.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    proj.image_paths = [img1, img2, img3]
    res2 = validate_project(proj, check_files=False)
    # Now image count matches chunk count!
    assert not any("1:1 Image-to-Subtitle mismatch" in err for err in res2.issues)


def test_automatic_temp_cleanup_on_startup(tmp_path):
    from app.core.app_state import AppState
    from app.core.project import Project

    # Setup dummy project with orphaned _vf_temp
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    temp_dir = proj_dir / "_vf_temp"
    temp_dir.mkdir()
    chunk_file = temp_dir / "chunk_001.ts"
    chunk_file.write_bytes(b"\x00" * 1024 * 50) # 50 KB dummy file

    state = AppState()
    state.initialize(app_data_dir=tmp_path / "app_data")
    dummy_proj = Project(folder=proj_dir, name="my_project")
    state._projects[dummy_proj.id] = dummy_proj

    assert temp_dir.exists()
    purged_count, mb_freed = state.cleanup_orphaned_temp_dirs()
    assert purged_count >= 1
    assert not temp_dir.exists()
    assert mb_freed > 0


def test_dynamic_ken_burns_motion_filter():
    from app.render.effects import build_motion_filter
    from app.render.timeline import MotionParams
    from app.core.project import MotionType

    # Test Ken Burns Zoom In with 3.5s duration at 30 fps -> 105 frames
    mp = MotionParams(motion_type=MotionType.ZOOM_IN, intensity=1.0)
    filt = build_motion_filter(mp, fit_mode="cover", width=1920, height=1080, duration=3.5, fps=30)
    assert "zoompan=" in filt
    assert "d=105" in filt
    assert "s=1920x1080:fps=30" in filt
    assert "trim=start_frame=0:end_frame=105,setpts=PTS-STARTPTS" in filt

    # Test Pan Right
    mp_pan = MotionParams(motion_type=MotionType.PAN_RIGHT, intensity=1.5)
    filt_pan = build_motion_filter(mp_pan, fit_mode="cover", width=1920, height=1080, duration=2.0, fps=30)
    assert "pan_right" not in filt_pan # Evaluated into zoompan expression
    assert "d=60" in filt_pan
    assert "trim=start_frame=0:end_frame=60" in filt_pan

    # Test MotionType.NONE returns standard fit filter without zoompan
    mp_none = MotionParams(motion_type=MotionType.NONE)
    filt_none = build_motion_filter(mp_none, fit_mode="cover", width=1920, height=1080, duration=2.0, fps=30)
    assert "zoompan=" not in filt_none
    assert "scale=" in filt_none


def test_enhanced_animated_subtitle_styles():
    from app.subtitles.styler import _build_karaoke_line

    words = ["viral", "animated", "captions"]
    normal_tag = r"{\1c&HFFFFFF&}"
    highlight_tag = r"{\1c&H00FFFF&}"

    # 1. Pop animation
    line_pop = _build_karaoke_line(words, active_idx=0, normal_tag=normal_tag, highlight_tag=highlight_tag, animation="pop")
    assert r"\fscx118" in line_pop
    assert r"\t(0,90,\fscx100\fscy100)" in line_pop
    assert "viral" in line_pop
    assert highlight_tag + " " not in line_pop

    # 2. Bounce animation
    line_bounce = _build_karaoke_line(words, active_idx=1, normal_tag=normal_tag, highlight_tag=highlight_tag, animation="bounce")
    assert r"\fscy125" in line_bounce
    assert r"\t(0,60,\fscy90)" in line_bounce
    assert "animated" in line_bounce

    # 3. Glow animation
    line_glow = _build_karaoke_line(words, active_idx=2, normal_tag=normal_tag, highlight_tag=highlight_tag, animation="glow")
    assert r"\bord4.5" in line_glow
    assert "captions" in line_glow

    # 4. None animation produces clean standard tags
    line_none = _build_karaoke_line(words, active_idx=0, normal_tag=normal_tag, highlight_tag=highlight_tag, animation="none")
    assert r"\fscx" not in line_none
    assert r"\bord4.5" not in line_none


def test_preset_column_and_project_preset_serialization():
    from app.core.project import Project, RenderProfile

    p = Project(name="test_preset_proj")
    p.preset_name = "dark_curiosity"
    p.profile.subtitle_animation = "pop"

    d = p.to_dict()
    assert d["preset_name"] == "dark_curiosity"
    assert d["profile"]["subtitle_animation"] == "pop"

    restored = Project.from_dict(d)
    assert restored.preset_name == "dark_curiosity"
    assert restored.profile.subtitle_animation == "pop"


def test_force_align_project(tmp_path):
    from app.core.project import Project
    from app.subtitles.aligner import force_align_project

    audio_p = tmp_path / "audio.wav"
    audio_p.write_bytes(b"RIFF" + b"\x00" * 4000)
    script_p = tmp_path / "script.txt"
    script_p.write_text("In 1973 hip hop was invented in the West Bronx.", encoding="utf-8")

    proj = Project(
        folder=tmp_path,
        name="hip_hop_origins",
        audio_path=audio_p,
        audio_duration=6.0,
        transcript_text="In 1973 hip hop was invented in the West Bronx."
    )

    out_srt = force_align_project(proj)
    assert out_srt is not None
    assert out_srt.exists()
    assert proj.transcript_path == out_srt
    assert proj.transcript_word_count == 10
    content = out_srt.read_text(encoding="utf-8")
    assert "-->" in content
    assert "1973" in content


def test_force_align_project_backups_existing_srt(tmp_path):
    from app.core.project import Project
    from app.subtitles.aligner import force_align_project

    audio_p = tmp_path / "audio.wav"
    audio_p.write_bytes(b"RIFF" + b"\x00" * 4000)
    script_p = tmp_path / "script.txt"
    script_p.write_text("Sentence one. Sentence two.", encoding="utf-8")

    # Create existing transcript.srt (e.g. from TTS)
    existing_srt = tmp_path / "transcript.srt"
    existing_srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nOriginal TTS SRT\n", encoding="utf-8")

    proj = Project(
        folder=tmp_path,
        name="test_proj",
        audio_path=audio_p,
        audio_duration=4.0,
        transcript_text="Sentence one. Sentence two."
    )

    out_srt = force_align_project(proj)
    assert out_srt == existing_srt
    bak_srt = tmp_path / "transcript.srt.bak"
    assert bak_srt.exists()
    assert "Original TTS SRT" in bak_srt.read_text(encoding="utf-8")


def test_x264_preset_sanitization():
    from app.core.project import RenderProfile, VALID_X264_PRESETS

    # Style preset name should never be passed to FFmpeg -preset
    for style_name in ["blueprint", "clay", "punk_zine", "cobalt_impact", "money_chuck"]:
        profile = RenderProfile.from_dict({"preset_name": style_name})
        x264_preset = profile.get_x264_preset()
        assert x264_preset in VALID_X264_PRESETS
        assert x264_preset != style_name

    # Valid x264 preset names should be preserved
    profile_slow = RenderProfile.from_dict({"preset_name": "slow"})
    assert profile_slow.get_x264_preset() == "slow"

    profile_fast = RenderProfile.from_dict({"x264_preset": "faster"})
    assert profile_fast.get_x264_preset() == "faster"


def test_100_percent_image_visibility_transitions_and_effects():
    from app.render.effects import build_motion_filter
    from app.render.timeline import build_zoompan_filter, MotionParams
    from app.core.project import MotionType

    # 1. ZOOM_IN: smooth zoom in toward center
    mp_zi = MotionParams(motion_type=MotionType.ZOOM_IN, intensity=1.0)
    filt_zi = build_motion_filter(mp_zi, fit_mode="cover", width=1920, height=1080, duration=3.0, fps=30)
    assert "zoompan=" in filt_zi
    assert "min(zoom+" in filt_zi
    assert "1920x1080" in filt_zi

    # 2. ZOOM_OUT: smooth zoom out toward 1.0
    mp_zo = MotionParams(motion_type=MotionType.ZOOM_OUT, intensity=1.0)
    filt_zo = build_motion_filter(mp_zo, fit_mode="cover", width=1920, height=1080, duration=3.0, fps=30)
    assert "zoompan=" in filt_zo
    assert "max(zoom-" in filt_zo

    # 3. PAN_RIGHT: smooth pan from left to right with orthogonal center
    mp_pr = MotionParams(motion_type=MotionType.PAN_RIGHT, intensity=1.0)
    filt_pr = build_motion_filter(mp_pr, fit_mode="cover", width=1920, height=1080, duration=3.0, fps=30)
    assert "zoompan=" in filt_pr
    assert "(ih-ih/zoom)/2" in filt_pr

    # 4. PAN_LEFT: smooth pan from right to left with orthogonal center
    mp_pl = MotionParams(motion_type=MotionType.PAN_LEFT, intensity=1.0)
    filt_pl = build_motion_filter(mp_pl, fit_mode="cover", width=1920, height=1080, duration=3.0, fps=30)
    assert "zoompan=" in filt_pl
    assert "1.0-on/" in filt_pl
    assert "(ih-ih/zoom)/2" in filt_pl

    # 5. PAN_DOWN: smooth pan from top to bottom
    mp_pd = MotionParams(motion_type=MotionType.PAN_DOWN, intensity=1.0)
    filt_pd = build_motion_filter(mp_pd, fit_mode="cover", width=1920, height=1080, duration=3.0, fps=30)
    assert "zoompan=" in filt_pd
    assert "(iw-iw/zoom)/2" in filt_pd

    # 6. PAN_UP: smooth pan from bottom to top
    mp_pu = MotionParams(motion_type=MotionType.PAN_UP, intensity=1.0)
    filt_pu = build_motion_filter(mp_pu, fit_mode="cover", width=1920, height=1080, duration=3.0, fps=30)
    assert "zoompan=" in filt_pu
    assert "(iw-iw/zoom)/2" in filt_pu

    # 7. Contain fit mode with motion must use decrease + pad to preserve 100% of image without cutting edges
    filt_contain = build_motion_filter(mp_pr, fit_mode="contain", width=1920, height=1080, duration=3.0, fps=30)
    assert "force_original_aspect_ratio=decrease" in filt_contain
    assert "pad=" in filt_contain

    # 8. timeline.py build_zoompan_filter must also support smooth continuous movement
    filt_tl_zi = build_zoompan_filter(mp_zi, 90, 1920, 1080, 30)
    assert "min(zoom+" in filt_tl_zi

    filt_tl_pl = build_zoompan_filter(mp_pl, 90, 1920, 1080, 30)
    assert "1.0-on/90" in filt_tl_pl


