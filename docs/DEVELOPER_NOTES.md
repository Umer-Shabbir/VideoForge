# VideoForge — Developer Notes

## Architecture Overview

```
main.py                  → Entry point; initializes AppState, launches MainWindow
app/
  core/
    app_state.py         → Singleton; owns DB, Settings, Queue, project dict
    project.py           → Project dataclass + RenderProfile + all enums
    job.py               → Job dataclass (queue state)
    queue_manager.py     → QObject; manages workers, job lifecycle
  gui/
    main_window.py       → QMainWindow; connects all panels to AppState
    theme.py             → Dark stylesheet + color constants
    widgets/
      dashboard.py       → Stat cards, quick actions
      project_table.py   → QTableWidget; project list + drag-drop
      queue_panel.py     → Live job progress
      logs_panel.py      → Live colored log viewer
    dialogs/
      project_detail.py  → Per-project settings override dialog
      settings_dialog.py → App-level settings dialog
  render/
    timeline.py          → ImageSlot, motion params, Ken Burns math
    ffmpeg_builder.py    → Builds FFmpeg filter_complex command
    renderer.py          → Orchestrates full render pipeline
  subtitles/
    segmenter.py         → Text → SubtitleChunk list
    aligner.py           → faster-whisper integration
    styler.py            → ASS file generation
  services/
    project_scanner.py   → Filesystem scanner → Project objects
  storage/
    database.py          → SQLite CRUD (projects, jobs, history)
    settings_manager.py  → JSON settings + presets
  validators/
    project_validator.py → ValidationResult per project
  workers/
    render_worker.py     → QThread for rendering + scanning
  utils/
    ffmpeg_utils.py      → FFmpeg/FFprobe discovery and invocation
    file_utils.py        → Path normalization, format detection
    logger.py            → Centralized logging with GUI callback
```

---

## Key Design Decisions

### Why PySide6 (not Electron/Tauri)?
- Native Windows look and feel
- No Node.js runtime needed
- Single-file distribution possible
- QThread integration is excellent for background workers
- Well-maintained, binaries available for Windows

### Why FFmpeg subprocess (not moviepy/OpenCV)?
- Maximum control over filter_complex
- FFmpeg xfade for transitions is battle-tested
- zoompan filter handles Ken Burns natively
- No Python media library size overhead
- Debugging is easy (show the command in logs)
- FFmpeg handles all codecs/containers

### Why faster-whisper (not openai-whisper)?
- CTranslate2 backend: faster on CPU, less memory
- int8 quantization: runs on any modern Windows CPU
- Word-level timestamps: enables accurate subtitle sync
- Graceful fallback: if not installed, use even distribution

### Why SQLite + JSON settings (not full ORM)?
- Zero dependencies
- Single .db file = easy backup/portability
- WAL mode for concurrent read/write
- Simple JSON settings file = human readable/editable

### Why ASS subtitles (not SRT)?
- Full control over font, color, outline, position, shadow
- Supports multi-line with line-break control
- FFmpeg `ass=` filter burns them in natively
- Also export SRT for portability

---

## Data Flow

```
User adds folder
       │
ProjectScanner.scan_folder()
       │
   detect_project_files()  →  audio, images, transcript
   get_audio_duration()    →  ffprobe
   read_transcript_text()  →  plain text extraction
   validate_project()      →  ValidationResult
       │
AppState.add_project(Project)
       │
  Database.save_project()  ← persisted to SQLite
  project_table.add_row()  ← shown in UI
       │
User clicks Queue
       │
QueueManager.add_project()
       │
  Job created → DB saved
  RenderWorker spawned (QThread)
       │
Worker: align_subtitles()
       ├─ faster-whisper → word timestamps
       ├─ segment_text() → SubtitleChunk list
       └─ write_ass_file() → temp .ass file
       │
Worker: generate_timeline()
       ├─ ImageSlot list with timing + motion params
       └─ build_zoompan_filter() → FFmpeg expr strings
       │
Worker: build_render_command()
       └─ full FFmpeg filter_complex cmd
       │
Worker: run_ffmpeg() → subprocess
       │
  Progress → job_progress signal → UI
  Completion → job_completed signal → DB updated
```

---

## Adding a New Transition Type

1. Add to `TransitionType` enum in `app/core/project.py`
2. The xfade filter in `ffmpeg_builder.py` uses the enum value directly
3. Add to the combo box in `project_detail.py`
4. The value must be a valid [FFmpeg xfade transition name](https://ffmpeg.org/ffmpeg-filters.html#xfade)

---

## Adding a New Subtitle Mode

1. Add to `SubtitleMode` enum in `app/core/project.py`
2. Add a case in `segmenter.py :: segment_text()`
3. It automatically appears in the UI combo boxes

---

## Adding a New Preset

Open `app/storage/settings_manager.py` → `_default_presets()`:
```python
p = RenderProfile()
p.width, p.height = 1920, 1080
p.subtitle_mode = SubtitleMode.PHRASE
# ... set other fields
presets["My New Preset"] = p.to_dict()
```

Or at runtime: Settings dialog → no code needed.

---

## Testing

```bash
# Unit test the segmenter
python -c "
from app.subtitles.segmenter import segment_text, SubtitleMode
chunks = segment_text('Hello world. This is a test.', SubtitleMode.PHRASE)
print(chunks)
"

# Test project scanning
python -c "
from pathlib import Path
from app.services.project_scanner import ProjectScanner
scanner = ProjectScanner(recursive=True)
projects = scanner.scan_folder(Path('test_projects/'))
for p in projects:
    print(p.name, p.status.value)
"

# Test FFmpeg detection
python -c "
from app.utils.ffmpeg_utils import check_ffmpeg_ready
ok, msg = check_ffmpeg_ready()
print('OK' if ok else 'FAIL', msg)
"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VF_DEBUG` | `0` | Set to `1` for debug logging |
| `FFMPEG_PATH` | auto | Override ffmpeg location |
| `APPDATA` | Windows default | App data location (Windows) |

---

## Performance Notes

- **Single-job default**: Rendering is CPU-bound. Running 2+ jobs in parallel on a typical 4-core machine is slower than sequential due to FFmpeg thread contention.
- **Whisper model caching**: Model stays in memory between renders. Don't call `clear_model_cache()` unless you need to free RAM.
- **FFmpeg threads**: Setting `ffmpeg_threads=0` lets FFmpeg auto-detect. Manual override helps on machines with many cores.
- **Image size**: Huge source images (8K+) slow down the zoompan filter. Pre-downscaling to 2× output resolution is sufficient.

---

## Extending the App

### Adding a plugin-style feature
The `AppState` singleton is accessible everywhere:
```python
from app.core.app_state import AppState
state = AppState.instance()
projects = state.get_all_projects()
state.queue_project(project)
```

### Hooking into the render pipeline
Subclass `render_worker.RenderWorker` or post-process in `renderer.py` after the FFmpeg call.

### Adding a new panel/tab
1. Create widget in `app/gui/widgets/`
2. Add to `MainWindow._setup_ui()` tabs
3. Connect to AppState signals
