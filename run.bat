@echo off
setlocal

:: Set working directory to the directory of this batch file
cd /d "%~dp0"

echo ===================================================
echo             Starting VideoForge
echo ===================================================
echo.

:: 1. Check if uv is available (recommended and fast)
where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Launching with uv...
    uv run --with-requirements requirements.txt python main.py %*
    goto end
)

:: 2. Check if a local virtual environment exists
if exist ".venv\Scripts\python.exe" (
    echo Launching using local virtual environment (.venv)...
    ".venv\Scripts\python.exe" main.py %*
    goto end
)

if exist "venv\Scripts\python.exe" (
    echo Launching using local virtual environment (venv)...
    "venv\Scripts\python.exe" main.py %*
    goto end
)

:: 3. Check for Python Launcher (py)
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Launching with Python Launcher (py)...
    py -3.12 main.py %*
    if %ERRORLEVEL% neq 0 (
        py main.py %*
    )
    goto end
)

:: 4. Fallback to global python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Launching with python...
    python main.py %*
    goto end
)

echo [ERROR] No suitable Python interpreter or uv installation found.
echo Please install uv or Python (3.10+) and ensure dependencies are installed.
pause

:end
endlocal
