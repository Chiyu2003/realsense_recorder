#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
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
