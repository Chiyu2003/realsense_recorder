import cv2
import numpy as np
import pyrealsense2 as rs
import datetime
import os
import time
import threading
import socket
import struct
from pathlib import Path

# --- 1. 目錄配置 (完全遵循原版) ---
OUTPUT_ROOT = Path("output")
BAG_DIR = OUTPUT_ROOT / "bag"
MP4_DIR = OUTPUT_ROOT / "mp4"
SNAPSHOT_ROOT = OUTPUT_ROOT / "snapshot"
COLOR_DIR = SNAPSHOT_ROOT / "color"
DEPTH_VIS_DIR = SNAPSHOT_ROOT / "depth_vis"
DEPTH_RAW_DIR = SNAPSHOT_ROOT / "depth_raw"

for d in [BAG_DIR, MP4_DIR, COLOR_DIR, DEPTH_VIS_DIR, DEPTH_RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 變數
running = True
is_recording = False
latest_preview_frame = None
remote_cmd_queue = []
current_conn = None
intrinsics = None
current_bag_path = None

STREAM_PROFILES = [
    {"name": "high", "depth": (640, 480, 30), "color": (1280, 720, 15)},
    {"name": "safe", "depth": (640, 480, 30), "color": (640, 480, 30)},
]
REQUESTED_STREAM_PROFILE = os.environ.get("REALSENSE_STREAM_PROFILE", "auto").lower()


def make_config(profile):
    config = rs.config()
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
        print("🔄 正在送出 RealSense hardware reset...")
        for dev in devices:
            dev.hardware_reset()
        time.sleep(5.0)
        return True
    except Exception as e:
        print(f"⚠️ 無法 reset RealSense: {e}")
        return False


def start_pipeline_with_fallback(pipeline):
    last_error = None
    max_retries = 3
    profiles = STREAM_PROFILES
    if REQUESTED_STREAM_PROFILE != "auto":
        profiles = [p for p in STREAM_PROFILES if p["name"] == REQUESTED_STREAM_PROFILE]
        if not profiles:
            valid_names = ", ".join(["auto"] + [p["name"] for p in STREAM_PROFILES])
            raise RuntimeError(f"Invalid REALSENSE_STREAM_PROFILE={REQUESTED_STREAM_PROFILE}. Use: {valid_names}")

    for stream_profile in profiles:
        config = make_config(stream_profile)
        for attempt in range(1, max_retries + 1):
            try:
                print(f"⏳ 嘗試 {stream_profile['name']} profile (第 {attempt}/{max_retries} 次)...")
                active_profile = pipeline.start(config)
                print(f"🟢 啟動成功！使用 {stream_profile['name']} profile。")
                return active_profile, stream_profile
            except RuntimeError as e:
                last_error = e
                print(f"⚠️ 啟動失敗: {e}")
                if attempt == 1:
                    reset_realsense_devices()
                else:
                    time.sleep(1.0)
        print(f"⚠️ {stream_profile['name']} profile 失敗，嘗試下一個設定...")
    raise RuntimeError("RealSense 啟動失敗：所有解析度設定都無法開始串流。") from last_error

def get_timestamp_str():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# --- 2. Socket 服務 ---
def send_packet(conn, p_type, data):
    try:
        header = struct.pack("<BL", p_type, len(data))
        conn.sendall(header + data)
        return True
    except: return False

def socket_server_worker():
    global running, latest_preview_frame, remote_cmd_queue, current_conn
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('0.0.0.0', 8888))
        server.listen(5)
    except: return

    while running:
        try:
            conn, addr = server.accept()
            current_conn = conn
            conn.settimeout(0.1)
            while running:
                try:
                    data = conn.recv(1024)
                    if data:
                        cmd = data.decode('utf-8').strip().lower()
                        if cmd in ['s', 'r', 'q']: remote_cmd_queue.append(cmd)
                except: pass
                if latest_preview_frame is not None:
                    _, img_encoded = cv2.imencode('.jpg', latest_preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 40])
                    if not send_packet(conn, 1, img_encoded.tobytes()): break
                time.sleep(0.05)
            conn.close()
            current_conn = None
        except: continue
    server.close()

# --- 3. 主程式 ---
def start():
    global running, latest_preview_frame, is_recording, current_conn, intrinsics
    global current_bag_path
    recorder = None
    
    pipeline = rs.pipeline()

    try:
        profile, selected_stream_profile = start_pipeline_with_fallback(pipeline)
        align = rs.align(rs.stream.color)
        colorizer = rs.colorizer()
        intrinsics = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()

        threading.Thread(target=socket_server_worker, daemon=True).start()
        print("🟢 啟動成功！")

        while running:
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)
            depth_f = aligned_frames.get_depth_frame()
            color_f = aligned_frames.get_color_frame()
            if not depth_f or not color_f: continue

            color_img = np.asanyarray(color_f.get_data())
            depth_img_raw = np.asanyarray(depth_f.get_data())
            depth_colormap = np.asanyarray(colorizer.colorize(depth_f).get_data())

            # 3D 資訊
            img_h, img_w = depth_img_raw.shape[:2]
            center_x = img_w // 2
            center_y = img_h // 2
            depth_mm = depth_img_raw[center_y, center_x]
            depth_m = depth_mm / 1000.0
            coord_text = f"X:0.0 Y:0.0 Z:{depth_m:.2f}m"
            if depth_m > 0:
                p = rs.rs2_deproject_pixel_to_point(intrinsics, [center_x, center_y], depth_m)
                coord_text = f"X:{p[0]:.2f}m Y:{p[1]:.2f}m Z:{p[2]:.2f}m"

            # 手機畫面
            m_c = cv2.resize(color_img.copy(), (320, 240))
            m_d = cv2.resize(depth_colormap.copy(), (320, 240))
            cv2.drawMarker(m_c, (160, 120), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
            cv2.putText(m_c, coord_text, (10, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            if is_recording: cv2.circle(m_c, (300, 20), 8, (0, 0, 255), -1)
            latest_preview_frame = np.vstack((m_c, m_d))

            # 本地視窗
            cv2.imshow("Server", np.hstack((cv2.resize(color_img, (640, 360)), cv2.resize(depth_colormap, (640, 360)))))
            if cv2.waitKey(1) & 0xFF == ord('q'): break

            # 處理指令
            if remote_cmd_queue:
                cmd = remote_cmd_queue.pop(0)
                ts = get_timestamp_str()
                if cmd == 's':
                    f_name = f"snapshot_{ts}_color.png"
                    cv2.imwrite(str(COLOR_DIR / f_name), color_img)
                    if current_conn: send_packet(current_conn, 2, f"Saved: {f_name}".encode())
                
                elif cmd == 'r':
                    if not is_recording:
                        ts = get_timestamp_str()
                        current_bag_path = (BAG_DIR / f"video_{ts}.bag").resolve()
                        recorder = rs.recorder(str(current_bag_path), profile.get_device())
                        is_recording = True
                        if current_conn: send_packet(current_conn, 2, b"REC Started")
                    else:
                        recorder = None 
                        is_recording = False
                        if current_conn:
                            send_packet(current_conn, 2, f"REC Stopped: {current_bag_path}".encode())
                        print(f"⏹️ 錄影停止，原始 .bag 已保存: {current_bag_path}")
                        print(f"   需要 MP4 時再執行: python tools/convert_bag_to_mp4.py {current_bag_path}")

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
        print("👋 系統關閉")

if __name__ == "__main__":
    start()
