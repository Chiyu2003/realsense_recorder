# RealSense Recorder For macOS

Minimal macOS repo for Intel RealSense D435 photo and video capture.

This is meant to run directly on macOS, not inside Docker Desktop. Docker on
macOS cannot reliably pass RealSense USB devices into Linux containers.

## What It Does

- Captures synchronized color and depth frames from RealSense.
- Saves snapshots under `dataset/snapshot/`.
- Records `.bag` files under `dataset/bag/`.
- Converts recorded `.bag` files later with a separate tool into three MP4
  outputs under `dataset/mp4/`:
  - side-by-side color/depth preview
  - pure color video
  - pure depth visualization video
- Opens a TCP control server on port `8888`.
- Includes a prebuilt macOS Python 3.11 RealSense artifact so most users do
  not need to compile Librealsense from source.

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
- install Homebrew packages: `cmake`, `pkg-config`, `libusb`, `openssl`
- use your existing `python3.11`, or install `python@3.11` with Homebrew if missing
- create `.venv`
- install Python dependencies
- install the prebuilt Apple Silicon Librealsense 2.57.7 artifact from `artifacts/` when available
- build Librealsense 2.57.7 with `FORCE_RSUSB_BACKEND=ON` only if the artifact is missing
  or the Mac is Intel
- install `pyrealsense2` into `.venv`

If Python 3.11 is installed at a custom path:

```bash
PYTHON_BIN=/path/to/python3.11 ./scripts/setup_new_mac.sh
```

## Manual Setup

If you prefer to run each step yourself:

```bash
xcode-select --install
brew install cmake pkg-config libusb openssl
./scripts/bootstrap_macos.sh
./scripts/install_realsense_artifact_macos.sh
```

If the prebuilt artifact does not work on a Mac, rebuild locally:

```bash
./scripts/build_librs_macos.sh
```

## Included Prebuilt RealSense Artifact

This repo tracks:

```text
artifacts/realsense-macos-python311-2.57.7.tar.gz
```

It contains the compiled `librealsense2` dynamic libraries and `pyrealsense2`
Python 3.11 extension from the original Mac build.

SHA256:

```text
5167537bf6a73455fac1bf87ae0a438f6464ad244028d857d1e3916939c1ec5c
```

Compatibility notes:

- Intended for Apple Silicon macOS with Python 3.11.
- Built from Librealsense 2.57.7.
- Binary architecture: `arm64`.
- Uses the `FORCE_RSUSB_BACKEND=ON` build style that works better on Apple
  Silicon Macs.
- Intel Macs should run `./scripts/build_librs_macos.sh` instead.
- If another Apple Silicon Mac cannot import `pyrealsense2`, run
  `./scripts/build_librs_macos.sh` on that Mac instead.

## Run

```bash
source .venv/bin/activate
python realsense_recorder.py
```

Keyboard controls in the OpenCV window:

- `s`: take snapshot
- `r`: start or stop recording
- `q`: quit safely

Recording only saves a `.bag` file. It does not convert to MP4 while recording,
so capture stays lighter and less likely to drop frames.

## Convert Recordings

Convert one recording:

```bash
python tools/convert_bag_to_mp4.py dataset/bag/video_YYYYMMDD_HHMMSS.bag
```

Convert every `.bag` file under `dataset/bag/`:

```bash
python tools/convert_bag_to_mp4.py
```

The converter writes:

- `dataset/mp4/video_*.mp4`: side-by-side color/depth preview
- `dataset/mp4/video_*_pure_color.mp4`: pure color video
- `dataset/mp4/video_*_pure_depth.mp4`: pure depth visualization video

If the MP4 files already exist, add `--overwrite`:

```bash
python tools/convert_bag_to_mp4.py --overwrite
```

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

Use the same environment variable when converting recordings from that folder:

```bash
REALSENSE_OUTPUT_ROOT=output python tools/convert_bag_to_mp4.py
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
- `tools/convert_bag_to_mp4.py`: converts saved `.bag` recordings into MP4
  files after capture.
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
