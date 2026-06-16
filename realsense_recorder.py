import cv2
import numpy as np
import pyrealsense2 as rs
import datetime
import os
import signal
import time
import threading
import socket
from dataclasses import dataclass
from pathlib import Path

# 全域生命週期變數
running = True  
is_recording = False
pipeline_runtimes = []

# 1. 建立結構化目錄
OUTPUT_ROOT = Path(os.environ.get("REALSENSE_OUTPUT_ROOT", "dataset"))
GUI_ENABLED = os.environ.get("REALSENSE_HEADLESS", "0").lower() not in {
    "1",
    "true",
    "yes",
}
BAG_DIR = OUTPUT_ROOT / "bag"
MP4_DIR = OUTPUT_ROOT / "mp4"
SNAPSHOT_ROOT = OUTPUT_ROOT / "snapshot"
COLOR_DIR = SNAPSHOT_ROOT / "color"
DEPTH_VIS_DIR = SNAPSHOT_ROOT / "depth_vis"
DEPTH_RAW_DIR = SNAPSHOT_ROOT / "depth_raw"

for d in [BAG_DIR, MP4_DIR, COLOR_DIR, DEPTH_VIS_DIR, DEPTH_RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def handle_shutdown_signal(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# 2. RealSense stream profiles. Single-camera auto tries high first; multi-camera auto uses safe first.
STREAM_PROFILES = [
    {"name": "high", "depth": (640, 480, 30), "color": (1280, 720, 15)},
    {"name": "safe", "depth": (640, 480, 30), "color": (640, 480, 30)},
]
REQUESTED_STREAM_PROFILE = os.environ.get("REALSENSE_STREAM_PROFILE", "auto").lower()
CAMERA_COUNT = int(os.environ.get("REALSENSE_CAMERA_COUNT", "2"))


@dataclass
class CameraRuntime:
    index: int
    serial: str
    name: str
    pipeline: object
    profile: object
    stream_profile: dict
    align: object
    colorizer: object
    intrinsics: object = None
    recorder: object = None
    current_bag_path: Path = None


def make_config(profile, serial=None):
    config = rs.config()
    if serial:
        config.enable_device(serial)
    depth_w, depth_h, depth_fps = profile["depth"]
    color_w, color_h, color_fps = profile["color"]
    config.enable_stream(rs.stream.depth, depth_w, depth_h, rs.format.z16, depth_fps)
    config.enable_stream(rs.stream.color, color_w, color_h, rs.format.bgr8, color_fps)
    return config


def reset_realsense_devices():
    try:
        devices = rs.context().query_devices()
        if len(devices) == 0:
            return False
        print("🔄 [硬體重置] 正在送出 RealSense hardware reset...")
        for dev in devices:
            dev.hardware_reset()
        time.sleep(5.0)
        return True
    except Exception as e:
        print(f"⚠️ [硬體重置] 無法 reset RealSense: {e}")
        return False


def get_connected_devices():
    devices = []
    for dev in rs.context().query_devices():
        serial = dev.get_info(rs.camera_info.serial_number)
        name = dev.get_info(rs.camera_info.name)
        devices.append({"serial": serial, "name": name})
    return devices


def get_stream_profiles_for_camera_count(camera_count):
    if REQUESTED_STREAM_PROFILE != "auto":
        profiles = [p for p in STREAM_PROFILES if p["name"] == REQUESTED_STREAM_PROFILE]
        if not profiles:
            valid_names = ", ".join(["auto"] + [p["name"] for p in STREAM_PROFILES])
            raise RuntimeError(f"Invalid REALSENSE_STREAM_PROFILE={REQUESTED_STREAM_PROFILE}. Use: {valid_names}")
        return profiles

    if camera_count > 1:
        return sorted(STREAM_PROFILES, key=lambda p: p["name"] != "safe")

    return STREAM_PROFILES


def start_pipeline_with_fallback(pipeline, serial, label, profiles, allow_reset=False):
    last_error = None
    max_retries = 3

    for stream_profile in profiles:
        config = make_config(stream_profile, serial)
        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"⏳ [硬體初始化] {label} 嘗試 {stream_profile['name']} profile "
                    f"(第 {attempt}/{max_retries} 次)..."
                )
                active_profile = pipeline.start(config)
                print(f"🟢 {label} 硬體握手成功！使用 {stream_profile['name']} profile。")
                return active_profile, stream_profile
            except RuntimeError as e:
                last_error = e
                print(f"⚠️ {label} 啟動失敗: {e}")
                if allow_reset and attempt == 1:
                    reset_realsense_devices()
                else:
                    time.sleep(1.0)
        print(f"⚠️ {label} {stream_profile['name']} profile 失敗，嘗試下一個設定...")
    raise RuntimeError(f"{label} RealSense 啟動失敗：所有解析度設定都無法開始串流。") from last_error


def start_cameras():
    devices = get_connected_devices()
    if len(devices) == 0:
        raise RuntimeError("找不到 RealSense 裝置。")

    selected_devices = devices[:CAMERA_COUNT]
    print(f"📷 偵測到 {len(devices)} 台 RealSense，準備啟動 {len(selected_devices)} 台。")
    profiles = get_stream_profiles_for_camera_count(len(selected_devices))
    profile_names = ", ".join(profile["name"] for profile in profiles)
    print(f"🎚️ 串流 profile 嘗試順序: {profile_names}")

    runtimes = []
    for i, dev in enumerate(selected_devices, start=1):
        pipeline = rs.pipeline()
        label = f"Camera {i} ({dev['serial']})"
        try:
            profile, selected_stream_profile = start_pipeline_with_fallback(
                pipeline,
                dev["serial"],
                label,
                profiles,
                allow_reset=len(runtimes) == 0,
            )
            runtimes.append(
                CameraRuntime(
                    index=i,
                    serial=dev["serial"],
                    name=dev["name"],
                    pipeline=pipeline,
                    profile=profile,
                    stream_profile=selected_stream_profile,
                    align=rs.align(rs.stream.color),
                    colorizer=rs.colorizer(),
                )
            )
        except Exception:
            try:
                pipeline.stop()
            except Exception:
                pass
            raise

    return runtimes


def update_intrinsics(camera):
    if camera.intrinsics is not None:
        return
    try:
        active_profile = camera.pipeline.get_active_profile()
        color_stream = active_profile.get_stream(rs.stream.color)
        camera.intrinsics = color_stream.as_video_stream_profile().get_intrinsics()
        print(f"📐 [系統通知] Camera {camera.index} 已抓取相機內參:")
        print(f"   FX={camera.intrinsics.fx:.2f}")
        print(f"   FY={camera.intrinsics.fy:.2f}")
        print(f"   CX={camera.intrinsics.ppx:.2f}")
        print(f"   CY={camera.intrinsics.ppy:.2f}")
    except Exception:
        pass


def read_camera_frame(camera, timeout_ms=5000):
    frames = camera.pipeline.wait_for_frames(timeout_ms=timeout_ms)
    update_intrinsics(camera)
    aligned_frames = camera.align.process(frames)
    depth_frame = aligned_frames.get_depth_frame()
    color_frame = aligned_frames.get_color_frame()
    if not depth_frame or not color_frame:
        return None

    color_img_raw = np.asanyarray(color_frame.get_data())
    depth_img_raw = np.asanyarray(depth_frame.get_data())
    depth_colormap_raw = np.asanyarray(camera.colorizer.colorize(depth_frame).get_data())

    img_h, img_w = depth_img_raw.shape[:2]
    center_x = img_w // 2
    center_y = img_h // 2
    center_depth_mm = depth_img_raw[center_y, center_x]
    center_depth_meters = center_depth_mm / 1000.0

    if camera.intrinsics is not None and center_depth_meters > 0:
        point = rs.rs2_deproject_pixel_to_point(
            camera.intrinsics,
            [center_x, center_y],
            center_depth_meters,
        )
        coord_text = f"Cam {camera.index} Center 3D: X={point[0]:.3f}m, Y={point[1]:.3f}m, Z={point[2]:.3f}m"
    elif camera.intrinsics is None:
        coord_text = f"Cam {camera.index} Center 3D: Waiting for intrinsics"
    else:
        coord_text = f"Cam {camera.index} Center 3D: Out of range"

    return {
        "color": color_img_raw,
        "depth_raw": depth_img_raw,
        "depth_vis": depth_colormap_raw,
        "center": (center_x, center_y),
        "coord_text": coord_text,
    }


def build_camera_preview(camera, frame_data):
    center_x, center_y = frame_data["center"]
    color_img_marked = frame_data["color"].copy()
    depth_colormap_marked = frame_data["depth_vis"].copy()
    cv2.drawMarker(color_img_marked, (center_x, center_y), (0, 255, 0), cv2.MARKER_CROSS, 25, 2)
    cv2.drawMarker(depth_colormap_marked, (center_x, center_y), (0, 255, 0), cv2.MARKER_CROSS, 25, 2)

    preview_color = cv2.resize(color_img_marked, (640, 360))
    preview_depth = cv2.resize(depth_colormap_marked, (640, 360))
    row = np.hstack((preview_color, preview_depth))

    cv2.rectangle(row, (10, 8), (360, 42), (0, 0, 0), -1)
    cv2.putText(
        row,
        f"Camera {camera.index}: {camera.serial}",
        (20, 31),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.rectangle(row, (10, 325), (620, 355), (0, 0, 0), -1)
    cv2.putText(
        row,
        frame_data["coord_text"],
        (20, 345),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (160, 255, 43),
        1,
        cv2.LINE_AA,
    )
    return row


def build_preview_window(camera_frames):
    rows = [build_camera_preview(camera, frame_data) for camera, frame_data in camera_frames]
    return np.vstack(rows) if len(rows) > 1 else rows[0]


def save_snapshots(camera_frames):
    ts_str = get_timestamp_str()
    for camera, frame_data in camera_frames:
        suffix = f"{ts_str}_{camera.index}"
        cv2.imwrite(str(COLOR_DIR / f"snapshot_{suffix}_color.png"), frame_data["color"])
        cv2.imwrite(str(DEPTH_VIS_DIR / f"snapshot_{suffix}_depth_vis.png"), frame_data["depth_vis"])
        np.save(str(DEPTH_RAW_DIR / f"snapshot_{suffix}_depth_raw.npy"), frame_data["depth_raw"])
    print(f"💾 [Remote/Local 拍照成功] timestamp={ts_str}, cameras={len(camera_frames)}")


def start_recording(cameras):
    global is_recording
    current_ts_str = get_timestamp_str()
    for camera in cameras:
        bag_filename = f"video_{current_ts_str}_{camera.index}.bag"
        camera.current_bag_path = BAG_DIR / bag_filename
        dev = camera.profile.get_device()
        camera.recorder = rs.recorder(str(camera.current_bag_path), dev)
    is_recording = True
    print(f"🔴 [Remote/Local 開始錄製影像數據包]: timestamp={current_ts_str}, cameras={len(cameras)}")


def stop_recording(cameras):
    global is_recording
    saved_paths = []
    for camera in cameras:
        if camera.current_bag_path is not None:
            saved_paths.append(camera.current_bag_path)
        camera.recorder = None
    is_recording = False
    print("⏹️ [Remote/Local 停止錄製] 原始 .bag 已保存:")
    for path in saved_paths:
        print(f"   {path}")
    print("   需要 MP4 時再執行: python tools/convert_bag_to_mp4.py <bag_path>")

def get_timestamp_str():
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d_%H%M%S_%f")[:-3]

def socket_server_worker():
    global running, remote_cmd_queue
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('0.0.0.0', 8888))  
        server.listen(5)
        server.settimeout(1.0)
        print("🌐 [Socket 伺服器] 已成功啟動，正在監聽 Port 8888...")
    except Exception as e:
        print(f"❌ [Socket 伺服器] 啟動失敗: {e}")
        return

    while running:
        try:
            conn, addr = server.accept()
            print(f"\n📱 [App 已連線] 來自行動裝置: {addr}")
            while running:
                data = conn.recv(1024)
                if not data: break
                cmd = data.decode('utf-8').strip().lower()
                if cmd in ['s', 'r', 'q']:
                    remote_cmd_queue.append(cmd)  
                    conn.sendall(f"ACK: {cmd}\n".encode('utf-8'))
            conn.close()
            print("📱 [App 已斷開連線]")
        except socket.timeout: continue
        except Exception as e: break
    server.close()

remote_cmd_queue = []

try:
    pipeline_runtimes = start_cameras()

    print("⏳ 正在釋放硬體預熱緩衝區...")
    for camera in pipeline_runtimes:
        for _ in range(15):
            try:
                camera.pipeline.wait_for_frames(timeout_ms=200)
            except Exception:
                pass

    socket_thread = threading.Thread(target=socket_server_worker)
    socket_thread.daemon = True
    socket_thread.start()

    print("🟢 數據採集核心已就緒！")
    print("==================================================================")
    print("【遠端控制已解鎖】可以使用 Flutter App 連線至此 Mac 的 IP:8888")
    print(f"【多機模式】已啟動 {len(pipeline_runtimes)} 台相機；拍照檔名會以 _1, _2 區分來源")
    if GUI_ENABLED:
        print("【實體鍵盤依舊可用】S=拍照, R=錄影, Q=退出")
    else:
        print("【Headless 模式】請使用 TCP 指令 S=拍照, R=錄影, Q=退出")
    print("==================================================================")

    while running:
        camera_frames = []
        try:
            for camera in pipeline_runtimes:
                frame_data = read_camera_frame(camera)
                if frame_data is not None:
                    camera_frames.append((camera, frame_data))
        except RuntimeError:
            continue

        if len(camera_frames) != len(pipeline_runtimes):
            continue

        preview_window = build_preview_window(camera_frames)

        if is_recording:
            cv2.circle(preview_window, (30, 30), 10, (0, 0, 255), -1)
            cv2.putText(preview_window, "REC", (50, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        key = -1
        if GUI_ENABLED:
            cv2.imshow('RealSense M1 Collector', preview_window)
            key = cv2.waitKey(1) & 0xFF

        active_cmd = None
        if key == ord('s'): active_cmd = 's'
        elif key == ord('r'): active_cmd = 'r'
        elif key == ord('q'): active_cmd = 'q'
        elif len(remote_cmd_queue) > 0: active_cmd = remote_cmd_queue.pop(0)

        if active_cmd == 's':
            save_snapshots(camera_frames)
            
        elif active_cmd == 'r':
            if not is_recording:
                start_recording(pipeline_runtimes)
            else:
                stop_recording(pipeline_runtimes)
                
        elif active_cmd == 'q':
            running = False
            break
finally:
    running = False
    for camera in pipeline_runtimes:
        camera.recorder = None
        try:
            camera.pipeline.stop()
        except Exception:
            pass
    if GUI_ENABLED:
        cv2.destroyAllWindows()
    print("👋 系統已安全關閉。")
