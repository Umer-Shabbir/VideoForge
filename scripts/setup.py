"""
VideoForge Windows Setup Script
Checks and installs all required dependencies.

Run from ANYWHERE:
    python scripts/setup.py
    python setup.py          (if you copied it to the root)
    cd scripts && python setup.py

All paths are resolved relative to the project root automatically.
"""

import sys
import subprocess
import os
import shutil
from pathlib import Path


# ─── Resolve project root robustly ────────────────────────────────────────────
# This script lives in <root>/scripts/setup.py  OR  <root>/setup.py
# We find the root by looking for both main.py AND requirements.txt

def _find_project_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent,           # scripts/  (script's own dir)
        Path(__file__).resolve().parent.parent,    # project root (one level up)
        Path.cwd(),                                # wherever the user ran from
        Path.cwd().parent,
    ]
    for c in candidates:
        if (c / "requirements.txt").exists() and (c / "main.py").exists():
            return c.resolve()
    # Final fallback: parent of script directory
    return Path(__file__).resolve().parent.parent


ROOT     = _find_project_root()
REQ_FILE = ROOT / "requirements.txt"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd, check=True, show_output=False):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if show_output and result.stdout:
        for line in result.stdout.splitlines()[-10:]:
            print(f"    {line}")
    if result.returncode != 0 and check:
        for line in (result.stderr or result.stdout or "").splitlines()[-15:]:
            print(f"    {line}")
    return result.returncode == 0, result.stdout, result.stderr


def _header(step, total, title):
    print(f"\n{'─'*55}")
    print(f"  [{step}/{total}] {title}")
    print(f"{'─'*55}")


# ─── Steps ────────────────────────────────────────────────────────────────────

def check_python():
    _header(1, 7, "Checking Python version")
    ver = sys.version_info
    print(f"  Python {ver.major}.{ver.minor}.{ver.micro}")
    print(f"  Executable: {sys.executable}")
    if ver < (3, 9):
        print(f"  ERROR: Python 3.9+ required. Download from https://python.org")
        sys.exit(1)
    print(f"  OK: Python version is supported")


def check_pip():
    _header(2, 7, "Checking pip")
    ok, out, _ = _run([sys.executable, "-m", "pip", "--version"], check=False)
    if ok:
        print(f"  OK: {out.strip()[:70]}")
    else:
        print("  pip not found. Attempting to bootstrap...")
        _run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)
        ok2, out2, _ = _run([sys.executable, "-m", "pip", "--version"], check=False)
        if ok2:
            print(f"  OK: {out2.strip()[:70]}")
        else:
            print("  ERROR: Could not install pip. Please reinstall Python.")
            sys.exit(1)


def install_requirements():
    _header(3, 7, "Installing Python packages from requirements.txt")
    print(f"  Project root : {ROOT}")
    print(f"  Requirements : {REQ_FILE}")
    print()

    if not REQ_FILE.exists():
        print(f"  ERROR: requirements.txt not found!")
        print()
        print(f"  Looked for it at: {REQ_FILE}")
        print()
        print(f"  This usually means one of:")
        print(f"    1. You are running this script from outside the VideoForge folder")
        print(f"    2. The ZIP was not fully extracted")
        print(f"    3. requirements.txt was accidentally deleted")
        print()
        print(f"  Fix:")
        print(f"    - Make sure you extracted the full VideoForge ZIP")
        print(f"    - Navigate INTO the VideoForge folder, then run:")
        print(f"        python scripts\\setup.py")
        print()
        print(f"  Or recreate requirements.txt by pasting this into a file called")
        print(f"  requirements.txt in your VideoForge folder:")
        print()
        _print_fallback_requirements()
        print()
        choice = input("  Create requirements.txt automatically now? (Y/n): ").strip().lower()
        if choice in ("", "y", "yes"):
            _write_fallback_requirements()
        else:
            sys.exit(1)

    # Show what will be installed
    lines = REQ_FILE.read_text(encoding="utf-8").splitlines()
    packages = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    print(f"  Installing {len(packages)} packages:")
    for pkg in packages:
        print(f"    {pkg}")
    print()

    ok, _, err = _run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQ_FILE), "--upgrade"],
        check=False, show_output=True
    )

    if ok:
        print(f"\n  OK: All packages installed successfully")
    else:
        print(f"\n  Some packages failed. Installing one by one...")
        _install_one_by_one(packages)


def _install_one_by_one(packages):
    failed = []
    for pkg in packages:
        ok, _, _ = _run([sys.executable, "-m", "pip", "install", pkg, "--upgrade"],
                        check=False)
        status = "OK" if ok else "FAILED"
        print(f"    {status}: {pkg}")
        if not ok:
            failed.append(pkg)
    if failed:
        print(f"\n  The following packages could not be installed:")
        for pkg in failed:
            print(f"    pip install {pkg}")
        print(f"\n  The app may still work but some features may be unavailable.")
    else:
        print(f"\n  OK: All packages installed")


def _print_fallback_requirements():
    reqs = [
        "PySide6>=6.5.0",
        "faster-whisper>=0.10.0",
        "mutagen>=1.46.0",
        "Pillow>=10.0.0",
        "humanize>=4.7.0",
        "python-docx>=0.8.11",
        "numpy>=1.24.0",
        "psutil>=5.9.0",
        "requests>=2.31.0",
    ]
    for r in reqs:
        print(f"    {r}")


def _write_fallback_requirements():
    content = "\n".join([
        "PySide6>=6.5.0",
        "faster-whisper>=0.10.0",
        "mutagen>=1.46.0",
        "Pillow>=10.0.0",
        "humanize>=4.7.0",
        "python-docx>=0.8.11",
        "numpy>=1.24.0",
        "psutil>=5.9.0",
        "requests>=2.31.0",
    ])
    REQ_FILE.write_text(content, encoding="utf-8")
    print(f"  Created: {REQ_FILE}")


def check_ffmpeg():
    _header(4, 7, "Checking FFmpeg")

    ffmpeg  = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    if ffmpeg and ffprobe:
        r = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True)
        ver = r.stdout.splitlines()[0] if r.stdout else "?"
        print(f"  OK: {ver[:70]}")
        print(f"  ffmpeg  -> {ffmpeg}")
        print(f"  ffprobe -> {ffprobe}")
        return

    # Check bundled / common Windows locations
    locations = [
        ROOT / "ffmpeg" / "bin",
        ROOT / "bin",
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/ffmpeg/bin"),
        Path.home() / "ffmpeg/bin",
        Path.home() / "AppData/Local/ffmpeg/bin",
    ]
    for loc in locations:
        if (loc / "ffmpeg.exe").exists():
            print(f"  Found at: {loc}")
            print(f"  WARNING: Not in PATH. Add {loc} to your system PATH,")
            print(f"  OR set the path manually in VideoForge Settings -> FFmpeg & Tools.")
            return

    print(f"  WARNING: FFmpeg not found.\n")
    print(f"  VideoForge needs FFmpeg to render videos.")
    print(f"  Install it using ONE of these methods:\n")
    print(f"  METHOD 1 - winget (easiest, Windows 10+):")
    print(f"    Open PowerShell and run:")
    print(f"      winget install \"FFmpeg (Essentials Build)\"")
    print(f"    Then close and re-open your terminal.\n")
    print(f"  METHOD 2 - Manual:")
    print(f"    1. Download from:")
    print(f"       https://github.com/BtbN/FFmpeg-Builds/releases")
    print(f"       (file: ffmpeg-master-latest-win64-gpl.zip)")
    print(f"    2. Extract it")
    print(f"    3. Move the folder to C:\\ffmpeg")
    print(f"    4. Add C:\\ffmpeg\\bin to your system PATH:")
    print(f"       Win+R -> sysdm.cpl -> Advanced -> Environment Variables")
    print(f"       -> System variables -> Path -> Edit -> New -> C:\\ffmpeg\\bin")
    print(f"    5. Click OK on all dialogs, restart terminal\n")
    print(f"  METHOD 3 - Set in app:")
    print(f"    Skip FFmpeg setup now. After launching VideoForge,")
    print(f"    go to Settings (gear icon) -> FFmpeg & Tools -> Browse")
    print(f"    and select your ffmpeg.exe file directly.\n")
    print(f"  You can continue setup and install FFmpeg later.")


def check_whisper():
    _header(5, 7, "Checking faster-whisper (subtitle sync)")

    try:
        import faster_whisper
        print(f"  OK: faster-whisper is installed")
        print(f"  Subtitle timing will use Whisper speech recognition.")
        print(f"  First render downloads the model (~250MB for 'small' model).")
        return
    except ImportError:
        pass

    print(f"  INFO: faster-whisper is not installed.")
    print(f"  Without it, subtitles use even text distribution (less precise).")
    print(f"  Recommended for accurate subtitle sync.\n")

    choice = input("  Install faster-whisper now? (Y/n): ").strip().lower()
    if choice in ("", "y", "yes"):
        ok, _, _ = _run(
            [sys.executable, "-m", "pip", "install", "faster-whisper"],
            check=False, show_output=True
        )
        if ok:
            print("  OK: faster-whisper installed")
        else:
            print("  FAILED. Try manually: pip install faster-whisper")
    else:
        print("  Skipped. Install later with: pip install faster-whisper")


def check_pillow():
    _header(6, 7, "Checking Pillow (image reading)")
    try:
        from PIL import Image
        import PIL
        print(f"  OK: Pillow {PIL.__version__}")
    except ImportError:
        print("  Pillow missing - installing...")
        ok, _, _ = _run([sys.executable, "-m", "pip", "install", "Pillow"], check=False)
        print("  OK: Pillow installed" if ok else "  FAILED: pip install Pillow")


def create_app_dirs():
    _header(7, 7, "Creating app data directories")
    try:
        sys.path.insert(0, str(ROOT))
        from app.storage.settings_manager import get_app_data_dir
        app_dir = get_app_data_dir()
    except Exception:
        # Fallback if app code not importable yet
        if os.name == "nt":
            app_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "VideoForge"
        else:
            app_dir = Path.home() / ".videoforge"

    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "logs").mkdir(exist_ok=True)
    print(f"  OK: {app_dir}")


def print_summary():
    print(f"\n{'='*55}")
    print(f"  Setup Complete!")
    print(f"{'='*55}")
    print(f"""
  LAUNCH THE APP:
    Double-click  launch.bat
    Or run:       python main.py

  QUICK START:
    1. Click [+ Add Folders] and select your project folder
    2. Each subfolder with audio + images = one project
    3. Valid projects get a green badge
    4. Click [Queue All Valid] to start rendering
    5. Output videos save next to each project folder

  EXAMPLE PROJECTS (to test immediately):
    python scripts\\create_examples.py
    Then add the 'example_projects' folder in the app.

  FULL GUIDE:
    docs\\INSTALLATION_GUIDE.md
    docs\\TROUBLESHOOTING.md
""")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print(f"  VideoForge - Setup")
    print(f"{'='*55}")
    print(f"  Script location : {Path(__file__).resolve()}")
    print(f"  Project root    : {ROOT}")

    check_python()
    check_pip()
    install_requirements()
    check_ffmpeg()
    check_whisper()
    check_pillow()
    create_app_dirs()
    print_summary()
