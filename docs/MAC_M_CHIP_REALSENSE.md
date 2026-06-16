# Apple Silicon RealSense Build Notes

This repo is set up for the same Librealsense build style that was used on the
original M chip Mac:

- Librealsense version: `2.57.7`
- Python: `3.11`
- CMake build type: `Release`
- `BUILD_PYTHON_BINDINGS=ON`
- `FORCE_RSUSB_BACKEND=ON`
- `CHECK_FOR_UPDATES=OFF`

`FORCE_RSUSB_BACKEND=ON` is the important Apple Silicon part. It avoids relying
on the normal Linux-style RealSense backend and is the setting that made the
camera usable on macOS.

## Recommended Setup

Install Xcode Command Line Tools:

```bash
xcode-select --install
```

Install build tools:

```bash
brew install cmake pkg-config libusb openssl
```

Create the Python environment:

```bash
./scripts/bootstrap_macos.sh
```

Install the prebuilt artifact that is committed in this repo:

```bash
./scripts/install_realsense_artifact_macos.sh
```

Then run:

```bash
source .venv/bin/activate
python realsense_recorder.py
```

If the prebuilt artifact does not work on a Mac, rebuild Librealsense and
install `pyrealsense2` into `.venv`:

```bash
./scripts/build_librs_macos.sh
```

## If Build Is Slow

Use fewer or more build jobs:

```bash
BUILD_JOBS=2 ./scripts/build_librs_macos.sh
BUILD_JOBS=8 ./scripts/build_librs_macos.sh
```

## Binary Artifact In This Repo

The full CMake build directory is large and machine-specific, so this repo only
tracks the small packaged runtime artifact:

```text
artifacts/realsense-macos-python311-2.57.7.tar.gz
```

SHA256:

```text
5167537bf6a73455fac1bf87ae0a438f6464ad244028d857d1e3916939c1ec5c
```

Compatibility:

- macOS `arm64` / Apple Silicon
- Python 3.11
- Librealsense 2.57.7

Intel Macs should rebuild locally with `./scripts/build_librs_macos.sh`.

To refresh the artifact from a local build, run:

```bash
./scripts/collect_local_realsense_artifacts.sh
```

The install script rewrites the copied binary paths to use `@loader_path`, so
the Python extension can find `librealsense2` inside the virtual environment
instead of looking for the original build directory from the first Mac.

## Why Not Docker?

Docker Desktop on macOS runs Linux inside a VM. RealSense USB passthrough is not
the same as native Linux `/dev/bus/usb`, so recorder capture should run directly
on macOS.
