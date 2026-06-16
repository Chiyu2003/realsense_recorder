import cv2
import numpy as np
import pyrealsense2 as rs
import datetime
import os
import signal
import time
import threading
import socket
from pathlib import Path

# 全域生命週期變數
running = True  
is_recording = False
pipeline_started = False
intrinsics = None  

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
LOG_3D_DIR = SNAPSHOT_ROOT / "log_3d"

for d in [BAG_DIR, MP4_DIR, COLOR_DIR, DEPTH_VIS_DIR, DEPTH_RAW_DIR, LOG_3D_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def handle_shutdown_signal(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# 2. 官方黃金硬體配置
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)

colorizer = rs.colorizer()
CENTER_X = 640
CENTER_Y = 360

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
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"⏳ [硬體初始化] 正在嘗試喚醒 RealSense D435 相機 (第 {attempt}/{max_retries} 次)...")
            profile = pipeline.start(config)
            pipeline_started = True
            print("🟢 硬體握手成功！供電狀態正常。")
            break
        except RuntimeError as e:
            if attempt == max_retries:
                raise RuntimeError(f"已連續重試 {max_retries} 次皆失敗，M1 底層 USB 供電已鎖死。") from e
            print("⚠️ 供電超時或拒絕，正在進行底層通訊重置，1 秒後自動重試...")
            time.sleep(1.0)

    align = rs.align(rs.stream.color)

    print("⏳ 正在釋放硬體預熱緩衝區...")
    for _ in range(15):
        try: pipeline.wait_for_frames(timeout_ms=200)
        except: pass

    socket_thread = threading.Thread(target=socket_server_worker)
    socket_thread.daemon = True
    socket_thread.start()

    print("🟢 數據採集核心已就緒！")
    print("==================================================================")
    print("【遠端控制已解鎖】可以使用 Flutter App 連線至此 Mac 的 IP:8888")
    if GUI_ENABLED:
        print("【實體鍵盤依舊可用】S=拍照, R=錄影, Q=退出")
    else:
        print("【Headless 模式】請使用 TCP 指令 S=拍照, R=錄影, Q=退出")
    print("==================================================================")

    while running:
        try: frames = pipeline.wait_for_frames(timeout_ms=5000)
        except RuntimeError: continue

        if intrinsics is None:
            try:
                active_profile = pipeline.get_active_profile()
                color_stream = active_profile.get_stream(rs.stream.color)
                intrinsics = color_stream.as_video_stream_profile().get_intrinsics()
                print("📐 [系統通知] 已抓取相機內參:")
                print(f"   FX={intrinsics.fx:.2f}")
                print(f"   FY={intrinsics.fy:.2f}")
                print(f"   CX={intrinsics.ppx:.2f}")
                print(f"   CY={intrinsics.ppy:.2f}")
            except: pass 

        aligned_frames = align.process(frames)
        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        if not depth_frame or not color_frame: continue
            
        color_img_raw = np.asanyarray(color_frame.get_data())
        depth_img_raw = np.asanyarray(depth_frame.get_data())
        depth_colormap_raw = np.asanyarray(colorizer.colorize(depth_frame).get_data())

        center_depth_mm = depth_img_raw[CENTER_Y, CENTER_X]
        center_depth_meters = center_depth_mm / 1000.0

        x_m, y_m, z_m = 0.0, 0.0, 0.0
        if intrinsics is not None and center_depth_meters > 0:
            point = rs.rs2_deproject_pixel_to_point(intrinsics, [CENTER_X, CENTER_Y], center_depth_meters)
            coord_text = f"Center 3D: X={point[0]:.3f}m, Y={point[1]:.3f}m, Z={point[2]:.3f}m"
            x_m, y_m, z_m = point[0], point[1], point[2]
        elif intrinsics is None:
            coord_text = "Center 3D: Waiting for intrinsics"
        else:
            coord_text = "Center 3D: Out of range"

        color_img_marked = color_img_raw.copy()
        depth_colormap_marked = depth_colormap_raw.copy()
        cv2.drawMarker(color_img_marked, (CENTER_X, CENTER_Y), (0, 255, 0), cv2.MARKER_CROSS, 25, 2)
        cv2.drawMarker(depth_colormap_marked, (CENTER_X, CENTER_Y), (0, 255, 0), cv2.MARKER_CROSS, 25, 2)
        
        preview_color = cv2.resize(color_img_marked, (640, 360))
        preview_depth = cv2.resize(depth_colormap_marked, (640, 360))
        preview_window = np.hstack((preview_color, preview_depth))

        cv2.rectangle(preview_window, (10, 325), (500, 355), (0, 0, 0), -1)
        cv2.putText(preview_window, coord_text, (20, 345), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 255, 43), 1, cv2.LINE_AA)

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
            ts_str = get_timestamp_str()
            cv2.imwrite(str(COLOR_DIR / f"snapshot_{ts_str}_color_clean.png"), color_img_raw)
            cv2.imwrite(str(DEPTH_VIS_DIR / f"snapshot_{ts_str}_depth_vis_clean.png"), depth_colormap_raw)
            cv2.imwrite(str(COLOR_DIR / f"snapshot_{ts_str}_color_marked.png"), color_img_marked)
            cv2.imwrite(str(DEPTH_VIS_DIR / f"snapshot_{ts_str}_depth_vis_marked.png"), depth_colormap_marked)
            np.save(str(DEPTH_RAW_DIR / f"snapshot_{ts_str}_depth_raw.npy"), depth_img_raw)
            with open(LOG_3D_DIR / f"snapshot_{ts_str}_3d_log.txt", "w") as f_log:
                f_log.write(f"Timestamp: {ts_str}\nRaw Depth: {center_depth_mm} mm\n")
                if intrinsics is not None and center_depth_meters > 0:
                    f_log.write(f"X = {x_m:.6f}\nY = {y_m:.6f}\nZ = {z_m:.6f}\n")
                else:
                    f_log.write("3D Coordinate: Pending/Invalid\n")
            print(f"💾 [Remote/Local 拍照成功] 標記: {ts_str}")
            
        elif active_cmd == 'r':
            if not is_recording:
                current_ts_str = get_timestamp_str()
                bag_filename = f"video_{current_ts_str}.bag"
                current_bag_path = BAG_DIR / bag_filename
                dev = profile.get_device()
                recorder = rs.recorder(str(current_bag_path), dev)
                is_recording = True
                print(f"🔴 [Remote/Local 開始錄製影像數據包]: {bag_filename}")
            else:
                recorder = None 
                is_recording = False
                print(f"⏹️ [Remote/Local 停止錄製] 原始 .bag 已保存: {current_bag_path}")
                print(f"   需要 MP4 時再執行: python tools/convert_bag_to_mp4.py {current_bag_path}")
                
        elif active_cmd == 'q':
            running = False
            break
finally:
    running = False
    if pipeline_started:
        try: pipeline.stop()
        except: pass
    if GUI_ENABLED:
        cv2.destroyAllWindows()
    print("👋 系統已安全關閉。")
