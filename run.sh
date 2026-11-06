#!/usr/bin/env bash
set -e

# Change directory to the script's directory
cd "$(dirname "$0")"

echo "==================================================="
echo "            Starting VideoForge"
echo "==================================================="
echo ""

# 1. Check if uv is available
if command -v uv >/dev/null 2>&1; then
    echo "Launching with uv..."
    exec uv run --with-requirements requirements.txt python main.py "$@"
fi

# 2. Check if a local virtual environment exists
if [ -f ".venv/bin/python" ]; then
    echo "Launching using local virtual environment (.venv)..."
    exec ".venv/bin/python" main.py "$@"
elif [ -f "venv/bin/python" ]; then
    echo "Launching using local virtual environment (venv)..."
    exec "venv/bin/python" main.py "$@"
fi

# 3. Check for python3
if command -v python3 >/dev/null 2>&1; then
    echo "Launching with python3..."
    exec python3 main.py "$@"
fi

# 4. Fallback to python
if command -v python >/dev/null 2>&1; then
    echo "Launching with python..."
    exec python main.py "$@"
fi

echo "[ERROR] No suitable Python interpreter or uv installation found."
echo "Please install uv or Python (3.10+) and ensure dependencies are installed."
exit 1
