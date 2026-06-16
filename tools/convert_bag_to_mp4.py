#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs


DEFAULT_OUTPUT_ROOT = Path(os.environ.get("REALSENSE_OUTPUT_ROOT", "dataset"))


def convert_bag_to_mp4(bag_path, output_dir, fps=30, overwrite=False):
    bag_path = Path(bag_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bag_path.exists():
        raise FileNotFoundError(f"Bag file does not exist: {bag_path}")

    mp4_main_path = output_dir / f"{bag_path.stem}.mp4"
    mp4_color_path = output_dir / f"{bag_path.stem}_pure_color.mp4"
    mp4_depth_path = output_dir / f"{bag_path.stem}_pure_depth.mp4"
    outputs = [mp4_main_path, mp4_color_path, mp4_depth_path]

    if not overwrite:
        existing = [path for path in outputs if path.exists()]
        if existing:
            names = ", ".join(path.name for path in existing)
            raise FileExistsError(f"Output already exists: {names}. Use --overwrite to replace.")

    pipeline = rs.pipeline()
    config = rs.config()
    writer_main = None
    writer_color = None
    writer_depth = None
    started = False

    try:
        config.enable_device_from_file(str(bag_path), repeat_playback=False)
        profile = pipeline.start(config)
        started = True
        playback = profile.get_device().as_playback()
        playback.set_real_time(False)

        align = rs.align(rs.stream.color)
        colorizer = rs.colorizer()
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        frame_count = 0

        while True:
            try:
                frames = pipeline.wait_for_frames(timeout_ms=1000)
            except RuntimeError:
                break

            aligned_frames = align.process(frames)
            depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()
            if not depth_frame or not color_frame:
                continue

            color_img = np.asanyarray(color_frame.get_data())
            depth_colormap = np.asanyarray(colorizer.colorize(depth_frame).get_data())

            preview_color = cv2.resize(color_img, (640, 360))
            preview_depth = cv2.resize(depth_colormap, (640, 360))
            composite_main = np.hstack((preview_color, preview_depth))

            if writer_main is None:
                h_main, w_main = composite_main.shape[:2]
                h_raw, w_raw = color_img.shape[:2]

                writer_main = cv2.VideoWriter(str(mp4_main_path), fourcc, fps, (w_main, h_main))
                writer_color = cv2.VideoWriter(str(mp4_color_path), fourcc, fps, (w_raw, h_raw))
                writer_depth = cv2.VideoWriter(str(mp4_depth_path), fourcc, fps, (w_raw, h_raw))

                writers = [writer_main, writer_color, writer_depth]
                if not all(writer.isOpened() for writer in writers):
                    raise RuntimeError("Failed to open one or more MP4 writers.")

            writer_main.write(composite_main)
            writer_color.write(color_img)
            writer_depth.write(depth_colormap)
            frame_count += 1

        if frame_count == 0:
            raise RuntimeError(f"No frames were decoded from {bag_path}")

        return {
            "frames": frame_count,
            "preview": mp4_main_path,
            "color": mp4_color_path,
            "depth": mp4_depth_path,
        }
    finally:
        for writer in [writer_main, writer_color, writer_depth]:
            if writer is not None:
                writer.release()
        if started:
            pipeline.stop()


def collect_bag_paths(paths):
    if not paths:
        return sorted((DEFAULT_OUTPUT_ROOT / "bag").glob("*.bag"))

    bag_paths = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            bag_paths.extend(sorted(path.glob("*.bag")))
        else:
            bag_paths.append(path)
    return bag_paths


def main():
    parser = argparse.ArgumentParser(description="Convert RealSense .bag recordings to MP4 files.")
    parser.add_argument(
        "bags",
        nargs="*",
        help="Bag file(s) or directories. Defaults to $REALSENSE_OUTPUT_ROOT/bag/*.bag or dataset/bag/*.bag.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(DEFAULT_OUTPUT_ROOT / "mp4"),
        help="Directory for MP4 outputs. Default: $REALSENSE_OUTPUT_ROOT/mp4 or dataset/mp4",
    )
    parser.add_argument("--fps", type=int, default=30, help="Output video FPS. Default: 30")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing MP4 outputs.")
    args = parser.parse_args()

    bag_paths = collect_bag_paths(args.bags)
    if not bag_paths:
        raise SystemExit("No .bag files found.")

    for bag_path in bag_paths:
        print(f"Converting {bag_path} ...")
        result = convert_bag_to_mp4(
            bag_path=bag_path,
            output_dir=args.output_dir,
            fps=args.fps,
            overwrite=args.overwrite,
        )
        print(f"Done: {result['frames']} frames")
        print(f"  preview: {result['preview']}")
        print(f"  color:   {result['color']}")
        print(f"  depth:   {result['depth']}")


if __name__ == "__main__":
    main()
