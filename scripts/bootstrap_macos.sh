#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
echo "Run recorder: python realsense_recorder.py"
echo
echo "If pyrealsense2 is missing on Apple Silicon, run:"
echo "  ./scripts/build_librs_macos.sh"
