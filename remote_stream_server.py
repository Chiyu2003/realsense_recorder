import cv2
import numpy as np
import pyrealsense2 as rs
import datetime
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
LOG_3D_DIR = SNAPSHOT_ROOT / "log_3d"

for d in [BAG_DIR, MP4_DIR, COLOR_DIR, DEPTH_VIS_DIR, DEPTH_RAW_DIR, LOG_3D_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 變數
active_convert_threads = []
running = True
is_recording = False
latest_preview_frame = None
remote_cmd_queue = []
current_conn = None
intrinsics = None
current_bag_path = None
current_mp4_path = None

CENTER_X = 640
CENTER_Y = 360

def get_timestamp_str():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# --- 2. 背景轉檔邏輯 (移植自原版) ---
def bg_convert_worker(bag_path, mp4_main_path):
    try:
        bg_pipeline = rs.pipeline()
        bg_config = rs.config()
        bg_config.enable_device_from_file(str(bag_path), repeat_playback=False)
        profile = bg_pipeline.start(bg_config)
        playback = profile.get_device().as_playback()
        playback.set_real_time(False)
        
        bg_align = rs.align(rs.stream.color)
        bg_colorizer = rs.colorizer()
        
        p = Path(mp4_main_path)
        mp4_color_path = p.parent / f"{p.stem}_pure_color.mp4"
        mp4_depth_path = p.parent / f"{p.stem}_pure_depth.mp4"
        
        writer_main = None
        writer_color = None
        writer_depth = None
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        
        while True:
            try: frames = bg_pipeline.wait_for_frames(timeout_ms=1000)
            except: break
            aligned_frames = bg_align.process(frames)
            depth_f = aligned_frames.get_depth_frame()
            color_f = aligned_frames.get_color_frame()
            if not depth_f or not color_f: continue
            
            color_img = np.asanyarray(color_f.get_data())
            depth_color = np.asanyarray(bg_colorizer.colorize(depth_f).get_data())
            
            if writer_main is None:
                h, w = color_img.shape[:2]
                writer_main = cv2.VideoWriter(str(mp4_main_path), fourcc, 30, (w*2, h))
                writer_color = cv2.VideoWriter(str(mp4_color_path), fourcc, 30, (w, h))
                writer_depth = cv2.VideoWriter(str(mp4_depth_path), fourcc, 30, (w, h))
            
            writer_main.write(np.hstack((color_img, depth_color)))
            writer_color.write(color_img)
            writer_depth.write(depth_color)
            
        if writer_main: writer_main.release()
        if writer_color: writer_color.release()
        if writer_depth: writer_depth.release()
        bg_pipeline.stop()
        print(f"🎉 影片轉換成功: {p.name}")
    except Exception as e:
        print(f"❌ 轉檔失敗: {e}")

# --- 3. Socket 服務 ---
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

# --- 4. 主程式 ---
def start():
    global running, latest_preview_frame, is_recording, current_conn, intrinsics
    global current_bag_path, current_mp4_path
    recorder = None
    
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)

    try:
        profile = pipeline.start(config)
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
            depth_mm = depth_img_raw[CENTER_Y, CENTER_X]
            depth_m = depth_mm / 1000.0
            coord_text = f"X:0.0 Y:0.0 Z:{depth_m:.2f}m"
            if depth_m > 0:
                p = rs.rs2_deproject_pixel_to_point(intrinsics, [CENTER_X, CENTER_Y], depth_m)
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
                    with open(LOG_3D_DIR / f"snapshot_{ts}_3d.txt", "w") as f_log:
                        f_log.write(f"Coord: {coord_text}\nRaw Depth: {depth_mm}mm")
                    if current_conn: send_packet(current_conn, 2, f"Saved: {f_name}".encode())
                
                elif cmd == 'r':
                    if not is_recording:
                        ts = get_timestamp_str()
                        current_bag_path = (BAG_DIR / f"video_{ts}.bag").resolve()
                        current_mp4_path = (MP4_DIR / f"video_{ts}.mp4").resolve()
                        recorder = rs.recorder(str(current_bag_path), profile.get_device())
                        is_recording = True
                        if current_conn: send_packet(current_conn, 2, b"REC Started")
                    else:
                        recorder = None 
                        is_recording = False
                        
                        # 2. 延遲 1 秒，確保 Recorder 完全釋放檔案
                        def delayed_convert(b, m):
                            time.sleep(1.0)
                            bg_convert_worker(b, m)
                            
                        if current_bag_path and current_mp4_path:
                            t = threading.Thread(
                                target=delayed_convert,
                                args=(current_bag_path, current_mp4_path),
                                daemon=True,
                            )
                            t.start()
                            active_convert_threads.append(t)
                        if current_conn: send_packet(current_conn, 2, b"REC Stopped & Converting...")

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
        print("👋 系統關閉")

if __name__ == "__main__":
    start()
