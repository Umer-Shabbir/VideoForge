import json
import pytest
from pathlib import Path
from app.services.chapter_generator import (
    format_timestamp,
    parse_chapters_from_script,
    generate_chapters_for_project,
    _match_opening_timestamp
)

def test_format_timestamp():
    assert format_timestamp(0.0) == "00:00"
    assert format_timestamp(52.4) == "00:52"
    assert format_timestamp(89.0) == "01:29"
    assert format_timestamp(3600.0) == "01:00:00"
    assert format_timestamp(3665.0) == "01:01:05"
    assert format_timestamp(125.0, use_hours=True) == "00:02:05"

def test_parse_chapters_from_script():
    script = """
[Chapter: The Impossible Challenge]
In 1933, building a suspension bridge across the Golden Gate Strait seemed mathematically impossible.
High winds and deep currents made construction deadly.

[Chapter: Engineering the Caissons]
To anchor the south tower, divers had to blast bedrock under 100 feet of churning water.

[Chapter 3: Defeating the Wind]
The bridge was engineered to bend without snapping.
    """
    chapters = parse_chapters_from_script(script)
    assert len(chapters) == 3
    assert chapters[0]["title"] == "The Impossible Challenge"
    assert "In 1933" in chapters[0]["first_sentence"]
    assert chapters[1]["title"] == "Engineering the Caissons"
    assert "To anchor the south tower" in chapters[1]["first_sentence"]
    assert chapters[2]["title"] == "Defeating the Wind"

def test_generate_chapters_with_srt(tmp_path):
    script = """
[Chapter: The Secret Weapon]
At three in the morning, inside the quiet shop, an eighteen year old hacker arrived.

[Chapter: The Postal Loophole]
Now, consider how the mail system worked across the country.

[Chapter: The Federal Alarm]
Inevitably, postal inspectors realized what was happening.
    """
    (tmp_path / "script.txt").write_text(script, encoding="utf-8")

    srt_content = """1
00:00:00,000 --> 00:00:02,500
At three in the morning, inside

2
00:00:02,500 --> 00:00:05,000
the quiet shop, an eighteen year old hacker arrived.

3
00:01:15,000 --> 00:01:17,500
Now, consider how the mail system worked

4
00:01:17,500 --> 00:01:20,000
across the country.

5
00:03:45,000 --> 00:03:47,500
Inevitably, postal inspectors realized

6
00:03:47,500 --> 00:03:50,000
what was happening.
"""
    (tmp_path / "transcript.srt").write_text(srt_content, encoding="utf-8")
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")

    chapters = generate_chapters_for_project(tmp_path, final_duration=230.0)

    assert len(chapters) == 3
    # First chapter MUST start at 00:00
    assert chapters[0]["timestamp"] == "00:00"
    assert chapters[0]["title"] == "The Secret Weapon"

    # Second chapter matched at 01:15
    assert chapters[1]["timestamp"] == "01:15"
    assert chapters[1]["title"] == "The Postal Loophole"

    # Third chapter matched at 03:45
    assert chapters[2]["timestamp"] == "03:45"
    assert chapters[2]["title"] == "The Federal Alarm"

    # Check chapters.txt written
    chapters_txt = tmp_path / "chapters.txt"
    assert chapters_txt.exists()
    content = chapters_txt.read_text(encoding="utf-8")
    assert "00:00 - The Secret Weapon" in content
    assert "01:15 - The Postal Loophole" in content
    assert "03:45 - The Federal Alarm" in content

    # Check project.json updated
    meta = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert "chapters" in meta
    assert len(meta["chapters"]) == 3
    assert meta["chapters"][1]["timestamp"] == "01:15"

def test_generate_chapters_fallback_without_tags(tmp_path):
    script = """
Paragraph one about the introduction. It introduces the big crisis.

Paragraph two expands on the background and historical context.

Paragraph three details the escalation and conflict.

Paragraph four is the turning point of the event.

Paragraph five describes the climax and peak drama.

Paragraph six wraps up with the modern resolution.
    """
    (tmp_path / "script.txt").write_text(script, encoding="utf-8")
    chapters = generate_chapters_for_project(tmp_path, final_duration=600.0)

    assert len(chapters) >= 3
    assert chapters[0]["timestamp"] == "00:00"
    assert (tmp_path / "chapters.txt").exists()
