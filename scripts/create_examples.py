"""
Example project generator for VideoForge.
Creates demo project folders with real (minimal) audio/image/transcript files
so you can immediately test the app without your own content.

Usage:
    python scripts/create_examples.py [--output <dir>]
"""

import sys
import struct
import math
import wave
import array
import os
from pathlib import Path


def _make_sine_wav(path: Path, duration: float = 5.0, freq: float = 440.0,
                   sample_rate: int = 44100):
    """Generate a simple sine-wave WAV file."""
    n_samples = int(sample_rate * duration)
    samples = array.array('h', [
        int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n_samples)
    ])
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def _make_gradient_png(path: Path, width: int = 800, height: int = 600,
                       color1=(30, 30, 80), color2=(100, 60, 180),
                       label: str = ""):
    """Generate a gradient PNG image using pure Python (no PIL required)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            t = y / height
            r = int(color1[0] * (1 - t) + color2[0] * t)
            g = int(color1[1] * (1 - t) + color2[1] * t)
            b = int(color1[2] * (1 - t) + color2[2] * t)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        if label:
            try:
                font = ImageFont.truetype("arial.ttf", 48)
            except Exception:
                font = ImageFont.load_default()
            draw.text((width // 2, height // 2), label,
                      fill=(255, 255, 255), font=font, anchor="mm")
        img.save(str(path), "PNG")
        return True
    except ImportError:
        # Fallback: write minimal valid PNG (1×1 black pixel repeated)
        _write_minimal_png(path)
        return False


def _write_minimal_png(path: Path):
    """Write a minimal valid 4×3 solid-color PNG without PIL."""
    import zlib, struct
    w, h = 4, 3
    raw = b''.join(b'\x00' + bytes([80, 60, 160]) * w for _ in range(h))
    compressed = zlib.compress(raw)
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', compressed)
           + chunk(b'IEND', b''))
    path.write_bytes(png)


def create_example_projects(output_dir: Path) -> list[Path]:
    """Create three realistic example projects."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []

    # ── Project 1: Travel Story (landscape, 16:9 style) ──────────────────────
    p1 = output_dir / "travel_story"
    p1.mkdir(exist_ok=True)

    _make_sine_wav(p1 / "narration.wav", duration=18.0, freq=220.0)
    (p1 / "script.txt").write_text(
        "Welcome to our travel story. We began our journey at sunrise, "
        "with mountains stretching endlessly before us. "
        "The first day brought unexpected rain, turning the roads to rivers. "
        "But nothing could dampen our spirits. "
        "By afternoon, golden light broke through the clouds. "
        "We found a small cafe tucked into the hillside. "
        "The coffee was perfect. The view was even better. "
        "That evening, we camped under a sky full of stars. "
        "This is what travel is all about.",
        encoding="utf-8"
    )

    slide_data = [
        ("slide_01_sunrise.png",     (20, 20, 60),   (80, 40, 120),   "Sunrise"),
        ("slide_02_mountains.png",   (10, 40, 10),   (40, 100, 40),   "Mountains"),
        ("slide_03_rain.png",        (40, 40, 80),   (80, 80, 140),   "The Journey"),
        ("slide_04_light.png",       (120, 80, 20),  (200, 150, 60),  "Golden Hour"),
        ("slide_05_cafe.png",        (80, 40, 20),   (160, 100, 60),  "The Cafe"),
        ("slide_06_stars.png",       (5, 5, 30),     (20, 20, 80),    "Starry Night"),
    ]
    for fname, c1, c2, lbl in slide_data:
        _make_gradient_png(p1 / fname, 1280, 720, c1, c2, lbl)

    created.append(p1)
    print(f"  ✓ Created: {p1.name}  ({len(slide_data)} slides, 18s audio)")

    # ── Project 2: Product Launch (portrait, 9:16 style) ─────────────────────
    p2 = output_dir / "product_launch"
    p2.mkdir(exist_ok=True)

    _make_sine_wav(p2 / "voiceover.wav", duration=12.0, freq=330.0)
    (p2 / "script.txt").write_text(
        "Introducing the future. "
        "We built something that changes everything. "
        "Faster. Smarter. More powerful than ever before. "
        "Designed for creators who refuse to compromise. "
        "Available now. Limited time offer. "
        "Get yours today.",
        encoding="utf-8"
    )

    product_slides = [
        ("hero_01.png",    (20, 10, 40),   (100, 50, 200),  "The Future"),
        ("feature_01.png", (10, 20, 50),   (40, 100, 200),  "Faster"),
        ("feature_02.png", (50, 10, 20),   (200, 60, 100),  "Smarter"),
        ("feature_03.png", (20, 50, 10),   (100, 200, 60),  "Powerful"),
        ("cta.png",        (100, 80, 0),   (200, 160, 0),   "Get Yours"),
    ]
    for fname, c1, c2, lbl in product_slides:
        _make_gradient_png(p2 / fname, 1080, 1920, c1, c2, lbl)

    # Also include an SRT transcript variant
    (p2 / "captions.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,500\nIntroducing the future.\n\n"
        "2\n00:00:01,800 --> 00:00:04,000\nWe built something that changes everything.\n\n"
        "3\n00:00:04,200 --> 00:00:06,500\nFaster. Smarter. More powerful.\n\n"
        "4\n00:00:07,000 --> 00:00:09,500\nDesigned for creators who refuse to compromise.\n\n"
        "5\n00:00:10,000 --> 00:00:12,000\nAvailable now. Get yours today.\n",
        encoding="utf-8"
    )
    created.append(p2)
    print(f"  ✓ Created: {p2.name}  ({len(product_slides)} slides, 12s audio + SRT)")

    # ── Project 3: Podcast Highlight (square, 1:1) ────────────────────────────
    p3 = output_dir / "podcast_highlight"
    p3.mkdir(exist_ok=True)

    _make_sine_wav(p3 / "podcast_clip.wav", duration=25.0, freq=180.0)
    (p3 / "transcript.txt").write_text(
        "The most important thing is to just start. "
        "Everyone is waiting for the perfect moment. "
        "There is no perfect moment. "
        "The moment you start is when things begin to happen. "
        "I learned this the hard way after years of waiting. "
        "Now I ship something every week, no matter what. "
        "Done is better than perfect. "
        "Progress over perfection. "
        "That is the real lesson.",
        encoding="utf-8"
    )

    podcast_slides = [
        ("quote_01.png",  (30, 20, 60),   (90, 60, 180),  "Just Start"),
        ("quote_02.png",  (60, 20, 20),   (180, 60, 60),  "No Perfect Moment"),
        ("quote_03.png",  (20, 60, 20),   (60, 180, 60),  "Ship It"),
        ("quote_04.png",  (20, 20, 60),   (60, 60, 180),  "Done > Perfect"),
        ("outro.png",     (40, 40, 40),   (100, 100, 100),"Progress"),
    ]
    for fname, c1, c2, lbl in podcast_slides:
        _make_gradient_png(p3 / fname, 1080, 1080, c1, c2, lbl)

    created.append(p3)
    print(f"  ✓ Created: {p3.name}  ({len(podcast_slides)} slides, 25s audio)")

    return created


def print_structure(output_dir: Path):
    print(f"\n  Project structure created in: {output_dir}")
    print()
    for item in sorted(output_dir.iterdir()):
        if item.is_dir():
            print(f"  {item.name}/")
            for f in sorted(item.iterdir()):
                size_kb = f.stat().st_size // 1024
                print(f"    ├── {f.name:<35} ({size_kb} KB)")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create VideoForge example projects")
    parser.add_argument("--output", "-o", default="example_projects",
                        help="Output directory (default: ./example_projects)")
    args = parser.parse_args()

    output = Path(args.output)
    print(f"\nCreating example projects in: {output.resolve()}")
    print("─" * 55)

    projects = create_example_projects(output)
    print_structure(output)

    print("=" * 55)
    print("  Example projects ready!")
    print("=" * 55)
    print()
    print("  To render them with VideoForge:")
    print(f"    python main.py --cli {output} --output {output / 'rendered'}")
    print()
    print("  Or open VideoForge GUI and drag the folder:")
    print(f"    {output.resolve()}")
    print()
