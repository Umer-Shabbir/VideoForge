# VideoForge — Installation & User Guide

## Installation

### System Requirements
- **OS:** Windows 10 or Windows 11 (64-bit)
- **Python:** 3.9 or newer
- **FFmpeg:** Separate install required (free)
- **RAM:** 4GB minimum, 8GB recommended
- **Disk:** 500MB for app, 200MB+ for Whisper models (optional)
- **GPU:** Not required, but CUDA GPU speeds up Whisper

---

### Step 1: Install Python

1. Download Python 3.11 from [python.org](https://python.org)
2. Run the installer
3. ✅ **Check "Add Python to PATH"** during installation
4. Click "Install Now"

Verify: open a terminal and run `python --version`

---

### Step 2: Get VideoForge

**Option A — Download:**
Extract the ZIP to a folder like `C:\VideoForge`

**Option B — Git:**
```bash
git clone https://github.com/yourproject/videoforge
cd videoforge
```

---

### Step 3: Run Setup

```cmd
cd C:\VideoForge
python scripts\setup.py
```

This will:
- Install all Python packages
- Check for FFmpeg
- Optionally install faster-whisper
- Create app data directories

---

### Step 4: Install FFmpeg

FFmpeg is a separate tool not bundled with VideoForge.

**Easiest — winget (Windows 10+):**
```powershell
winget install "FFmpeg (Essentials Build)"
```

**Manual install:**
1. Go to: https://github.com/BtbN/FFmpeg-Builds/releases
2. Download: `ffmpeg-master-latest-win64-gpl.zip`
3. Extract to `C:\ffmpeg` (or any folder)
4. Add `C:\ffmpeg\bin` to PATH:
   - Press `Win+R`, type `sysdm.cpl`
   - Advanced → Environment Variables
   - Under "System variables", select `Path`, click Edit
   - Click New, enter `C:\ffmpeg\bin`
   - Click OK on all dialogs
5. Restart any open terminals

**Verify:** `ffmpeg -version` should show version info.

---

### Step 5: Launch VideoForge

```cmd
python main.py
```

Or double-click `launch.bat`

---

## First-Time Setup in the App

### Configure FFmpeg (if not auto-detected)
1. Click ⚙ **Settings**
2. Go to **FFmpeg & Tools** tab
3. Click **Browse...** next to "FFmpeg path"
4. Select your `ffmpeg.exe` file
5. Click **Test FFmpeg** to verify
6. Click **Save**

### Configure Whisper (optional, for accurate subtitle timing)
1. Settings → **Subtitles / AI**
2. Select model size:
   - `tiny` — fastest, less accurate (~75MB)
   - `small` — good balance (~250MB) ← **recommended**
   - `medium` — better accuracy (~800MB)
   - `large` — best accuracy (~1.5GB)
3. The model downloads automatically on first render

---

## Using VideoForge

### Adding Projects

**Method 1 — Add Folders button:**
1. Click **＋ Add Folders** in the top bar
2. Navigate to your container folder (the folder that *contains* your project folders)
3. Click OK — VideoForge scans for valid projects automatically

**Method 2 — Drag and Drop:**
- Drag folders from Windows Explorer and drop them onto the Projects table

**Method 3 — Single folder:**
- Menu: File → Add Single Folder...

### Understanding Project Status

| Status | Meaning |
|--------|---------|
| 🟢 Valid | Ready to render |
| 🔴 Invalid | Missing files (see Edit → Validation tab) |
| 🔵 Queued | Waiting in render queue |
| 🟡 Processing | Currently rendering |
| ✅ Completed | Render finished |
| ❌ Failed | Render error (see error message) |

### Rendering

**Quick batch render:**
1. Click **▶ Queue All Valid**
2. Watch progress in the **Queue** tab
3. Output videos save alongside each project folder

**Queue one project:**
- Click the **Queue** button in the project row
- Or right-click the project → Queue for Rendering

**Edit a project first:**
- Click **Edit** or double-click the project row
- Adjust resolution, subtitles, transitions, output path
- Click **Save & Queue**

### Queue Controls

| Button | Action |
|--------|--------|
| ⏸ Pause | Stop starting new jobs (current job finishes) |
| ▶ Resume | Resume starting new jobs |
| ✕ Cancel All | Cancel all pending and running jobs |
| 🗑 Clear Done | Remove completed jobs from the list |

### Per-Project Settings

Click **Edit** on any project to customize:

**Output tab:**
- Resolution (1920×1080, 9:16, square, custom)
- FPS (typically 30)
- Video codec (H.264/H.265)
- Quality (CRF: 18=high quality, 28=smaller file)
- Transitions (fade, wipe, dissolve, etc.)
- Motion effects (Ken Burns, zoom, pan)
- Audio normalization and fade

**Subtitles tab:**
- Enable/disable subtitles
- Mode: Classic / Phrase / Viral / Word
- Font, size, bold, outline width
- Vertical position (margin)

**Images tab:**
- Drag to reorder images (changes slide sequence)

**Validation tab:**
- See exactly what's wrong and how to fix it

### Applying Presets

1. Open **Edit** on any project
2. In the Output tab, use the **Apply Preset** dropdown
3. Built-in presets: YouTube HD, Reels/Shorts, Instagram Square

Or set a global default in Settings → click "Set as Default Profile".

---

## Output Videos

- Videos save to the same folder as the project (default)
- Or configure a global output folder in Settings
- Filename: `{project_name}_{date}.mp4` (configurable template)
- Format: MP4 (H.264 video + AAC audio)
- Subtitles are burned into the video (hardcoded)
- A `.srt` file is also saved alongside the video for reference

---

## Subtitle Alignment

VideoForge uses two methods:

1. **Whisper (recommended)** — runs speech recognition on the audio to get word-level timestamps, then maps your text to the audio. Very accurate, requires `faster-whisper` installed.

2. **Even distribution (fallback)** — splits the transcript into chunks and distributes them evenly across the audio duration. Works without Whisper but timing is approximate.

### Supported Transcript Formats
| Format | Notes |
|--------|-------|
| `.txt` | Plain text, one or more paragraphs |
| `.srt` | SRT subtitle file — timestamps extracted |
| `.vtt` | WebVTT subtitle file |
| `.json` | JSON with `text`, `transcript`, or `content` key |
| `.docx` | Word document — text extracted |

---

## Tips & Best Practices

**For best subtitle results:**
- Use a clean transcript that matches exactly what was said
- Install `faster-whisper` for accurate timing
- Choose `small` or `medium` Whisper model
- Make sure the audio is clear (no heavy background noise)

**For smooth video:**
- Use 5-15 images for a 3-5 minute audio — gives ~15-30s per slide
- Transition duration of 0.5-0.8s looks natural
- Ken Burns motion adds life to still images

**For batch processing:**
- Organize all projects under one container folder
- Use consistent naming: `project_name/audio.mp3`, etc.
- Set a global default preset before scanning

**For social media:**
- Reels/Shorts preset: 1080×1920, Viral subtitle mode, large font
- YouTube: 1920×1080, Classic subtitle mode
- Instagram: 1080×1080, Phrase subtitle mode

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Add Folders |
| Ctrl+Enter | Queue All Valid |
| Ctrl+, | Settings |
| Ctrl+W | Close dialog |

---

## Troubleshooting

### "FFmpeg not found"
- Run `ffmpeg -version` in a terminal — if it fails, FFmpeg isn't in PATH
- Go to Settings → FFmpeg & Tools, set the exact path to ffmpeg.exe
- Or re-install FFmpeg per the installation instructions above

### "Subtitles are not timed correctly"
- Install faster-whisper: `pip install faster-whisper`
- Or check Settings → Subtitles / AI and verify the model/language settings
- For non-English audio: set the language code (e.g., `es` for Spanish)

### "Project shows as Invalid"
- Click Edit → Validation tab for specific error messages
- Most common: missing audio or no images in the folder

### "Render fails with filter error"
- Enable "Show FFmpeg commands in logs" in Settings → Advanced
- Check the Logs tab for the full FFmpeg error
- Common causes: very short audio, image files that can't be read, disk full

### "App is slow"
- Set Concurrent Jobs to 1 (default)
- Use "Fast Preview (720p)" preset for test runs
- Close other CPU-heavy applications during rendering

### "The app crashed / queue is gone"
- Restart the app — queue state is automatically saved and restored
- Projects in "Processing" state at startup are reset to "Failed" (safe to retry)
