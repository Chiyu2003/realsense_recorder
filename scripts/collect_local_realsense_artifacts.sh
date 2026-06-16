#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_RELEASE_DIR="${SOURCE_RELEASE_DIR:-$ROOT_DIR/../librealsense-2.57.7/build/Release}"
ARTIFACT_DIR="$ROOT_DIR/artifacts/realsense-macos-python311-2.57.7"

if [[ ! -d "$SOURCE_RELEASE_DIR" ]]; then
  echo "Cannot find build release directory: $SOURCE_RELEASE_DIR"
  echo "Set SOURCE_RELEASE_DIR=/path/to/librealsense/build/Release and retry."
  exit 1
fi

mkdir -p "$ARTIFACT_DIR"

cp "$SOURCE_RELEASE_DIR"/librealsense2.2.57.7.dylib "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/librealsense2.2.57.dylib "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/librealsense2.dylib "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/pyrealsense2.2.57.7.cpython-311-darwin.so "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/pyrealsense2.2.57.cpython-311-darwin.so "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/pyrealsense2.cpython-311-darwin.so "$ARTIFACT_DIR"/

for so in "$ARTIFACT_DIR"/pyrealsense2*.so; do
  install_name_tool \
    -change @rpath/librealsense2.2.57.dylib @loader_path/librealsense2.2.57.dylib \
    "$so" 2>/dev/null || true
  install_name_tool \
    -change @rpath/pyrealsense2.2.57.cpython-311-darwin.so @loader_path/pyrealsense2.2.57.cpython-311-darwin.so \
    "$so" 2>/dev/null || true
  install_name_tool -add_rpath @loader_path "$so" 2>/dev/null || true
  codesign --force --sign - "$so" >/dev/null 2>&1 || true
done

for dylib in "$ARTIFACT_DIR"/librealsense2*.dylib; do
  codesign --force --sign - "$dylib" >/dev/null 2>&1 || true
done

tar -C "$ROOT_DIR/artifacts" -czf \
  "$ROOT_DIR/artifacts/realsense-macos-python311-2.57.7.tar.gz" \
  "realsense-macos-python311-2.57.7"

echo "Created: $ROOT_DIR/artifacts/realsense-macos-python311-2.57.7.tar.gz"
echo "Do not commit artifacts by default; upload it to GitHub Releases if needed."
