"""
FFmpeg utilities: path detection, version probing, media info extraction,
and subprocess execution with full stderr logging.
"""

import subprocess
import json
import shutil
import os
import re
import threading
from pathlib import Path
from typing import Optional
import logging

log = logging.getLogger("videoforge.ffmpeg_utils")

_ffmpeg_path: Optional[str] = None
_ffprobe_path: Optional[str] = None
_ffmpeg_version_cache: Optional[str] = None   # cached so -version isn't run during renders
_ffmpeg_ready_cache: Optional[tuple] = None    # (ok, msg)


def find_ffmpeg(custom_path: Optional[str] = None) -> Optional[str]:
    global _ffmpeg_path
    if _ffmpeg_path:
        return _ffmpeg_path
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path:
        candidates.append(env_path)
    from_path = shutil.which("ffmpeg")
    if from_path:
        candidates.append(from_path)

    app_dir = Path(__file__).parent.parent.parent
    candidates += [
        str(app_dir / "ffmpeg" / "ffmpeg.exe"),
        str(app_dir / "ffmpeg" / "ffmpeg"),
        str(app_dir / "ffmpeg.exe"),
        str(app_dir / "ffmpeg"),
        str(app_dir / "bin" / "ffmpeg.exe"),
        str(app_dir / "bin" / "ffmpeg"),
    ]

    if os.name == "nt":
        sys_drive = os.environ.get("SystemDrive", "C:")
        prog_files = os.environ.get("ProgramFiles", rf"{sys_drive}\Program Files")
        candidates += [
            rf"{sys_drive}\ffmpeg\bin\ffmpeg.exe",
            rf"{prog_files}\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe"),
            os.path.expanduser(r"~\AppData\Local\ffmpeg\bin\ffmpeg.exe"),
        ]
    else:
        candidates += [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",
            os.path.expanduser("~/bin/ffmpeg"),
            os.path.expanduser("~/.local/bin/ffmpeg"),
        ]

    for c in candidates:
        p = Path(c)
        if p.is_file():
            _ffmpeg_path = str(p)
            log.info(f"Found ffmpeg at: {_ffmpeg_path}")
            return _ffmpeg_path
    log.warning("ffmpeg not found")
    return None


def find_ffprobe(custom_path: Optional[str] = None) -> Optional[str]:
    global _ffprobe_path
    if _ffprobe_path:
        return _ffprobe_path
    env_path = os.environ.get("FFPROBE_PATH")
    if env_path and Path(env_path).is_file():
        _ffprobe_path = env_path
        return _ffprobe_path
    ffmpeg = find_ffmpeg(custom_path)
    if ffmpeg:
        for name in ("ffprobe.exe", "ffprobe"):
            probe = Path(ffmpeg).parent / name
            if probe.is_file():
                _ffprobe_path = str(probe)
                return _ffprobe_path
    from_path = shutil.which("ffprobe")
    if from_path:
        _ffprobe_path = from_path
        return _ffprobe_path
    if os.name != "nt":
        for loc in (
            "/usr/bin/ffprobe",
            "/usr/local/bin/ffprobe",
            "/opt/homebrew/bin/ffprobe",
            os.path.expanduser("~/bin/ffprobe"),
            os.path.expanduser("~/.local/bin/ffprobe"),
        ):
            if Path(loc).is_file():
                _ffprobe_path = loc
                return _ffprobe_path
    return None


def reset_cached_paths():
    """Reset all cached paths and version info (backward-compat alias for invalidate_ffmpeg_cache)."""
    invalidate_ffmpeg_cache()


def get_ffmpeg_version(ffmpeg_bin: Optional[str] = None, use_cache: bool = True) -> Optional[str]:
    """Get FFmpeg version string. Cached after first call to avoid timeout during renders."""
    global _ffmpeg_version_cache
    if use_cache and _ffmpeg_version_cache:
        return _ffmpeg_version_cache
    binary = ffmpeg_bin or find_ffmpeg()
    if not binary:
        return None
    try:
        result = subprocess.run([binary, "-version"], capture_output=True,
                                text=True, timeout=8)
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        m = re.search(r"ffmpeg version ([\S]+)", first_line)
        ver = m.group(1) if m else first_line[:60]
        _ffmpeg_version_cache = ver
        return ver
    except Exception as e:
        log.error(f"ffmpeg version check failed: {e}")
        return None


def probe_media(path: Path, ffprobe_bin: Optional[str] = None) -> Optional[dict]:
    binary = ffprobe_bin or find_ffprobe()
    if not binary:
        log.error("ffprobe not found")
        return None
    try:
        cmd = [binary, "-v", "quiet", "-print_format", "json",
               "-show_format", "-show_streams", str(path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log.error(f"ffprobe error for {path}: {result.stderr[:300]}")
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.error(f"ffprobe timed out for {path}")
        return None
    except Exception as e:
        log.error(f"ffprobe failed for {path}: {e}")
        return None


def get_audio_duration(path: Path, ffprobe_bin: Optional[str] = None) -> Optional[float]:
    info = probe_media(path, ffprobe_bin)
    if not info:
        return None
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError):
        pass
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            try:
                return float(stream["duration"])
            except (KeyError, ValueError):
                pass
    return None


def get_media_info(path: Path, ffprobe_bin: Optional[str] = None) -> dict:
    result = {
        "duration": None, "bitrate": None, "codec": None,
        "sample_rate": None, "channels": None,
        "width": None, "height": None, "valid": False
    }
    info = probe_media(path, ffprobe_bin)
    if not info:
        return result
    fmt = info.get("format", {})
    try:
        result["duration"] = float(fmt.get("duration", 0))
        result["bitrate"] = int(fmt.get("bit_rate", 0))
        result["valid"] = True
    except (ValueError, TypeError):
        pass
    for stream in info.get("streams", []):
        codec_type = stream.get("codec_type", "")
        if codec_type == "audio" and not result["codec"]:
            result["codec"] = stream.get("codec_name")
            try:
                result["sample_rate"] = int(stream.get("sample_rate", 0))
                result["channels"] = int(stream.get("channels", 0))
                if not result["duration"]:
                    result["duration"] = float(stream.get("duration", 0))
            except (ValueError, TypeError):
                pass
        elif codec_type == "video":
            try:
                result["width"] = int(stream.get("width", 0))
                result["height"] = int(stream.get("height", 0))
            except (ValueError, TypeError):
                pass
    return result


def get_image_size(path: Path) -> Optional[tuple]:
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception as e:
        log.warning(f"Could not read image size for {path}: {e}")
        return None


def run_ffmpeg(
    cmd: list,
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
    progress_callback=None,
    log_callback=None,
    expected_duration: Optional[float] = None,
) -> tuple:
    """
    Run an FFmpeg command, capturing all output.
    Returns (returncode, stdout, stderr).

    Full stderr is always logged at DEBUG level.
    On failure, full stderr is logged at ERROR level.
    """
    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        return -1, "", "ffmpeg not found"

    cmd = list(cmd)
    if cmd[0] == "ffmpeg":
        cmd[0] = ffmpeg_bin

    if "-nostdin" not in cmd:
        cmd.insert(1, "-nostdin")

    # ── Command logging ───────────────────────────────────────────────────────
    cmd_str = " ".join(str(a) for a in cmd)
    log.info(f"FFmpeg command: {cmd_str}")

    stderr_lines = []
    stdout_chunks = []
    duration_total = expected_duration if (expected_duration and expected_duration > 0) else None

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def _read_stdout():
            try:
                if process.stdout:
                    for line in process.stdout:
                        stdout_chunks.append(line)
            except (ValueError, OSError):
                pass

        def _read_stderr():
            nonlocal duration_total
            try:
                if process.stderr:
                    for line in process.stderr:
                        line = line.rstrip()
                        if not line:
                            continue
                        stderr_lines.append(line)
                        if log_callback:
                            log_callback(line)
                        # Progress parsing
                        if "Duration:" in line and duration_total is None:
                            m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", line)
                            if m:
                                h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                                duration_total = h * 3600 + mn * 60 + s
                        if "time=" in line and duration_total and progress_callback:
                            m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
                            if m:
                                h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                                elapsed = h * 3600 + mn * 60 + s
                                progress_callback(min(100.0, elapsed / duration_total * 100))
            except (ValueError, OSError):
                pass

        t_err = threading.Thread(target=_read_stderr, daemon=True)
        t_out = threading.Thread(target=_read_stdout, daemon=True)
        t_err.start()
        t_out.start()

        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            t_err.join(timeout=3)
            t_out.join(timeout=3)
            return -2, "", "FFmpeg process timed out"

        t_err.join(timeout=8)
        t_out.join(timeout=8)

        rc = process.returncode
        full_stderr = "\n".join(stderr_lines)
        full_stdout = "".join(stdout_chunks)

        # Always log full stderr at debug level
        if full_stderr:
            log.debug(f"FFmpeg stderr:\n{full_stderr}")

        # On failure, log the full stderr at ERROR level so it's visible
        if rc != 0:
            log.error(
                f"FFmpeg exited with code {rc}.\n"
                f"Command: {cmd_str[:300]}\n"
                f"Full stderr:\n{full_stderr}"
            )

        return rc, full_stdout, full_stderr

    except Exception as e:
        log.error(f"FFmpeg Popen failed: {e}")
        return -3, "", str(e)


def _del_temp(path: Optional[str]):
    if path:
        try:
            os.unlink(path)
        except Exception:
            pass


def check_ffmpeg_ready(force: bool = False) -> tuple:
    """
    Check if FFmpeg is ready. Cached after first successful check.
    Pass force=True to bypass cache (e.g. after changing FFmpeg path in settings).
    """
    global _ffmpeg_ready_cache
    if not force and _ffmpeg_ready_cache is not None:
        return _ffmpeg_ready_cache

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        result = False, (
            "FFmpeg not found. Install it (winget install ffmpeg) "
            "or set the path in Settings → FFmpeg & Tools."
        )
        _ffmpeg_ready_cache = result
        return result
    ffprobe = find_ffprobe()
    if not ffprobe:
        result = False, "ffprobe not found — it must be in the same folder as ffmpeg."
        _ffmpeg_ready_cache = result
        return result
    version = get_ffmpeg_version(ffmpeg, use_cache=not force)
    if not version:
        result = False, "FFmpeg found but version check failed."
        _ffmpeg_ready_cache = result
        return result
    result = True, f"FFmpeg {version} ready"
    _ffmpeg_ready_cache = result
    return result


def invalidate_ffmpeg_cache():
    """Call when the FFmpeg path is changed in settings."""
    global _ffmpeg_path, _ffprobe_path, _ffmpeg_version_cache, _ffmpeg_ready_cache
    _ffmpeg_path = None
    _ffprobe_path = None
    _ffmpeg_version_cache = None
    _ffmpeg_ready_cache = None
