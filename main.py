"""
VideoForge — Bulk Video Generator
Main entry point. Run: python main.py
"""

import sys
import os


def main():
    # ── Windows: UTF-8 console output ─────────────────────────────────────────
    if os.name == "nt":
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
                sys.stderr.reconfigure(encoding="utf-8")
            except Exception:
                pass

    # ── Qt6 high-DPI: env var BEFORE QApplication, no deprecated attributes ───
    # AA_EnableHighDpiScaling / AA_UseHighDpiPixmaps are removed in Qt6/PySide6.
    # Qt6 does high-DPI automatically; the rounding-policy env var is sufficient.
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette, QColor

    app = QApplication(sys.argv)
    app.setApplicationName("VideoForge")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("VideoForge")

    # ── Initialize app state ──────────────────────────────────────────────────
    from app.core.app_state import AppState
    state = AppState.instance()
    state.initialize()

    # ── Apply dark theme ──────────────────────────────────────────────────────
    from app.gui.theme import get_stylesheet
    app.setStyleSheet(get_stylesheet())

    # Force dark palette so native widgets inherit it on Windows
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor("#0f0f17"))
    palette.setColor(QPalette.WindowText,      QColor("#e8e8f0"))
    palette.setColor(QPalette.Base,            QColor("#1a1a2e"))
    palette.setColor(QPalette.AlternateBase,   QColor("#1e1e32"))
    palette.setColor(QPalette.Text,            QColor("#e8e8f0"))
    palette.setColor(QPalette.Button,          QColor("#1e1e32"))
    palette.setColor(QPalette.ButtonText,      QColor("#e8e8f0"))
    palette.setColor(QPalette.Highlight,       QColor("#6c63ff"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Link,            QColor("#a89fff"))
    palette.setColor(QPalette.ToolTipBase,     QColor("#1e1e32"))
    palette.setColor(QPalette.ToolTipText,     QColor("#e8e8f0"))
    palette.setColor(QPalette.PlaceholderText, QColor("#5a5a7a"))
    app.setPalette(palette)

    # ── CLI mode — skip GUI ───────────────────────────────────────────────────
    if "--cli" in sys.argv:
        idx = sys.argv.index("--cli")
        _run_cli(sys.argv[idx + 1:], state)
        sys.exit(0)

    # ── Launch main window ────────────────────────────────────────────────────
    from app.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    exit_code = app.exec()
    state.shutdown()
    sys.exit(exit_code)


def _run_cli(args: list, state):
    """
    Headless batch mode.
    Usage: python main.py --cli <folder> [folder2 ...] [--output <dir>] [--overwrite] [--no-subtitles]
    """
    import argparse
    from pathlib import Path
    from app.services.project_scanner import ProjectScanner
    from app.render.renderer import render_project

    parser = argparse.ArgumentParser(prog="videoforge --cli")
    parser.add_argument("folders", nargs="+", help="Project folder(s) to render")
    parser.add_argument("--output", "-o",  help="Output directory")
    parser.add_argument("--no-subtitles",  action="store_true")
    parser.add_argument("--overwrite",     action="store_true")
    parsed = parser.parse_args(args)

    scanner = ProjectScanner(recursive=True, auto_validate=True)
    projects = []
    for folder_str in parsed.folders:
        folder = Path(folder_str)
        if folder.is_dir():
            projects.extend(scanner.scan_folder(folder))

    print(f"Found {len(projects)} project(s)")
    success = fail = 0

    for project in projects:
        if not project.validation.valid:
            print(f"  SKIP  {project.name}  ({', '.join(project.validation.issues[:1])})")
            fail += 1
            continue

        if parsed.output:
            out_dir = Path(parsed.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            project.output_path = out_dir / f"{project.name}.mp4"
        else:
            project.output_path = project.folder / f"{project.name}_output.mp4"

        if parsed.no_subtitles:
            project.profile.subtitle_enabled = False

        print(f"  Rendering  {project.name} ...", flush=True)

        def _progress(pct, msg=""):
            bar = "=" * int(pct / 5) + " " * (20 - int(pct / 5))
            print(f"\r    [{bar}] {pct:5.1f}%  {msg[:40]:<40}", end="", flush=True)

        result = render_project(
            project,
            output_path=project.output_path,
            progress_callback=_progress,
            overwrite=parsed.overwrite,
        )
        print()
        if result.success:
            size = (result.metrics.output_size_bytes or 0) // (1024 * 1024)
            secs = result.metrics.render_time_seconds or 0
            print(f"  OK    {result.output_path.name}  ({size} MB, {secs:.0f}s)")
            success += 1
        else:
            print(f"  FAIL  {result.error}")
            fail += 1

    print(f"\nDone: {success} succeeded, {fail} failed")


if __name__ == "__main__":
    main()
