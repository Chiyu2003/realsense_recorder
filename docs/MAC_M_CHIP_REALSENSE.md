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

If you are using the prebuilt Apple Silicon artifact, you only need Python 3.11
and the Python dependencies. Homebrew is not required if Python 3.11 is already
installed. If `wheelhouse/*.whl` is present, the Python dependencies install
locally without PyPI.

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

On macOS 12+ and newer, libusb access may require elevated privileges. If the
camera is visible in USB tools but stream startup fails with `failed to set
power state` or `No device connected`, run:

```bash
sudo env REALSENSE_STREAM_PROFILE=safe .venv/bin/python realsense_recorder.py
```

If the prebuilt artifact does not work on a Mac, rebuild Librealsense and
install `pyrealsense2` into `.venv`:

```bash
xcode-select --install
brew install cmake pkg-config libusb openssl
./scripts/build_librs_macos.sh
```

Then run:

```bash
source .venv/bin/activate
python realsense_recorder.py
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
d7e0807e439fd49260f0cb5cea3eeab86a040ac9909c10f30ba20ffa7a829f58
```

Compatibility:

- macOS `arm64` / Apple Silicon
- Python 3.11
- Librealsense 2.57.7
- Bundled `libusb-1.0.0.dylib`

Intel Macs should rebuild locally with `./scripts/build_librs_macos.sh`.

To refresh the artifact from a local build, run:

```bash
./scripts/collect_local_realsense_artifacts.sh
```

## Python Wheelhouse

The repo can also track Python wheels for Apple Silicon:

```text
wheelhouse/numpy-*.whl
wheelhouse/opencv_python-*.whl
```

To refresh them:

```bash
./scripts/collect_python_wheels_macos.sh
```

When `wheelhouse/` exists, `scripts/bootstrap_macos.sh` and
`scripts/install_realsense_artifact_macos.sh` install with `--no-index`, so the
other Mac does not need network access to PyPI.

The install script rewrites the copied binary paths to use `@loader_path`, so
the Python extension can find `librealsense2` inside the virtual environment
instead of looking for the original build directory from the first Mac.

## Why Not Docker?

Docker Desktop on macOS runs Linux inside a VM. RealSense USB passthrough is not
the same as native Linux `/dev/bus/usb`, so recorder capture should run directly
on macOS.
