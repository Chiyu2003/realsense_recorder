#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script is for macOS."
  exit 1
fi

cd "$ROOT_DIR"

echo "==> Checking Xcode Command Line Tools"
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Xcode Command Line Tools are missing."
  echo "A macOS installer prompt will open now. After it finishes, rerun:"
  echo "  ./scripts/setup_new_mac.sh"
  xcode-select --install
  exit 1
fi

echo "==> Checking Homebrew dependencies"
if command -v brew >/dev/null 2>&1; then
  brew install cmake pkg-config libusb openssl python@3.11
else
  echo "Homebrew is not installed."
  echo "Install Homebrew from https://brew.sh, then rerun:"
  echo "  ./scripts/setup_new_mac.sh"
  echo
  echo "Required packages: cmake pkg-config libusb openssl python@3.11"
  exit 1
fi

echo "==> Creating Python environment"
PYTHON_BIN=python3.11 ./scripts/bootstrap_macos.sh

echo "==> Building Librealsense for this Mac"
PYTHON_BIN=python3.11 ./scripts/build_librs_macos.sh

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
