#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
WHEELHOUSE_DIR="${WHEELHOUSE_DIR:-$ROOT_DIR/wheelhouse}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

cd "$ROOT_DIR"

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate

if compgen -G "$WHEELHOUSE_DIR/*.whl" >/dev/null; then
  echo "Installing Python dependencies from local wheelhouse: $WHEELHOUSE_DIR"
  python -m pip install --no-index --find-links "$WHEELHOUSE_DIR" -r requirements.txt
else
  echo "Local wheelhouse not found; installing Python dependencies from PyPI."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

echo
echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
echo "Run recorder: python realsense_recorder.py"
echo
echo "If pyrealsense2 is missing on Apple Silicon, run:"
echo "  ./scripts/build_librs_macos.sh"
