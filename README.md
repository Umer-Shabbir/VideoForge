# VideoForge — Bulk Video Generator

VideoForge is a desktop and CLI automation application designed to generate high-quality video content at scale from audio tracks, narration transcripts, and image sets with automatic scene synchronization, animated karaoke typography, and motion transitions.

---

## Prerequisites

- **Python:** 3.10 or newer (tested on Python 3.10, 3.11, and 3.12).
- **FFmpeg & FFprobe:** Installed and accessible in your system `PATH` (or configured via `FFMPEG_PATH` in `.env`).
  - **Windows:** `winget install "FFmpeg (Essentials Build)"` or download from [BtbN FFmpeg Releases](https://github.com/BtbN/FFmpeg-Builds/releases).
  - **macOS:** `brew install ffmpeg`
  - **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
- **Hardware (Optional):** NVIDIA GPU with CUDA support for accelerated Whisper subtitle transcription (CPU fallback is included and enabled by default).

---

## Quick Start (Fresh Clone)

### 1. Clone the Repository
```bash
git clone <repository-url> videoforge
cd videoforge
```

### 2. Configure Environment Variables (Optional)
Copy the example environment configuration to `.env`:
```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Windows (CMD)
copy .env.example .env

# Linux / macOS
cp .env.example .env
```
*Note: All variables have built-in defaults; setting `.env` is optional unless you need custom FFmpeg or data paths.*

### 3. Install Dependencies

#### Using `uv` (Fastest, Recommended):
```bash
uv venv .venv
uv pip install -r requirements.txt
```

#### Using standard `python` & `pip`:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running the Application

### GUI Mode
- **Windows:** Double-click `launch.bat` (or `run.bat`), or run:
  ```bash
  python main.py
  ```
- **Linux / macOS:** Run `run.sh` or:
  ```bash
  ./run.sh
  # or
  python3 main.py
  ```

### Headless / CLI Batch Mode
Render one or multiple project folders without launching the GUI:
```bash
python main.py --cli path/to/project_folder --output path/to/output_dir
```

Additional CLI options:
- `--overwrite`: Overwrite existing output files instead of generating incremental suffixes (`_2.mp4`).
- `--no-subtitles`: Disable burning subtitles into the rendered video.

---

## Environment Variables

| Variable | Default Value | Required | Description |
| :--- | :--- | :--- | :--- |
| `FFMPEG_PATH` | *Auto-detected* | No | Custom path to the `ffmpeg` binary if not in system PATH or bundled directories. |
| `FFPROBE_PATH` | *Auto-detected* | No | Custom path to the `ffprobe` binary if not beside `ffmpeg` or in system PATH. |
| `VIDEOFORGE_DATA_DIR` | *Platform standard* | No | App data folder for SQLite database (`videoforge.db`) and runtime logs. Defaults to `%APPDATA%\VideoForge` on Windows, `~/Library/Application Support/VideoForge` on macOS, and `~/.local/share/videoforge` on Linux. |
| `VIDEOFORGE_SETTINGS_PATH` | `<DATA_DIR>/settings.json` | No | Explicit path to `settings.json`. Falls back to repository `./settings.json` or data directory. |
| `MASTER_PRESETS_REGISTRY_PATH` | `presets/master_presets_registry.json` | No | Path to master preset typography definitions. |
| `VF_DEBUG` | `0` | No | Set to `1` or `true` to enable verbose debug logging to console and log files. |
| `QT_SCALE_FACTOR_ROUNDING_POLICY` | `PassThrough` | No | Qt6 high-DPI scaling policy (`PassThrough`, `Round`, `Floor`, `Ceil`). |
| `GENERATED_CONTENT_DIR` | *None* | No | Optional path to existing generated batch content for extended integration tests. |

---

## Project Structure

```text
├── app/
│   ├── core/          # App state, project entities, and queue management
│   ├── gui/           # PySide6 desktop interface, widgets, and dialogs
│   ├── render/        # FFmpeg pipeline, motion filters, and timeline builder
│   ├── services/      # Project discovery, validation, and chapter generator
│   ├── storage/       # SQLite persistence and settings manager
│   ├── subtitles/     # Subtitle segmentation, Whisper alignment, and ASS styling
│   ├── utils/         # Cross-platform file, audio, and FFmpeg utilities
│   └── workers/       # Asynchronous render and scanning background workers
├── docs/              # Detailed guides and developer notes
├── presets/           # Master typography and styling presets registry
├── scripts/           # Automation, testing, and setup helpers
├── tests/             # Pytest test suite (130+ unit & integration tests)
├── .env.example       # Example environment configuration
├── launch.bat         # Windows one-click launcher
├── main.py            # Main application entry point (GUI / CLI)
├── requirements.txt   # Runtime production dependencies
├── requirements-dev.txt # Development and testing dependencies
├── run.bat            # Windows startup script
└── run.sh             # Linux/macOS startup script
```

---

## Running Tests

To verify your installation and all rendering pipelines:
```bash
pytest
```
Or with verbose output:
```bash
pytest -v
```
