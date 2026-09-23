"""
Subtitle styler — generates polished ASS subtitle files.

KARAOKE MODE — DEFINITIVE IMPLEMENTATION
=========================================

The requirement: as each word is spoken, that word highlights in a custom
colour (e.g. yellow) while all other words stay in the normal colour (white).

WHY THE PREVIOUS ATTEMPTS FAILED
---------------------------------
Attempt 1 (original): Used ASS {\\kf<N>} karaoke fill tags.
  BROKEN because ffmpeg's burn-in renderer does NOT animate \\kf. Every word
  was rendered permanently in PrimaryColour (the highlight). No progression.

Attempt 2 (first fix): Layer 0 base line + Layer 1 per-word overlays.
  BROKEN because when two Dialogue lines occupy the same screen position at
  the same time, libass renders both as separate text objects at the same
  location → doubled/blurry/shadow text. This looks terrible.

THE CORRECT APPROACH
--------------------
Generate exactly N Dialogue lines for a chunk of N words.
Each line covers only its word's active time window.
Each line contains the FULL chunk text with inline colour tags.
Word gaps are eliminated by extending each word's end to the next word's start.

Example: "The quick brown fox" (chunk 0.5→3.5s, words at 0.5/1.0/1.8/2.6):
  Line 1:  0.50→1.00  {yellow}The {white}quick {white}brown {white}fox
  Line 2:  1.00→1.80  {white}The {yellow}quick {white}brown {white}fox
  Line 3:  1.80→2.60  {white}The {white}quick {yellow}brown {white}fox
  Line 4:  2.60→3.50  {white}The {white}quick {white}brown {yellow}fox

At any moment, exactly ONE Dialogue line is active.
No doubling, no gaps, no animation tags, fully renderer-agnostic.

INLINE ASS COLOUR TAG FORMAT
------------------------------
ASS override tags use:  {\\1c&H<BBGGRR>&}
  NOT the full &HAABBGGRR style-header format.
  Yellow (#FFFF00) → BBGGRR = 00FFFF → tag: {\\1c&H00FFFF&}
  White  (#FFFFFF) → BBGGRR = FFFFFF → tag: {\\1c&HFFFFFF&}

SPACE HANDLING
--------------
Spaces between words must carry a colour tag to avoid inheriting the style's
PrimaryColour. We tag the space as part of the PREVIOUS word's colour region:
  {\\1c&Hnormal&}The  ← space included before next tag
  {\\1c&Hyellow&}quick
This is achieved by including the trailing space inside the normal-colour span.
"""

import logging
from pathlib import Path
from app.core.project import RenderProfile, SubtitleMode
from app.subtitles.segmenter import SubtitleChunk

log = logging.getLogger("videoforge.styler")


# ─── Time helpers ─────────────────────────────────────────────────────────────

def _ass_time(s: float) -> str:
    s = max(0.0, s)
    h  = int(s // 3600)
    m  = int((s % 3600) // 60)
    sc = s % 60
    cs = int((sc % 1) * 100)
    return f"{h}:{m:02d}:{int(sc):02d}.{cs:02d}"


def _esc(text: str) -> str:
    """Escape special ASS characters: backslash and braces."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _wrap(text: str, max_chars: int) -> str:
    """Insert \\N at the natural midpoint if text is too long for one line."""
    if len(text) <= max_chars:
        return text
    words = text.split()
    if len(words) <= 1:
        return text
    mid = len(text) // 2
    pos = 0
    best_i, best_d = 0, float("inf")
    for i, w in enumerate(words[:-1]):
        pos += len(w) + 1
        d = abs(pos - mid)
        if d < best_d:
            best_d, best_i = d, i
    l1 = " ".join(words[:best_i + 1])
    l2 = " ".join(words[best_i + 1:])
    return f"{l1}\\N{l2}"


def _hex_to_ass(hex_color: str, alpha: str = "00") -> str:
    """Convert #RRGGBB to ASS &H<AA><BB><GG><RR> format (style header format)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H{alpha}{b}{g}{r}".upper()
    return hex_color if hex_color.startswith("&H") else "&H00FFFFFF"


def _ass_color_to_bbggrr(ass_color: str) -> str:
    """
    Extract the BBGGRR hex string from an ASS &HAABBGGRR colour.
    Used for inline override tags: {\\1c&H<BBGGRR>&}

    Examples:
      "&H0000FFFF"  → "00FFFF"   (yellow)
      "&H00FFFFFF"  → "FFFFFF"   (white)
      "&H00FFFFFF&" → "FFFFFF"   (trailing & stripped)
    """
    h = ass_color.strip()
    if h.startswith("&H"):
        h = h[2:]
    h = h.rstrip("&")
    if len(h) == 8:
        return h[2:]    # drop alpha prefix, keep BBGGRR
    if len(h) == 6:
        return h
    return "FFFFFF"


def _make_colour_tag(bbggrr: str) -> str:
    """Build an ASS inline primary colour override tag."""
    return "{\\1c&H" + bbggrr.upper() + "&}"


# ─── Style line builder ───────────────────────────────────────────────────────

def _style_line(profile: RenderProfile, style_name: str = "Default",
                is_karaoke: bool = False) -> str:
    """
    Build one ASS V4+ style line.
    For karaoke, PrimaryColour = highlight, SecondaryColour = normal text.
    (These are overridden per-word via inline tags anyway, but setting them
    correctly ensures a sane fallback if a renderer ignores inline tags.)
    """
    mode = profile.subtitle_mode
    base_size = max(32, min(profile.subtitle_font_size, 120))

    if mode in (SubtitleMode.VIRAL, SubtitleMode.WORD, SubtitleMode.KARAOKE):
        font_size  = int(base_size * 1.15)
        margin_v   = max(120, profile.subtitle_margin_v)
        outline_w  = 4.0
        shadow     = 2.0
    else:
        font_size  = base_size
        margin_v   = profile.subtitle_margin_v
        outline_w  = profile.subtitle_outline_width
        shadow     = profile.subtitle_shadow

    bold  = "-1" if profile.subtitle_bold else "0"
    font  = profile.subtitle_font or "Arial"

    if is_karaoke:
        primary   = profile.subtitle_karaoke_color
        secondary = profile.subtitle_primary_color
    else:
        primary   = profile.subtitle_primary_color
        secondary = profile.subtitle_primary_color

    outline = profile.subtitle_outline_color
    back    = "&H80000000"

    return (
        f"Style: {style_name},"
        f"{font},{font_size},"
        f"{primary},{secondary},{outline},{back},"
        f"{bold},0,0,0,"
        f"100,100,0,0,"
        f"1,"
        f"{outline_w:.1f},{shadow:.1f},"
        f"2,"
        f"10,10,{margin_v},"
        f"1"
    )


# ─── Write ASS ────────────────────────────────────────────────────────────────

def write_ass_file(
    chunks: list[SubtitleChunk],
    output_path: Path,
    profile: RenderProfile,
    total_duration: float = 0.0,
) -> bool:
    """Write an ASS subtitle file. Returns True on success."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        is_karaoke = (profile.subtitle_mode == SubtitleMode.KARAOKE)

        header = [
            "[Script Info]",
            "; VideoForge subtitles",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            f"PlayResX: {profile.width}",
            f"PlayResY: {profile.height}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            _style_line(profile, "Default", is_karaoke=is_karaoke),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        if is_karaoke:
            events = _karaoke_events(chunks, profile)
        else:
            events = _standard_events(chunks, profile)

        output_path.write_text(
            "\n".join(header + events),
            encoding="utf-8-sig"
        )
        log.info(f"ASS written: {output_path.name} ({len(chunks)} chunks, "
                 f"{'karaoke' if is_karaoke else 'standard'} mode)")
        return True

    except Exception as e:
        log.error(f"write_ass_file failed: {e}", exc_info=True)
        return False


# ─── Standard (non-karaoke) events ───────────────────────────────────────────

def _standard_events(chunks: list[SubtitleChunk], profile: RenderProfile) -> list[str]:
    """One Dialogue line per chunk — simple, reliable."""
    events = []
    max_chars = profile.subtitle_max_chars
    for chunk in chunks:
        if chunk.start is None or chunk.end is None or chunk.end <= chunk.start:
            continue
        text = _wrap(_esc(chunk.text), max_chars)
        events.append(
            f"Dialogue: 0,{_ass_time(chunk.start)},{_ass_time(chunk.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return events


# ─── Karaoke events ───────────────────────────────────────────────────────────

def _karaoke_events(chunks: list[SubtitleChunk], profile: RenderProfile) -> list[str]:
    """
    Generate frame-accurate word-by-word highlight subtitle events.

    For each chunk of N words, produces exactly N Dialogue lines.
    Each line is active only during that word's spoken time window.
    Each line contains the full chunk text with per-word colour override tags.
    Gap-filling: each word's line extends to the next word's start time,
    ensuring seamless transitions with no flicker between words.

    No animation tags, no layer stacking, no doubled text.
    Works correctly with ffmpeg's ASS burn-in renderer.
    """
    events = []

    normal_bbggrr    = _ass_color_to_bbggrr(profile.subtitle_primary_color)
    highlight_bbggrr = _ass_color_to_bbggrr(profile.subtitle_karaoke_color)
    normal_tag    = _make_colour_tag(normal_bbggrr)
    highlight_tag = _make_colour_tag(highlight_bbggrr)

    log.debug(
        f"Karaoke: normal=&H{normal_bbggrr} "
        f"highlight=&H{highlight_bbggrr}"
    )

    for chunk in chunks:
        if chunk.start is None or chunk.end is None or chunk.end <= chunk.start:
            continue

        chunk_start = max(0.0, chunk.start)
        chunk_end   = max(chunk_start + 0.1, chunk.end)

        words = chunk.words if chunk.words else chunk.text.split()
        if not words:
            continue

        n = len(words)

        # ── Build per-word absolute time windows ──────────────────────────
        if (chunk.word_starts and chunk.word_ends
                and len(chunk.word_starts) == n
                and len(chunk.word_ends) == n):
            raw_starts = [max(chunk_start, min(s, chunk_end))
                          for s in chunk.word_starts]
            raw_ends   = [max(chunk_start, min(e, chunk_end))
                          for e in chunk.word_ends]
        else:
            # Even distribution fallback
            total   = chunk_end - chunk_start
            per     = total / n
            raw_starts = [chunk_start + i * per       for i in range(n)]
            raw_ends   = [chunk_start + (i + 1) * per for i in range(n)]

        # ── Gap-fill: extend each word's end to the next word's start ─────
        # This eliminates flicker/blink between words while ensuring the last
        # word's line ends exactly at the chunk boundary.
        word_starts = list(raw_starts)
        word_ends   = [
            raw_starts[i + 1] if i + 1 < n else chunk_end
            for i in range(n)
        ]
        # Never shorten a word below its natural end (handles Whisper overlaps)
        for i in range(n):
            word_ends[i] = max(word_ends[i], raw_ends[i])

        # ── Escape word text ──────────────────────────────────────────────
        esc_words = [_esc(w) for w in words]

        # ── One Dialogue line per word ────────────────────────────────────
        for i in range(n):
            ws = word_starts[i]
            we = word_ends[i]

            # Safety: minimum 40ms visible duration
            if we - ws < 0.04:
                we = ws + 0.04

            line_text = _build_karaoke_line(esc_words, i, normal_tag, highlight_tag)

            events.append(
                f"Dialogue: 0,{_ass_time(ws)},{_ass_time(we)},"
                f"Default,,0,0,0,,{line_text}"
            )

    return events


def _build_karaoke_line(
    esc_words: list[str],
    active_idx: int,
    normal_tag: str,
    highlight_tag: str,
) -> str:
    """
    Build the full-line ASS text for a karaoke word-highlight frame.

    Critical: spaces between words must be inside a colour tag to prevent them
    from inheriting the style's PrimaryColour (= highlight colour in karaoke
    mode), which would make all spaces appear yellow.

    Strategy:
    - Normal (inactive) words: include trailing space INSIDE the normal-colour span.
    - Active (highlighted) word: the word is in highlight colour, but the trailing
      space is explicitly put in normal colour so it does not appear highlighted.

      {\\1c&Hnormal&}The  {\\1c&Hyellow&}quick{\\1c&Hnormal&}  {\\1c&Hnormal&}brown  {\\1c&Hnormal&}fox
                       ^^                      ^^^^^^^^^^^^^^^^^^^^             ^^
                  normal space           space forced to normal colour      normal space
    """
    n = len(esc_words)
    parts = []
    for j, w in enumerate(esc_words):
        is_active = (j == active_idx)
        is_last = (j == n - 1)
        if is_active:
            if is_last:
                parts.append(f"{highlight_tag}{w}")
            else:
                # Highlighted word: tag the word in highlight, then force space to normal
                parts.append(f"{highlight_tag}{w}{normal_tag} ")
        else:
            if is_last:
                parts.append(f"{normal_tag}{w}")
            else:
                # Normal word: include trailing space inside normal-colour span
                parts.append(f"{normal_tag}{w} ")
    return "".join(parts)


# ─── SRT ─────────────────────────────────────────────────────────────────────

def write_srt_file(chunks: list[SubtitleChunk], output_path: Path) -> bool:
    """Write a plain SRT file (no karaoke — plain text for portability)."""
    def _srt_time(s: float) -> str:
        s  = max(0.0, s)
        ms = int((s % 1) * 1000)
        si = int(s)
        h, m, sc = si // 3600, (si % 3600) // 60, si % 60
        return f"{h:02d}:{m:02d}:{sc:02d},{ms:03d}"

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        idx = 1
        for c in chunks:
            if c.start is None or c.end is None or c.end <= c.start:
                continue
            lines += [str(idx), f"{_srt_time(c.start)} --> {_srt_time(c.end)}", c.text, ""]
            idx += 1
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return True
    except Exception as e:
        log.error(f"write_srt_file failed: {e}")
        return False
