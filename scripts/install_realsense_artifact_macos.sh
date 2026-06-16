#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
ARTIFACT_TARBALL="${1:-$ROOT_DIR/artifacts/realsense-macos-python311-2.57.7.tar.gz}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ ! -f "$ARTIFACT_TARBALL" ]]; then
  echo "Artifact not found: $ARTIFACT_TARBALL"
  echo "Build from source instead: ./scripts/build_librs_macos.sh"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  fi
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

tar -xzf "$ARTIFACT_TARBALL" -C "$TMP_DIR"
ARTIFACT_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name 'realsense-macos-python311-*' | head -n 1)"

if [[ -z "$ARTIFACT_DIR" ]]; then
  echo "Invalid artifact layout: $ARTIFACT_TARBALL"
  exit 1
fi

SITE_PACKAGES="$("$VENV_DIR/bin/python" - <<'PY'
import sysconfig
print(sysconfig.get_paths()["purelib"])
PY
)"

cp "$ARTIFACT_DIR"/librealsense2*.dylib "$SITE_PACKAGES"/
cp "$ARTIFACT_DIR"/pyrealsense2*.so "$SITE_PACKAGES"/

for so in "$SITE_PACKAGES"/pyrealsense2*.so; do
  install_name_tool \
    -change @rpath/librealsense2.2.57.dylib @loader_path/librealsense2.2.57.dylib \
    "$so" 2>/dev/null || true
  install_name_tool \
    -change @rpath/pyrealsense2.2.57.cpython-311-darwin.so @loader_path/pyrealsense2.2.57.cpython-311-darwin.so \
    "$so" 2>/dev/null || true
  install_name_tool -add_rpath @loader_path "$so" 2>/dev/null || true
  codesign --force --sign - "$so" >/dev/null 2>&1 || true
done

for dylib in "$SITE_PACKAGES"/librealsense2*.dylib; do
  codesign --force --sign - "$dylib" >/dev/null 2>&1 || true
done

python - <<'PY'
import pathlib
import pyrealsense2 as rs

print("pyrealsense2:", getattr(rs, "__version__", "import-ok"))
print("module:", pathlib.Path(rs.__file__).resolve())
PY

echo
echo "Artifact installed into: $SITE_PACKAGES"
