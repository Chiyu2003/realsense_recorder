#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
ARTIFACT_TARBALL="$ROOT_DIR/artifacts/realsense-macos-python311-2.57.7.tar.gz"
USE_PREBUILT=0

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script is for macOS."
  exit 1
fi

cd "$ROOT_DIR"

if [[ "$(uname -m)" == "arm64" && -f "$ARTIFACT_TARBALL" ]]; then
  USE_PREBUILT=1
fi

echo "==> Checking Python"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if [[ "$PYTHON_BIN" == "python3.11" && "$(command -v brew || true)" != "" ]]; then
    echo "Python 3.11 not found; installing python@3.11 with Homebrew"
    brew install python@3.11
  elif [[ "$USE_PREBUILT" == "1" ]]; then
    echo "Cannot find PYTHON_BIN=$PYTHON_BIN"
    echo "Install Python 3.11 from https://www.python.org/downloads/macos/ and rerun:"
    echo "  ./scripts/setup_new_mac.sh"
    echo
    echo "Or rerun with a custom Python 3.11 path:"
    echo "  PYTHON_BIN=/path/to/python3.11 ./scripts/setup_new_mac.sh"
    exit 1
  elif [[ "$PYTHON_BIN" == "python3.11" ]]; then
    echo "Cannot find python3.11 and Homebrew is not installed."
    echo "Install Homebrew from https://brew.sh or install Python 3.11 manually."
    exit 1
  else
    echo "Cannot find PYTHON_BIN=$PYTHON_BIN"
    exit 1
  fi
fi

if [[ "$USE_PREBUILT" == "1" ]]; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> Homebrew found, but not required for the prebuilt Apple Silicon artifact"
  else
    echo "==> Homebrew not found; continuing with the bundled prebuilt artifact"
  fi
else
  echo "==> Checking Xcode Command Line Tools"
  if ! xcode-select -p >/dev/null 2>&1; then
    echo "Xcode Command Line Tools are missing."
    echo "A macOS installer prompt will open now. After it finishes, rerun:"
    echo "  ./scripts/setup_new_mac.sh"
    xcode-select --install
    exit 1
  fi

  echo "==> Checking Homebrew build dependencies"
  BREW_PACKAGES=(cmake pkg-config libusb openssl)
  if command -v brew >/dev/null 2>&1; then
    brew install "${BREW_PACKAGES[@]}"
  else
    echo "Homebrew is not installed."
    echo "Install Homebrew from https://brew.sh, then rerun:"
    echo "  ./scripts/setup_new_mac.sh"
    echo
    echo "Required packages for local build: ${BREW_PACKAGES[*]}"
    exit 1
  fi
fi

echo "==> Creating Python environment"
PYTHON_BIN="$PYTHON_BIN" ./scripts/bootstrap_macos.sh

if [[ "$USE_PREBUILT" == "1" ]]; then
  echo "==> Installing prebuilt Librealsense artifact"
  PYTHON_BIN="$PYTHON_BIN" ./scripts/install_realsense_artifact_macos.sh "$ARTIFACT_TARBALL"
elif [[ "$(uname -m)" != "arm64" ]]; then
  echo "==> Prebuilt artifact is Apple Silicon arm64 only; building Librealsense for this Mac"
  PYTHON_BIN="$PYTHON_BIN" ./scripts/build_librs_macos.sh
else
  echo "==> Prebuilt artifact not found; building Librealsense for this Mac"
  PYTHON_BIN="$PYTHON_BIN" ./scripts/build_librs_macos.sh
fi

cat <<'EOF'

Setup complete.

Plug in the RealSense camera, then run:

  source .venv/bin/activate
  python realsense_recorder.py

Keyboard controls:
  s = take snapshot
  r = start/stop recording
  q = quit safely
EOF
