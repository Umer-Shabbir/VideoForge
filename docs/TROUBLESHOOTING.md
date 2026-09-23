# VideoForge — Troubleshooting Guide

## Diagnostic Checklist

Run this first when something isn't working:

```bash
# 1. Verify Python version
python --version    # Must be 3.9+

# 2. Verify all packages
pip list | findstr /I "PySide6 faster-whisper Pillow mutagen"

# 3. Verify FFmpeg
ffmpeg -version
ffprobe -version

# 4. Run unit tests
python tests/test_all.py

# 5. Run setup check
python scripts/setup.py
```

---

## FFmpeg Issues

### "FFmpeg not found"

**Symptom:** Red warning in top bar; renders fail immediately.

**Causes & Fixes:**

1. **FFmpeg not installed**
   ```powershell
   winget install "FFmpeg (Essentials Build)"
   # Then restart terminal/app
   ```

2. **FFmpeg not in PATH**
   - Win+R → `sysdm.cpl` → Advanced → Environment Variables
   - Edit `Path` under System variables
   - Add `C:\ffmpeg\bin` (or wherever ffmpeg.exe is)
   - Click OK, restart the app

3. **Custom path in Settings**
   - Settings → FFmpeg & Tools → Browse to `ffmpeg.exe`
   - Click "Test FFmpeg" — should show version

4. **Wrong architecture**
   - Download the `win64` build, not win32

**Verify FFmpeg works:**
```cmd
ffmpeg -version
ffprobe -version
```
Both must work. If only `ffmpeg` works but not `ffprobe`, download the full build (not "essentials").

---

### "FFmpeg error: No such file or directory"

The render command references a file that doesn't exist. Usually:
- Audio or image file was moved after import
- Re-scan the project: right-click → "Remove from List", then re-add the folder

---

### "FFmpeg error: Invalid data found when processing input"

Audio file is corrupted or in an unsupported format.
- Try converting: `ffmpeg -i input.m4a output.wav`
- Supported: MP3, WAV, M4A, FLAC, AAC, OGG, OPUS

---

### "FFmpeg error: filter_complex parse error"

The generated filter is malformed. Enable debug logging:
1. Settings → Advanced → Enable debug logging
2. Settings → FFmpeg & Tools → "Show FFmpeg commands in logs"
3. Try the render again
4. Check Logs tab for the exact ffmpeg command
5. Copy it to a terminal to see the full error

**Common causes:**
- Very short audio (< 1 second per image with many images)
- Image files that PIL can't read
- Special characters in file paths — try moving to a path with only ASCII characters

---

### Render is very slow

1. Use **Fast Preview (720p)** preset for testing
2. Set Encoding Speed to `ultrafast` in project settings
3. Reduce resolution (1280×720 instead of 1920×1080)
4. Check Task Manager — if CPU is at 100%, that's expected; FFmpeg is CPU-bound
5. Close other CPU-heavy applications
6. Don't set concurrent jobs > 1 on a 4-core machine

---

## Subtitle Issues

### "Subtitles not appearing in output"

1. Check project Settings → Subtitles tab → "Enable subtitles" is checked
2. Check there's a transcript file (`.txt`, `.srt`, etc.)
3. Check Logs for any subtitle errors
4. Verify the transcript file is UTF-8 (open in Notepad++ → check encoding)

---

### "Subtitle timing is way off"

**Without Whisper:** Timing is based on even distribution (approximate by design).

**With Whisper:**
1. Settings → Subtitles / AI → Set Language to the correct language code
   - English = `en`, Spanish = `es`, French = `fr`, German = `de`
   - Or leave empty for auto-detect
2. Try a larger Whisper model: `small` → `medium` → `large`
3. Check that the transcript text actually matches what's spoken in the audio

---

### "faster-whisper crashes / CUDA error"

If you set Device to `cuda` but don't have CUDA:
- Settings → Subtitles / AI → Device → change to `cpu`

If Whisper crashes with memory error:
- Use smaller model: `small` instead of `large`
- Close other applications to free RAM

---

### "Whisper model download fails"

Models download on first use from HuggingFace. If download fails:
1. Check internet connection
2. Models cache to: `C:\Users\<you>\.cache\huggingface\`
3. Manually download from: https://huggingface.co/Systran/faster-whisper-small
4. Place in the cache directory

---

## Project Import Issues

### Projects show as "Invalid"

Click **Edit** on the project → **Validation** tab for specific errors.

**Common issues:**
| Issue | Fix |
|-------|-----|
| No audio file | Add a `.mp3`/`.wav` file to the folder |
| No images | Add `.jpg`/`.png` files to the folder |
| Audio too short | Audio must be at least 0.5 seconds |
| File not found | Re-scan; files may have moved |

---

### "Drag and drop doesn't work"

- Drag the **folder** itself, not files inside it
- Drop onto the Projects table area
- If the app is running as admin, drag-drop from non-admin Explorer may fail

---

### "Recursive scan finds too many / too few projects"

- Settings → Scanning → adjust "Max scan depth" (default 5)
- A "project folder" is detected by having BOTH an audio file AND at least one image
- Parent container folders (with only subfolders) are not treated as projects

---

## Output / Export Issues

### "Output file already exists warning"

- Settings → General → enable "Overwrite existing output files"
- OR: edit the project, set a different output path
- VideoForge never silently overwrites — it appends `_2`, `_3`, etc. by default

---

### "Output video has no audio"

This should not happen normally. If it does:
1. Check your audio file isn't silent
2. Verify `ffprobe` shows audio streams: `ffprobe -v quiet -show_streams your_audio.mp3`
3. Try a different audio format (WAV instead of MP3)

---

### "Output video is shorter than the audio"

- Check there's a `-t` (duration) argument in the FFmpeg command (visible in logs)
- This is intentional: the video is trimmed to the exact audio duration
- If the video is shorter than expected: check `audio_duration` shown in the project list

---

## App Crashes / Errors

### App doesn't start

```bash
python main.py
```
Check the console output. Common causes:
- `ModuleNotFoundError: No module named 'PySide6'` → `pip install PySide6`
- `ModuleNotFoundError: No module named 'mutagen'` → `pip install -r requirements.txt`
- Python version < 3.9 → update Python

---

### "Projects disappeared after restart"

Projects are saved in SQLite. Check:
1. `%APPDATA%\VideoForge\videoforge.db` exists
2. If the app crashed mid-save, projects in "Processing" state are reset to "Failed" at startup
3. Re-scan your folders to re-import

---

### High memory usage

- Whisper models stay in memory: Settings → Subtitles → use `tiny` or `small` model
- Large images in RAM: VideoForge doesn't load images into Python memory (FFmpeg reads them directly)
- If memory keeps growing: check for a runaway FFmpeg process in Task Manager

---

## Logging and Diagnostics

### Enable full debug logging

```bash
# Environment variable
set VF_DEBUG=1
python main.py

# Or in Settings → Advanced → Enable debug logging
```

### Export logs for support

1. Logs tab → **Export...** → save to Desktop
2. Or: menu → Tools → Export Logs

### See the exact FFmpeg command being run

1. Settings → FFmpeg & Tools → "Show FFmpeg commands in logs"
2. Trigger a render
3. Logs tab → filter by level = DEBUG

### Test FFmpeg commands manually

Copy the command from logs, then run in a terminal. The full command is shown like:
```
ffmpeg -y -loop 1 -framerate 30 -t 6.4 -i "C:/project/img.jpg" ...
```

---

## Getting Help

1. Check the logs first: Logs tab in the app
2. Run `python tests/test_all.py` — all 61 tests should pass
3. Run `python scripts/setup.py` — shows dependency status
4. Create an issue with: Python version, FFmpeg version, log export, and the project folder structure
