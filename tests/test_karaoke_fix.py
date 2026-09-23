"""
Tests for the karaoke subtitle fix.
Run with:  python -m pytest tests/test_karaoke_fix.py -v

The karaoke implementation uses ONE Dialogue line per word per chunk.
Each line spans only that word's active time window and contains the
full chunk text with per-word colour override tags {\\1c&H<BBGGRR>&}.
No Layer 1 / base-layer stacking. No \\kf animation tags.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
from pathlib import Path

from app.subtitles.styler import (
    write_ass_file,
    _karaoke_events,
    _ass_color_to_bbggrr,
    _ass_time,
    _esc,
    _build_karaoke_line,
)
from app.subtitles.segmenter import SubtitleChunk
from app.core.project import RenderProfile, SubtitleMode


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_profile(karaoke_color="&H0000FFFF", primary_color="&H00FFFFFF"):
    p = RenderProfile()
    p.subtitle_mode = SubtitleMode.KARAOKE
    p.subtitle_karaoke_color = karaoke_color
    p.subtitle_primary_color = primary_color
    return p


def make_chunk(text, start, end, words=None, word_starts=None, word_ends=None):
    wl = words or text.split()
    n = len(wl)
    dur = (end - start) / n
    ws = word_starts or [start + i * dur       for i in range(n)]
    we = word_ends   or [start + (i + 1) * dur for i in range(n)]
    return SubtitleChunk(
        text=text, start=start, end=end,
        words=wl, word_starts=ws, word_ends=we,
    )


def get_dialogue(events):
    """Return only Dialogue lines from event list."""
    return [e for e in events if e.startswith("Dialogue:")]


def get_text(dialogue_line):
    """Extract the text field (field 10) from a Dialogue line."""
    return dialogue_line.split(",", 9)[9]


def get_start(dialogue_line):
    return dialogue_line.split(",")[1]


def get_end(dialogue_line):
    return dialogue_line.split(",")[2]


def get_layer(dialogue_line):
    return int(dialogue_line.split(",")[0].split(": ")[1])


# ─── _ass_color_to_bbggrr ─────────────────────────────────────────────────────

class TestAssColorToBbggrr:
    def test_full_8char(self):
        assert _ass_color_to_bbggrr("&H00FFFF00") == "FFFF00"

    def test_6char_no_alpha(self):
        assert _ass_color_to_bbggrr("&H00FFFF") == "00FFFF"

    def test_yellow_ass(self):
        # Yellow: &H0000FFFF → AABBGGRR → drop AA → BBGGRR = 00FFFF
        assert _ass_color_to_bbggrr("&H0000FFFF") == "00FFFF"

    def test_white_ass(self):
        assert _ass_color_to_bbggrr("&H00FFFFFF") == "FFFFFF"

    def test_strips_trailing_ampersand(self):
        assert _ass_color_to_bbggrr("&H00FFFFFF&") == "FFFFFF"


# ─── _karaoke_events — core structure ────────────────────────────────────────

class TestKaraokeEvents:

    def test_one_line_per_word(self):
        """New approach: exactly N Dialogue lines for N words (one per word)."""
        profile = make_profile()
        chunk = make_chunk("hello world foo", 0.0, 3.0)
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        # 3 words → 3 lines (one per word)
        assert len(d) == 3

    def test_all_lines_layer_0(self):
        """All lines are Layer 0 — no stacking, no doubling."""
        profile = make_profile()
        chunk = make_chunk("one two three", 0.0, 3.0)
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        assert all(get_layer(line) == 0 for line in d)

    def test_each_line_spans_one_word_window(self):
        """Each Dialogue line's timing matches that word's time window."""
        profile = make_profile()
        words = ["one", "two", "three"]
        ws = [0.0, 1.0, 2.0]
        we = [1.0, 2.0, 3.0]
        chunk = make_chunk("one two three", 0.0, 3.0,
                           words=words, word_starts=ws, word_ends=we)
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        assert len(d) == 3
        # Line 0 covers word "one": 0.0 → 1.0
        assert get_start(d[0]) == _ass_time(0.0)
        assert get_end(d[0])   == _ass_time(1.0)
        # Line 1 covers word "two": 1.0 → 2.0
        assert get_start(d[1]) == _ass_time(1.0)
        assert get_end(d[1])   == _ass_time(2.0)
        # Line 2 covers word "three": 2.0 → 3.0
        assert get_start(d[2]) == _ass_time(2.0)
        assert get_end(d[2])   == _ass_time(3.0)

    def test_gap_filling_extends_word_end_to_next_start(self):
        """Word ends that don't reach the next word's start are gap-filled."""
        profile = make_profile()
        # word_ends don't reach word_starts — gaps of 100ms each
        chunk = make_chunk("hello world",
                           start=0.0, end=2.0,
                           words=["hello", "world"],
                           word_starts=[0.0, 1.0],
                           word_ends=[0.8, 2.0])   # gap 0.8→1.0
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        # "hello" line should be extended to 1.0 (next word's start)
        assert get_end(d[0]) == _ass_time(1.0)
        # "world" ends at chunk_end
        assert get_end(d[1]) == _ass_time(2.0)

    def test_no_gap_between_consecutive_lines(self):
        """Consecutive word lines are seamless: end of word N = start of word N+1."""
        profile = make_profile()
        chunk = make_chunk("alpha beta gamma", 0.0, 3.0,
                           words=["alpha", "beta", "gamma"],
                           word_starts=[0.0, 1.0, 2.0],
                           word_ends=[0.9, 1.9, 3.0])
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        assert get_end(d[0]) == get_start(d[1])
        assert get_end(d[1]) == get_start(d[2])

    def test_highlight_colour_on_active_word_only(self):
        """Each line has highlight colour on its own word, normal on all others."""
        profile = make_profile(
            karaoke_color="&H0000FFFF",   # yellow → BBGGRR = 00FFFF
            primary_color="&H00FFFFFF",   # white  → BBGGRR = FFFFFF
        )
        chunk = make_chunk("hello world",
                           start=0.0, end=2.0,
                           words=["hello", "world"],
                           word_starts=[0.0, 1.0],
                           word_ends=[1.0, 2.0])
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)

        # Line 0: "hello" highlighted, "world" normal
        t0 = get_text(d[0])
        assert r"\1c&H00FFFF&}hello" in t0   # yellow on hello
        assert r"\1c&HFFFFFF&}world" in t0   # white on world
        assert r"\1c&H00FFFF&}world" not in t0  # world is NOT highlighted

        # Line 1: "world" highlighted, "hello" normal
        t1 = get_text(d[1])
        assert r"\1c&H00FFFF&}world" in t1   # yellow on world
        assert r"\1c&HFFFFFF&}hello" in t1   # white on hello

    def test_no_kf_tags_in_output(self):
        """The broken \\kf animation tag must never appear in output."""
        profile = make_profile()
        chunk = make_chunk("test word here now", 0.0, 4.0)
        events = _karaoke_events([chunk], profile)
        full = "\n".join(events)
        assert r"\kf" not in full
        assert r"\k}" not in full

    def test_uses_1c_colour_override_tags(self):
        """Output must use \\1c inline colour tags, not animation tags."""
        profile = make_profile()
        chunk = make_chunk("test word", 0.0, 2.0)
        events = _karaoke_events([chunk], profile)
        full = "\n".join(events)
        assert r"\1c&H" in full

    def test_spaces_inside_colour_tag_spans(self):
        """Spaces must not immediately follow the highlight (yellow) colour tag."""
        profile = make_profile(
            karaoke_color="&H0000FFFF",   # yellow → BBGGRR = 00FFFF
            primary_color="&H00FFFFFF",   # white
        )
        highlight_tag = r"{\1c&H00FFFF&}"
        chunk = make_chunk("one two three", 0.0, 3.0)
        events = _karaoke_events([chunk], profile)
        for line in get_dialogue(events):
            text = get_text(line)
            # A space must NEVER immediately follow the highlight tag (yellow space bug)
            assert highlight_tag + " " not in text, (
                f"Space found immediately after highlight tag (yellow space bug) in: {text}"
            )

    def test_empty_chunk_skipped(self):
        profile = make_profile()
        chunk = SubtitleChunk(text="", start=0.0, end=1.0)
        events = _karaoke_events([chunk], profile)
        assert events == []

    def test_chunk_with_no_timing_fallback(self):
        """Chunk with no word_starts uses evenly distributed timing."""
        profile = make_profile()
        chunk = SubtitleChunk(text="hello world foo", start=0.0, end=3.0)
        chunk.words = ["hello", "world", "foo"]
        # word_starts / word_ends are empty → fallback to even distribution
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        # 3 words → 3 lines
        assert len(d) == 3

    def test_multiple_chunks(self):
        """N chunks with M words each → N×M total Dialogue lines."""
        profile = make_profile()
        chunks = [
            make_chunk("first chunk here", 0.0, 2.0),   # 3 words
            make_chunk("second chunk words", 2.0, 4.0),  # 3 words
        ]
        events = _karaoke_events(chunks, profile)
        d = get_dialogue(events)
        # 2 chunks × 3 words = 6 total lines
        assert len(d) == 6
        # All Layer 0
        assert all(get_layer(line) == 0 for line in d)

    def test_write_ass_file_karaoke(self, tmp_path):
        profile = make_profile()
        chunks = [make_chunk("the quick brown fox", 0.0, 4.0)]
        out = tmp_path / "test.ass"
        ok = write_ass_file(chunks, out, profile)
        assert ok
        assert out.exists()
        text = out.read_text(encoding="utf-8-sig")
        assert "[Script Info]" in text
        assert "[V4+ Styles]"  in text
        assert "Dialogue:"     in text
        assert r"\kf"          not in text
        assert r"\1c&H"        in text

    def test_ass_file_colour_correct_direction(self, tmp_path):
        """
        Style header: PrimaryColour = highlight (yellow), SecondaryColour = normal (white).
        This is correct even though inline tags override per-word.
        """
        profile = make_profile(
            karaoke_color="&H0000FFFF",
            primary_color="&H00FFFFFF",
        )
        out = tmp_path / "kara.ass"
        write_ass_file([make_chunk("test", 0.0, 1.0)], out, profile)
        text = out.read_text(encoding="utf-8-sig")
        style_line = [l for l in text.splitlines() if l.startswith("Style:")][0]
        parts = style_line.split(",")
        # Format: Style: Name,Font,Size,Primary,Secondary,...
        assert parts[3] == "&H0000FFFF"   # Primary = highlight (yellow)
        assert parts[4] == "&H00FFFFFF"   # Secondary = normal (white)


# ─── Timing edge cases ────────────────────────────────────────────────────────

class TestKaraokeTimingEdgeCases:

    def test_zero_duration_word_gets_minimum(self):
        """Zero-duration word timestamps are padded to minimum 40ms."""
        profile = make_profile()
        chunk = SubtitleChunk(text="test", start=1.0, end=1.5)
        chunk.words = ["test"]
        chunk.word_starts = [1.0]
        chunk.word_ends   = [1.0]   # zero duration
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        assert len(d) == 1
        # End must be > start
        start_t = get_start(d[0])
        end_t   = get_end(d[0])
        assert end_t != start_t

    def test_single_word_chunk(self):
        """Single-word chunk produces exactly one Dialogue line."""
        profile = make_profile()
        chunk = make_chunk("hello", 0.5, 1.5)
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        assert len(d) == 1
        assert get_start(d[0]) == _ass_time(0.5)
        assert get_end(d[0])   == _ass_time(1.5)

    def test_none_start_end_skipped(self):
        """Chunk with None start/end produces no events."""
        profile = make_profile()
        bad_chunk = SubtitleChunk(text="hello world", start=None, end=None)
        events = _karaoke_events([bad_chunk], profile)
        assert events == []

    def test_last_word_ends_at_chunk_end(self):
        """The last word's line always ends at the chunk boundary."""
        profile = make_profile()
        chunk = make_chunk("alpha beta gamma", 1.0, 5.0,
                           words=["alpha", "beta", "gamma"],
                           word_starts=[1.0, 2.0, 3.5],
                           word_ends=[1.8, 3.0, 4.5])   # last word ends before chunk
        events = _karaoke_events([chunk], profile)
        d = get_dialogue(events)
        # Last line should end at chunk_end (5.0), not raw word_end (4.5)
        assert get_end(d[-1]) == _ass_time(5.0)

    def test_word_colour_tags_all_present_on_every_line(self):
        """Every Dialogue line must have a colour tag for every word."""
        profile = make_profile()
        chunk = make_chunk("red green blue", 0.0, 3.0)
        events = _karaoke_events([chunk], profile)
        for line in get_dialogue(events):
            text = get_text(line)
            # All three words must appear with a colour tag
            assert "red"   in text
            assert "green" in text
            assert "blue"  in text
            # Each word gets at least one \1c tag; the active (non-last) word gets
            # two tags (highlight + normal-for-space), so count is >= 3 and <= 4.
            tag_count = text.count(r"\1c&H")
            assert 3 <= tag_count <= 4, f"Expected 3-4 colour tags, got {tag_count}: {text}"


# ─── _build_karaoke_line ─────────────────────────────────────────────────────

class TestBuildKaraokeLine:

    def test_active_word_gets_highlight(self):
        normal_tag    = r"{\1c&HFFFFFF&}"
        highlight_tag = r"{\1c&H00FFFF&}"
        line = _build_karaoke_line(["one", "two", "three"], 1,
                                   normal_tag, highlight_tag)
        # Active word "two" has highlight tag; the trailing space is in normal colour
        assert highlight_tag + "two" in line
        assert normal_tag + "one "    in line
        assert normal_tag + "three"   in line   # last word, no trailing space
        # Space after highlight word must NOT be inside the highlight span
        assert highlight_tag + "two " not in line, "Space after active word should be normal colour"

    def test_last_word_no_trailing_space(self):
        normal_tag    = r"{\1c&HFFFFFF&}"
        highlight_tag = r"{\1c&H00FFFF&}"
        line = _build_karaoke_line(["a", "b", "c"], 2,
                                   normal_tag, highlight_tag)
        # Last word "c" is active; should not end with a space
        assert line.endswith("c")

    def test_single_word(self):
        normal_tag    = r"{\1c&HFFFFFF&}"
        highlight_tag = r"{\1c&H00FFFF&}"
        line = _build_karaoke_line(["word"], 0, normal_tag, highlight_tag)
        assert highlight_tag + "word" in line
        assert line.endswith("word")


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
