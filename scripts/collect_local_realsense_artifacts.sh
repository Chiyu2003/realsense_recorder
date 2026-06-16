#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_RELEASE_DIR="${SOURCE_RELEASE_DIR:-$ROOT_DIR/../librealsense-2.57.7/build/Release}"
LIBUSB_DYLIB="${LIBUSB_DYLIB:-/opt/homebrew/opt/libusb/lib/libusb-1.0.0.dylib}"
ARTIFACT_DIR="$ROOT_DIR/artifacts/realsense-macos-python311-2.57.7"

if [[ ! -d "$SOURCE_RELEASE_DIR" ]]; then
  echo "Cannot find build release directory: $SOURCE_RELEASE_DIR"
  echo "Set SOURCE_RELEASE_DIR=/path/to/librealsense/build/Release and retry."
  exit 1
fi

if [[ ! -f "$LIBUSB_DYLIB" ]]; then
  echo "Cannot find libusb dylib: $LIBUSB_DYLIB"
  echo "Set LIBUSB_DYLIB=/path/to/libusb-1.0.0.dylib and retry."
  exit 1
fi

mkdir -p "$ARTIFACT_DIR"

cp "$SOURCE_RELEASE_DIR"/librealsense2.2.57.7.dylib "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/librealsense2.2.57.dylib "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/librealsense2.dylib "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/pyrealsense2.2.57.7.cpython-311-darwin.so "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/pyrealsense2.2.57.cpython-311-darwin.so "$ARTIFACT_DIR"/
cp "$SOURCE_RELEASE_DIR"/pyrealsense2.cpython-311-darwin.so "$ARTIFACT_DIR"/
cp "$LIBUSB_DYLIB" "$ARTIFACT_DIR"/

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

for dylib in "$ARTIFACT_DIR"/*.dylib; do
  install_name_tool \
    -change /opt/homebrew/opt/libusb/lib/libusb-1.0.0.dylib @loader_path/libusb-1.0.0.dylib \
    "$dylib" 2>/dev/null || true
  install_name_tool -id "@loader_path/$(basename "$dylib")" "$dylib" 2>/dev/null || true
  codesign --force --sign - "$dylib" >/dev/null 2>&1 || true
done

tar -C "$ROOT_DIR/artifacts" -czf \
  "$ROOT_DIR/artifacts/realsense-macos-python311-2.57.7.tar.gz" \
  "realsense-macos-python311-2.57.7"

echo "Created: $ROOT_DIR/artifacts/realsense-macos-python311-2.57.7.tar.gz"
echo "This repo is configured to commit the tarball, but not the extracted artifact directory."
