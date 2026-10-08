# VideoForge — Complete Setup & Usage Guide

Everything you need to install, configure, and use VideoForge on Windows.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Step 1 — Install Python](#2-step-1--install-python)
3. [Step 2 — Extract VideoForge](#3-step-2--extract-videoforge)
4. [Step 3 — Run Setup](#4-step-3--run-setup)
5. [Step 4 — Install FFmpeg](#5-step-4--install-ffmpeg)
6. [Step 5 — Launch the App](#6-step-5--launch-the-app)
7. [First-Time Configuration](#7-first-time-configuration)
8. [Preparing Your Projects](#8-preparing-your-projects)
9. [Using the App — Step by Step](#9-using-the-app--step-by-step)
10. [Render Settings Explained](#10-render-settings-explained)
11. [Subtitle Options](#11-subtitle-options)
12. [Presets](#12-presets)
13. [Bulk Processing](#13-bulk-processing)
14. [CLI / Headless Mode](#14-cli--headless-mode)
15. [Output Files](#15-output-files)
16. [Common Errors & Fixes](#16-common-errors--fixes)

---

## 1. System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | Windows 10 64-bit | Windows 11 64-bit |
| Python | 3.9 | 3.11 or 3.12 |
| RAM | 4 GB | 8 GB or more |
| Disk | 1 GB free | 5 GB free |
| CPU | Any dual-core | Quad-core or better |
| GPU | Not required | CUDA GPU speeds up Whisper |
| Internet | For setup only | Not needed after install |

---

## 2. Step 1 — Install Python

1. Go to **https://python.org/downloads/**
2. Click the big yellow **"Download Python 3.x.x"** button
3. Run the installer
4. On the first screen: **CHECK THE BOX** that says **"Add Python to PATH"** — this is critical
5. Click **"Install Now"**
6. When it finishes, click "Close"

**Verify it worked:** Open Command Prompt (`Win+R`, type `cmd`, press Enter) and run:

```
python --version
```

You should see something like `Python 3.11.9`. If you see an error, Python is not in PATH — reinstall and make sure to check the "Add to PATH" box.

---

## 3. Step 2 — Extract VideoForge

1. Download the `VideoForge_complete.zip` file
2. Right-click it → **"Extract All..."**
3. Choose a location, for example `C:\VideoForge`
4. Click **Extract**

After extracting, you should see a folder structure like this:

```
C:\VideoForge\
├── main.py
├── requirements.txt        ← must exist here
├── launch.bat
├── README.md
├── app\
│   ├── core\
│   ├── gui\
│   ├── render\
│   └── ...
├── scripts\
│   ├── setup.py
│   └── create_examples.py
├── docs\
│   ├── INSTALLATION_GUIDE.md
│   └── ...
└── tests\
    └── ...
```

**Important:** Make sure `requirements.txt` is directly inside the `VideoForge` folder (next to `main.py`), not inside a nested subfolder.

---

## 4. Step 3 — Run Setup

Open Command Prompt, navigate to your VideoForge folder, and run setup:

```cmd
cd C:\VideoForge
python scripts\setup.py
```

The setup script will:
- Confirm your Python version is OK
- Install all required Python packages automatically
- Check if FFmpeg is installed
- Optionally install `faster-whisper` for subtitle sync
- Create app data folders

**If you see "requirements.txt not found":**

This means you are running the script from the wrong directory. Make sure to `cd` into the VideoForge folder first:

```cmd
cd C:\VideoForge          ← navigate into the folder first
python scripts\setup.py   ← then run setup
```

Not:
```cmd
python C:\VideoForge\scripts\setup.py   ← this can fail
```

**Example of successful setup output:**

```
=======================================================
  VideoForge - Setup
=======================================================
  Script location : C:\VideoForge\scripts\setup.py
  Project root    : C:\VideoForge

[1/7] Checking Python version
  Python 3.11.9
  OK: Python version is supported

[2/7] Checking pip
  OK: pip 24.0

[3/7] Installing Python packages from requirements.txt
  Project root : C:\VideoForge
  Requirements : C:\VideoForge\requirements.txt

  Installing 9 packages:
    PySide6>=6.5.0
    faster-whisper>=0.10.0
    ...

  OK: All packages installed successfully

[4/7] Checking FFmpeg
  OK: ffmpeg version 7.0.2 ...

[5/7] Checking faster-whisper
  OK: faster-whisper is installed

[6/7] Checking Pillow
  OK: Pillow 10.3.0

[7/7] Creating app data directories
  OK: C:\Users\YourName\AppData\Roaming\VideoForge
```

---

## 5. Step 4 — Install FFmpeg

FFmpeg is a separate, free tool that VideoForge uses to create videos. It is not bundled with the app.

### Option A — Automatic (Windows 10/11, easiest)

Open **PowerShell** (not Command Prompt) and run:

```powershell
winget install "FFmpeg (Essentials Build)"
```

When it finishes, close PowerShell and open a new Command Prompt. Test it:

```cmd
ffmpeg -version
```

You should see version information. Done.

---

### Option B — Manual Install

1. Go to: **https://github.com/BtbN/FFmpeg-Builds/releases**
2. Under "Assets", download: `ffmpeg-master-latest-win64-gpl.zip`
   - It's about 90 MB
3. Extract the ZIP — you'll get a folder like `ffmpeg-master-20241201-...`
4. Rename that folder to just `ffmpeg`
5. Move the `ffmpeg` folder to `C:\ffmpeg`
   - After this step, you should have `C:\ffmpeg\bin\ffmpeg.exe`
6. Add `C:\ffmpeg\bin` to your system PATH:
   - Press `Win+R`, type `sysdm.cpl`, press Enter
   - Click the **"Advanced"** tab
   - Click **"Environment Variables..."**
   - In the **"System variables"** section (bottom half), find **"Path"**
   - Click **"Edit..."**
   - Click **"New"**
   - Type: `C:\ffmpeg\bin`
   - Click **OK** on all three dialogs
7. **Close and reopen** Command Prompt (required for PATH change to take effect)
8. Test: `ffmpeg -version`

---

### Option C — Set path inside the app

If you prefer not to modify PATH, you can tell VideoForge exactly where FFmpeg is:

1. Launch VideoForge
2. Click the **⚙ Settings** button (top right)
3. Go to the **"FFmpeg & Tools"** tab
4. Click **"Browse..."** next to "FFmpeg path"
5. Navigate to your `ffmpeg.exe` file and select it
6. Click **"Test FFmpeg"** — you should see a green checkmark
7. Click **"Save"**

---

## 6. Step 5 — Launch the App

**Double-click `launch.bat`** in the VideoForge folder.

Or from Command Prompt:

```cmd
cd C:\VideoForge
python main.py
```

The app will open with a dark-themed window.

---

## 7. First-Time Configuration

When you first open VideoForge, check these settings:

### Open Settings

Click the **⚙** button in the top-right corner (or menu → Tools → Settings).

### FFmpeg & Tools tab

- **Test FFmpeg** — click this button. You should see ✅ green. If not, see Step 4.
- **Whisper model** — set to `small` (good balance of speed and accuracy)
- **Device** — leave as `cpu` unless you have a CUDA GPU

### General tab

- **Default output folder** — leave empty to save videos next to each project, or set a folder like `C:\VideoForge\Output`
- **Filename template** — default is `{project_name}_{date}` (e.g. `my_video_20241201.mp4`)
- **Auto-validate on import** — keep this ON

### Subtitles / AI tab

- **Language** — set to `en` for English, `es` for Spanish, etc. Leave empty for auto-detect.

Click **Save**.

---

## 8. Preparing Your Projects

### What is a "project"?

A project is a single folder containing:
- **1 audio file** — the narration or music
- **1 or more images** — the slides/visuals
- **1 text file** (optional) — the transcript/script for subtitles

### Folder structure

```
my_video/
├── audio.mp3          ← narration audio
├── script.txt         ← transcript (optional, for subtitles)
├── slide_01.jpg
├── slide_02.jpg
└── slide_03.png
```

If you have multiple projects, organize them like this:

```
All_Projects/
├── video_about_dogs/
│   ├── narration.mp3
│   ├── script.txt
│   ├── photo1.jpg
│   └── photo2.jpg
├── product_demo/
│   ├── voiceover.wav
│   ├── transcript.txt
│   ├── image_a.png
│   └── image_b.png
└── podcast_clip/
    ├── audio.mp3
    ├── text.txt
    └── thumbnail.jpg
```

### Supported file formats

| Type | Formats |
|------|---------|
| Audio | `.mp3` `.wav` `.m4a` `.flac` `.aac` `.ogg` `.opus` |
| Images | `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff` |
| Transcript | `.txt` `.srt` `.vtt` `.json` `.docx` |

### Writing your transcript

The transcript file should contain the words spoken in the audio, as plain text:

```
Hello everyone and welcome to today's video. Today we're going to cover 
the three most important things you need to know about starting a business. 
First, you need to have a clear vision of what you want to achieve.
```

Tips:
- Match the transcript to exactly what's said in the audio for best subtitle sync
- Punctuation helps the subtitle segmenter split text at natural boundaries
- You can also use an SRT file if you already have timed captions

### Test with example projects

Don't have content yet? Generate test projects:

```cmd
cd C:\VideoForge
python scripts\create_examples.py
```

This creates a folder called `example_projects` with 3 real working projects (real WAV audio, real PNG images, real transcript files).

---

## 9. Using the App — Step by Step

### Step 1: Add your projects

**Method A — Add Folders button:**
1. Click **＋ Add Folders** in the top bar
2. Navigate to your container folder (the folder that *contains* your project folders)
3. Click **"Select Folder"**
4. VideoForge scans all subfolders automatically

**Method B — Drag and Drop:**
1. Open Windows Explorer
2. Drag your project folder (or container folder) into the VideoForge window
3. Drop it onto the Projects table area

**Method C — Single specific folder:**
1. Menu → File → Add Single Folder...
2. Select the exact project folder

### Step 2: Review the project list

After scanning, the **Projects** tab shows all found projects.

| Badge color | Meaning |
|-------------|---------|
| 🟢 Valid | Ready to render — has audio and images |
| 🔴 Invalid | Something is missing — click Edit to see what |
| ⚪ Discovered | Found but not yet validated |

Look at the columns:
- **Images** — how many slide images were detected
- **Duration** — length of the audio (e.g. `3:45`)
- **Words** — transcript word count
- **Health** — a 0-100 score (green bar = good)
- **Output** — where the video will be saved

### Step 3: Check invalid projects (if any)

If a project shows 🔴 Invalid:
1. Click **"Edit"** in that project's row
2. Go to the **"Validation"** tab
3. Read the issues listed in red — each one has a suggested fix

Common issues:
- *"No audio file found"* → add an `.mp3` or `.wav` to the folder
- *"No image files found"* → add `.jpg` or `.png` files to the folder
- *"Audio file missing"* → the file was moved; re-scan after putting it back

### Step 4: Adjust settings (optional)

To customize how a project renders:
1. Click **"Edit"** on any project
2. The project editor has 5 tabs:

**Overview tab** — shows detected files and metadata

**Output tab** — change these settings:
- **Apply Preset** — pick YouTube HD, Reels/Shorts, Instagram, etc.
- **Resolution** — 1920×1080, 1080×1920 (portrait), 1080×1080, or custom
- **FPS** — 30 for most content
- **CRF** — quality (18=excellent, 23=default, 28=smaller file)
- **Transition** — fade, dissolve, wipe, etc.
- **Motion Effect** — Ken Burns, zoom in/out, pan

**Subtitles tab** — change subtitle style:
- **Enable subtitles** — toggle on/off
- **Mode** — Classic (full sentences), Phrase (short chunks), Viral (large social style), Word (one word at a time)
- **Font size** — default 72px (scales well for social media)

**Images tab** — drag images to reorder them (changes slide sequence)

**Validation tab** — full list of issues and warnings

Click **"Save Settings"** when done.

### Step 5: Render

**Render everything valid at once:**
- Click **▶ Queue All Valid** in the top bar

**Render specific projects:**
- Click **"Queue"** button on individual project rows
- Or select checkboxes on multiple rows → click **"Queue Selected"**

**Watch progress:**
- Click the **Queue** tab
- Each project shows a progress bar and status
- Live log lines from FFmpeg appear as the render runs

### Step 6: Find your output

When complete, the project's status changes to ✅ Completed.

By default, the output `.mp4` video saves in **the same folder as the project**:

```
my_video/
├── audio.mp3
├── script.txt
├── slide_01.jpg
├── slide_02.jpg
└── my_video_20241201.mp4   ← new file created here
```

A `.srt` subtitle file is also saved alongside it.

To open the output folder automatically after render: Settings → General → enable **"Auto-open output folder after render"**.

---

## 10. Render Settings Explained

### Resolution presets

| Preset | Dimensions | Best for |
|--------|-----------|---------|
| 1920×1080 | 16:9 landscape | YouTube, LinkedIn |
| 1280×720 | 16:9 landscape | Faster render, still HD |
| 1080×1920 | 9:16 portrait | Instagram Reels, TikTok, YouTube Shorts |
| 1080×1080 | 1:1 square | Instagram feed posts |
| 1080×1350 | 4:5 portrait | Instagram feed (slightly taller) |

### CRF quality setting

CRF controls the quality/size tradeoff:

| CRF | Quality | File size |
|-----|---------|-----------|
| 16–18 | Excellent (archive quality) | Very large |
| 20–23 | Very good (default) | Medium |
| 26–28 | Good (fast preview) | Small |
| 32+ | Noticeable compression | Very small |

### Encoding speed

| Preset | Speed | Quality |
|--------|-------|---------|
| ultrafast | ~3× real-time | Lower (for quick tests) |
| fast | ~1.5× real-time | Good |
| medium | Real-time | Good (default) |
| slow | 0.5× real-time | Best quality |

For social media, `medium` or `fast` is fine. Use `ultrafast` only for test renders.

### Motion effects

| Effect | Description |
|--------|-------------|
| Ken Burns | Automatic mix of zoom + pan — the best looking option |
| Zoom In | Slowly zooms into each image |
| Zoom Out | Slowly zooms out from each image |
| Pan Left | Camera pans left across the image |
| Pan Right | Camera pans right |
| Pan Up / Down | Camera pans vertically |
| None | Static images, no movement |

### Transitions

| Transition | Look |
|-----------|------|
| Fade | Simple dissolve to black (clean, works everywhere) |
| Dissolve | Cross-dissolve between images |
| Wipe Left/Right | Slide wipe in a direction |
| Slide Left/Right | Images slide past each other |
| Circlecrop | Circular reveal |
| Pixelize | Pixelation effect |
| None | Hard cut, no transition |

### Image fit modes

| Mode | Behavior |
|------|---------|
| Cover | Image fills frame, cropping edges if needed |
| Contain | Full image visible, black bars on sides or top |
| Blur Background | Full image visible, blurred version fills the background |
| Stretch | Image stretches to fill — can distort |

**Cover** is best for most content. **Blur Background** looks great for portrait images in a landscape video.

---

## 11. Subtitle Options

### Subtitle modes

| Mode | Chunks | Best for |
|------|--------|---------|
| Classic | Full sentences (1-2 lines) | Long-form, professional |
| Phrase | Short natural phrases | General purpose, YouTube |
| Viral | Very short (2-5 words) | Reels, TikTok, Shorts |
| Word | One word at a time | High impact, music |

### How subtitle sync works

**With faster-whisper installed (recommended):**
- VideoForge runs speech recognition on your audio
- Gets word-level timestamps
- Maps your transcript text to the audio timeline
- Produces accurate, word-synced subtitles

**Without faster-whisper:**
- VideoForge splits your text into chunks
- Distributes them evenly across the audio duration
- Less precise but still usable

### Installing faster-whisper

```cmd
pip install faster-whisper
```

First time a project is rendered with subtitles, the model downloads automatically (~250MB for `small`).

### Language settings

In Settings → Subtitles / AI → Language:
- Leave empty for auto-detect (works well but slightly slower)
- Or enter a language code: `en` (English), `es` (Spanish), `fr` (French), `de` (German), `zh` (Chinese), `ja` (Japanese), etc.

### Subtitle styling

In the project editor → Subtitles tab:

- **Font** — default is Arial; any installed Windows font works (e.g. `Impact`, `Helvetica Neue`)
- **Font Size** — 72px default. For Reels/Shorts, try 80-96. For YouTube, 60-72.
- **Bold** — on by default
- **Outline Width** — 3.0 default gives clean readability
- **Vertical Margin** — distance from bottom edge (pixels). For Reels, increase to 200-300 to avoid covering user's face.

---

## 12. Presets

Presets save all render settings as a named profile you can reuse.

### Built-in presets

| Preset | Resolution | Subtitles | Best for |
|--------|-----------|-----------|---------|
| YouTube HD | 1920×1080 | Classic mode | Long-form YouTube |
| Reels / Shorts | 1080×1920 | Viral mode | Instagram/TikTok/Shorts |
| Instagram Square | 1080×1080 | Phrase mode | Instagram feed |
| Fast Preview | 1280×720 | Classic mode | Quick test renders |
| High Quality Archive | 1920×1080 | Phrase mode | Archive / master copy |

### Applying a preset

**To one project:**
- Edit the project → Output tab → "Apply Preset" dropdown

**Creating your own preset:**
1. Menu → Tools → Preset Manager
2. Click **"＋ New"**
3. Enter a name
4. Close the Preset Manager
5. Edit any project and apply your preset to configure its values
6. Or open the Preset Manager and view/edit the fields

**Setting a default preset for all new projects:**
- Settings → General → (apply a preset first, then it becomes the default)

---

## 13. Bulk Processing

VideoForge is built for bulk. Here's the efficient workflow:

### Processing 10-100 projects

1. Put all project folders inside one container folder:
   ```
   C:\My_Projects\
   ├── episode_01\
   ├── episode_02\
   ├── episode_03\
   └── ...
   ```
2. Click **＋ Add Folders** → select `C:\My_Projects`
3. VideoForge scans all subfolders automatically
4. Review the project list — fix any invalid ones
5. Click **▶ Queue All Valid**
6. Leave it running — it processes one at a time by default

### Monitoring progress

- **Dashboard** tab — shows counts of queued, processing, completed, failed
- **Queue** tab — live per-project progress bars
- **Logs** tab — detailed render output
- Status bar at the bottom — shows current render

### Handling failures

If a project fails:
1. Queue tab shows it in red with "Failed" status
2. Click the **↻** retry button next to it
3. Or click **Edit** on the project, check the Validation tab, fix the issue, re-queue

Failed projects never block other projects — the queue continues automatically.

### Concurrent rendering

By default, VideoForge renders one project at a time (most reliable). To process 2 simultaneously:
- Settings → General → Concurrent jobs → set to 2

**Warning:** Running 2+ FFmpeg processes on a typical 4-core machine is usually slower than sequential, because they compete for CPU. Only increase this on machines with 8+ cores.

### Pausing and resuming

- Click **⏸ Pause** to stop starting new jobs (current job finishes)
- Click **▶ Resume** to start again
- You can close the app mid-queue — state is saved. When you reopen, pending jobs are restored.

---

## 14. CLI / Headless Mode

VideoForge includes a command-line interface for scripting or server use.

### Basic usage

```cmd
python main.py --cli "C:\My_Projects"
```

This scans the folder, validates projects, and renders all valid ones.

### Options

```
python main.py --cli <folder> [folder2 ...] [options]

  folder          One or more project container folders
  --output <dir>  Save all output videos here
  --no-subtitles  Skip subtitle generation
  --overwrite     Overwrite existing output files
```

### Examples

**Render one container folder:**
```cmd
python main.py --cli "C:\Projects\Batch01"
```

**Render multiple folders, save to one output directory:**
```cmd
python main.py --cli "C:\Batch01" "C:\Batch02" --output "D:\Rendered"
```

**Overwrite existing output:**
```cmd
python main.py --cli "C:\Projects" --output "D:\Out" --overwrite
```

**No subtitles (faster):**
```cmd
python main.py --cli "C:\Projects" --no-subtitles
```

**Automate with Task Scheduler:**
Create a batch file `render_nightly.bat`:
```cmd
@echo off
cd C:\VideoForge
python main.py --cli "D:\New_Projects" --output "D:\Rendered" --overwrite
```
Then schedule it in Windows Task Scheduler.

---

## 15. Output Files

### File location

By default, output saves to the **same folder as the project**:
```
my_project/
├── audio.mp3
├── slide_01.jpg
└── my_project_20241201.mp4    ← created here
```

To change the output location:
- **Per-project:** Edit project → Output tab → set Output file path
- **Global default:** Settings → Output → Default output folder

### Filename template

Default: `{project_name}_{date}`

Available variables:
| Variable | Replaced with |
|----------|--------------|
| `{project_name}` | The project folder name |
| `{date}` | Today's date as YYYYMMDD |
| `{folder}` | Parent folder name |

Example templates:
- `{project_name}_{date}` → `my_video_20241201.mp4`
- `rendered_{project_name}` → `rendered_my_video.mp4`
- `{date}_{project_name}_hd` → `20241201_my_video_hd.mp4`

### Files created per project

| File | What it is |
|------|-----------|
| `{name}.mp4` | The main output video with burned-in subtitles |
| `audio.srt` | Raw subtitle timing file (for external players) |

### Overwrite protection

By default, VideoForge will NOT overwrite existing files. It adds `_2`, `_3` etc:
```
my_video_20241201.mp4
my_video_20241201_2.mp4    ← if the first one existed
```

To allow overwriting: Settings → General → enable "Overwrite existing output files".

---

## 16. Common Errors & Fixes

### "requirements.txt not found"

You ran setup from the wrong directory. Always `cd` into the VideoForge folder first:
```cmd
cd C:\VideoForge
python scripts\setup.py
```

### "FFmpeg not found" (red warning in top bar)

Install FFmpeg — see [Step 4](#5-step-4--install-ffmpeg) above.

Or set the path manually: Settings → FFmpeg & Tools → Browse.

### Project shows as "Invalid — No audio file"

Your project folder has no recognized audio file. Check:
- The file extension is one of: `.mp3` `.wav` `.m4a` `.flac` `.aac` `.ogg`
- The file is directly inside the project folder (not in a subfolder)

### Project shows as "Invalid — No image files"

Your project folder has no recognized image files. Check:
- Extensions: `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff`
- Images are directly in the project folder

### "Render failed: FFmpeg error"

Enable debug logging to see the exact error:
1. Settings → Advanced → enable "Enable debug logging"
2. Settings → FFmpeg & Tools → enable "Show FFmpeg commands in logs"
3. Retry the render
4. Check the Logs tab — look for lines starting with "Error" or "Invalid"

Common causes:
- Audio file is corrupted → test it in a media player
- Image file is corrupted → try opening it in Paint
- Path contains special characters → move files to a simple path like `C:\Projects\`
- Disk is full → free up space

### Subtitles not appearing

1. Make sure "Enable subtitles" is checked in the project's Subtitles tab
2. Make sure there is a transcript file in the project folder
3. Check the Logs tab for subtitle errors

### App won't open / crashes on start

Run from command line to see the error:
```cmd
cd C:\VideoForge
python main.py
```

Look at the error message. Common causes:
- `ModuleNotFoundError: No module named 'PySide6'` → run `pip install PySide6`
- `ModuleNotFoundError: No module named 'mutagen'` → run `python scripts\setup.py`
- Python version too old → install Python 3.9+

### Slow rendering

Normal behavior — FFmpeg is CPU-intensive. To speed it up:
1. Use the **"Fast Preview (720p)"** preset
2. Set Encoding Speed to `ultrafast`
3. Lower the output resolution
4. Reduce the number of concurrent jobs to 1 (default)
5. Close other CPU-heavy applications while rendering

### Getting more help

1. Check `docs\TROUBLESHOOTING.md` for 30+ specific scenarios
2. Run the test suite to confirm everything is working:
   ```cmd
   python tests\test_all.py
   ```
   All 61 tests should pass.
3. Export your logs: menu → Tools → Export Logs, then review the file
