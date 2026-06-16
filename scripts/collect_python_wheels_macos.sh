#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
WHEELHOUSE_DIR="${WHEELHOUSE_DIR:-$ROOT_DIR/wheelhouse}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Cannot find PYTHON_BIN=$PYTHON_BIN"
  echo "Install Python 3.11 or rerun with:"
  echo "  PYTHON_BIN=/path/to/python3.11 ./scripts/collect_python_wheels_macos.sh"
  exit 1
fi

mkdir -p "$WHEELHOUSE_DIR"

"$PYTHON_BIN" -m pip download \
  --only-binary=:all: \
  --dest "$WHEELHOUSE_DIR" \
  -r "$ROOT_DIR/requirements.txt"

echo
echo "Created local wheelhouse:"
echo "  $WHEELHOUSE_DIR"
echo
echo "Commit the .whl files if you want another Apple Silicon Mac to install without PyPI."
