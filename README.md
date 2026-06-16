# RealSense Recorder For macOS

Minimal macOS repo for Intel RealSense D435 photo and video capture.

This is meant to run directly on macOS, not inside Docker Desktop. Docker on
macOS cannot reliably pass RealSense USB devices into Linux containers.

## What It Does

- Captures synchronized color and depth frames from RealSense.
- Saves snapshots under `dataset/snapshot/`.
- Records `.bag` files under `dataset/bag/`.
- Converts recorded `.bag` files into three MP4 outputs under `dataset/mp4/`:
  - side-by-side color/depth preview
  - pure color video
  - pure depth visualization video
- Opens a TCP control server on port `8888`.

## Requirements

- macOS on Apple Silicon or Intel Mac
- Python 3.11 recommended
- Intel RealSense D435 or compatible camera
- Camera connected directly to the Mac through a reliable USB 3 cable or hub

## Fast Setup On A New Mac

On the other Mac, run:

```bash
git clone git@github.com:Chiyu2003/realsense_recorder.git
cd realsense_recorder
./scripts/setup_new_mac.sh
```

If macOS opens the Xcode Command Line Tools installer, finish that installer and
then rerun:

```bash
./scripts/setup_new_mac.sh
```

The setup script will:

- check Xcode Command Line Tools
- install Homebrew packages: `cmake`, `pkg-config`, `libusb`, `openssl`, `python@3.11`
- create `.venv`
- install Python dependencies
- build Librealsense 2.57.7 with `FORCE_RSUSB_BACKEND=ON`
- install `pyrealsense2` into `.venv`

## Manual Setup

If you prefer to run each step yourself:

```bash
xcode-select --install
brew install cmake pkg-config libusb openssl python@3.11
./scripts/bootstrap_macos.sh
./scripts/build_librs_macos.sh
```

## Run

```bash
source .venv/bin/activate
python realsense_recorder.py
```

Keyboard controls in the OpenCV window:

- `s`: take snapshot
- `r`: start or stop recording
- `q`: quit safely

## Remote Control

The recorder listens on TCP port `8888`.

From the same Mac:

```bash
python tools/send_command.py s
python tools/send_command.py r
python tools/send_command.py q
```

From another device on the same network:

```bash
python tools/send_command.py s --host <mac-ip-address>
```

## Headless Mode

You can disable the OpenCV GUI and control the recorder through TCP only:

```bash
REALSENSE_HEADLESS=1 python realsense_recorder.py
```

Change output folder:

```bash
REALSENSE_OUTPUT_ROOT=output python realsense_recorder.py
```

## Files

- `realsense_recorder.py`: main recorder for local keyboard and TCP control.
- `remote_stream_server.py`: alternate server that also streams JPEG preview
  frames over TCP using a small binary packet protocol.
- `scripts/setup_new_mac.sh`: one-command setup for a fresh Mac after cloning.
- `scripts/build_librs_macos.sh`: rebuilds Librealsense 2.57.7 with the Apple
  Silicon-friendly Python binding settings.
- `scripts/install_realsense_artifact_macos.sh`: installs a prebuilt local
  RealSense artifact tarball into `.venv`.
- `tools/send_command.py`: tiny TCP command sender for testing.
- `docs/MAC_M_CHIP_REALSENSE.md`: details about the M chip Librealsense build.

## Troubleshooting

If RealSense initialization fails:

- Unplug and replug the camera.
- Use a USB 3 cable or powered hub.
- Close other apps that may be using the camera.
- Try running once from a normal Terminal, not inside an IDE terminal.

If `pyrealsense2` cannot install, check that Python is 3.11:

```bash
python3 --version
```
