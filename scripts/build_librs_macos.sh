#!/usr/bin/env bash
set -euo pipefail

LIBRS_VERSION="${LIBRS_VERSION:-2.57.7}"
BUILD_JOBS="${BUILD_JOBS:-4}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
SOURCE_DIR="${SOURCE_DIR:-$ROOT_DIR/third_party/librealsense-$LIBRS_VERSION}"
BUILD_DIR="${BUILD_DIR:-$SOURCE_DIR/build-macos}"
ARCHIVE="$ROOT_DIR/third_party/librealsense-$LIBRS_VERSION.tar.gz"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  fi
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required. Install it with: brew install cmake"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required. Install Xcode Command Line Tools with: xcode-select --install"
  exit 1
fi

BREW_PREFIX=""
if command -v brew >/dev/null 2>&1; then
  BREW_PREFIX="$(brew --prefix)"
fi

mkdir -p "$ROOT_DIR/third_party"

if [[ ! -d "$SOURCE_DIR" ]]; then
  if [[ -f "$ARCHIVE" ]]; then
    tar -xzf "$ARCHIVE" -C "$ROOT_DIR/third_party"
  else
    curl -L \
      "https://github.com/IntelRealSense/librealsense/archive/refs/tags/v$LIBRS_VERSION.tar.gz" \
      -o "$ARCHIVE"
    tar -xzf "$ARCHIVE" -C "$ROOT_DIR/third_party"
  fi
fi

CMAKE_PREFIX_ARGS=()
if [[ -n "$BREW_PREFIX" ]]; then
  CMAKE_PREFIX_ARGS+=("-DCMAKE_PREFIX_PATH=$BREW_PREFIX")
fi

cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$VENV_DIR" \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_GRAPHICAL_EXAMPLES=OFF \
  -DBUILD_TOOLS=OFF \
  -DBUILD_UNIT_TESTS=OFF \
  -DBUILD_PYTHON_BINDINGS=ON \
  -DCHECK_FOR_UPDATES=OFF \
  -DFORCE_RSUSB_BACKEND=ON \
  -DPYTHON_EXECUTABLE="$VENV_DIR/bin/python" \
  "${CMAKE_PREFIX_ARGS[@]}"

cmake --build "$BUILD_DIR" --parallel "$BUILD_JOBS"
cmake --install "$BUILD_DIR"

python - <<'PY'
import pathlib
import pyrealsense2 as rs

print("pyrealsense2:", getattr(rs, "__version__", "import-ok"))
print("module:", pathlib.Path(rs.__file__).resolve())
PY

echo
echo "Librealsense build complete."
echo "Run recorder with:"
echo "  source .venv/bin/activate"
echo "  python realsense_recorder.py"
