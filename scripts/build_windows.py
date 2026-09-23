"""
VideoForge Windows Build Script
Creates a standalone executable using PyInstaller.
Run from the project root: python scripts/build_windows.py
"""

import sys
import subprocess
import shutil
import os
from pathlib import Path


ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "_pyinstaller"


def check_pyinstaller():
    try:
        import PyInstaller
        print(f"  ✅ PyInstaller {PyInstaller.__version__}")
        return True
    except ImportError:
        print("  Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        return True


def clean_build():
    print("\n[1/4] Cleaning previous build...")
    for d in [DIST / "VideoForge", BUILD]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed: {d}")


def ensure_assets():
    print("\n[2/4] Ensuring assets exist...")
    assets_dir = ROOT / "assets" / "icons"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Create a minimal .ico if none exists
    ico = assets_dir / "app.ico"
    if not ico.exists():
        print("  ⚠️  No app.ico found. Skipping icon.")

    presets_dir = ROOT / "presets"
    presets_dir.mkdir(exist_ok=True)


def run_pyinstaller():
    print("\n[3/4] Running PyInstaller...")
    spec_file = ROOT / "build" / "VideoForge.spec"

    if not spec_file.exists():
        print(f"  ❌ Spec file not found: {spec_file}")
        return False

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--noconfirm",
    ]
    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode == 0


def package_output():
    print("\n[4/4] Packaging output...")
    exe_dir = DIST / "VideoForge"
    if not exe_dir.exists():
        print("  ❌ Build output not found")
        return

    # Copy extra files
    for fname in ["README.md", "launch.bat", "requirements.txt"]:
        src = ROOT / fname
        if src.exists():
            shutil.copy2(src, exe_dir / fname)
            print(f"  Copied: {fname}")

    # Copy docs
    docs_src = ROOT / "docs"
    if docs_src.exists():
        shutil.copytree(docs_src, exe_dir / "docs", dirs_exist_ok=True)
        print("  Copied: docs/")

    # Check for NSIS to make installer
    nsis = shutil.which("makensis")
    if nsis:
        print("  NSIS found — creating installer...")
        _build_nsis_installer(exe_dir)
    else:
        print("  NSIS not found — skipping installer creation")
        print("  Install NSIS from https://nsis.sourceforge.io/ for .exe installer")

    # Create ZIP archive
    archive = DIST / "VideoForge-Windows"
    shutil.make_archive(str(archive), "zip", str(DIST), "VideoForge")
    print(f"  ✅ ZIP archive: {archive}.zip")
    print(f"\n  ✅ Build complete: {exe_dir}")
    print(f"     Run: {exe_dir / 'VideoForge.exe'}")


def _build_nsis_installer(exe_dir: Path):
    """Generate and run an NSIS installer script."""
    nsis_script = DIST / "installer.nsi"
    script = f'''
!include "MUI2.nsh"
Name "VideoForge"
OutFile "{DIST / "VideoForge-Installer.exe"}"
InstallDir "$PROGRAMFILES64\\VideoForge"
InstallDirRegKey HKCU "Software\\VideoForge" ""
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "VideoForge" SecMain
  SetOutPath "$INSTDIR"
  File /r "{exe_dir}\\*.*"
  CreateDirectory "$SMPROGRAMS\\VideoForge"
  CreateShortcut "$SMPROGRAMS\\VideoForge\\VideoForge.lnk" "$INSTDIR\\VideoForge.exe"
  CreateShortcut "$DESKTOP\\VideoForge.lnk" "$INSTDIR\\VideoForge.exe"
  WriteRegStr HKCU "Software\\VideoForge" "" "$INSTDIR"
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\\VideoForge.lnk"
  Delete "$SMPROGRAMS\\VideoForge\\VideoForge.lnk"
  RMDir "$SMPROGRAMS\\VideoForge"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\\VideoForge"
SectionEnd
'''
    nsis_script.write_text(script)
    subprocess.run(["makensis", str(nsis_script)])
    nsis_script.unlink()


if __name__ == "__main__":
    print("="*60)
    print("  VideoForge Windows Build")
    print("="*60)

    check_pyinstaller()
    clean_build()
    ensure_assets()
    ok = run_pyinstaller()
    if ok:
        package_output()
    else:
        print("\n❌ Build failed. Check output above.")
        sys.exit(1)
