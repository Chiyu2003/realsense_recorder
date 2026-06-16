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
active_convert_threads = []  
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

def bg_convert_worker(bag_path, mp4_main_path):
    """ 🚀 核心重構：獨立背景執行緒，一口氣將 .bag 拆分並輸出三組獨立影片 """
    try:
        bg_pipeline = rs.pipeline()
        bg_config = rs.config()
        bg_config.enable_device_from_file(str(bag_path), repeat_playback=False)
        profile = bg_pipeline.start(bg_config)
        playback = profile.get_device().as_playback()
        playback.set_real_time(False) # 關閉即時，全速解包
        
        bg_align = rs.align(rs.stream.color)
        bg_colorizer = rs.colorizer()
        
        # 定義三路影片的輸出路徑
        p = Path(mp4_main_path)
        mp4_color_path = p.parent / f"{p.stem}_pure_color.mp4"
        mp4_depth_path = p.parent / f"{p.stem}_pure_depth.mp4"
        
        writer_main = None   # 左右拼接版
        writer_color = None  # 純彩色版
        writer_depth = None  # 純深度彩虹版
        
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        
        while True:
            try: 
                frames = bg_pipeline.wait_for_frames(timeout_ms=1000)
            except RuntimeError: 
                break # 讀取完畢
                
            aligned_frames = bg_align.process(frames)
            depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()
            if not depth_frame or not color_frame: continue
                
            color_img = np.asanyarray(color_frame.get_data())
            depth_colormap_raw = np.asanyarray(bg_colorizer.colorize(depth_frame).get_data())
            
            # A. 建立拼接視窗 (為了防止檔案過大，拼接版維持 640x360 縮放)
            preview_color = cv2.resize(color_img, (640, 360))
            preview_depth = cv2.resize(depth_colormap_raw, (640, 360))
            composite_main = np.hstack((preview_color, preview_depth))
            
            # 初始化三個寫入器 (純彩色與純深度影片採用 1280x720 高清無損尺寸)
            if writer_main is None:
                h_main, w_main = composite_main.shape[:2]
                h_raw, w_raw = color_img.shape[:2]
                
                writer_main = cv2.VideoWriter(str(mp4_main_path), fourcc, 30, (w_main, h_main))
                writer_color = cv2.VideoWriter(str(mp4_color_path), fourcc, 30, (w_raw, h_raw))
                writer_depth = cv2.VideoWriter(str(mp4_depth_path), fourcc, 30, (w_raw, h_raw))
            
            # 三路同時灌入數據落盤
            writer_main.write(composite_main)
            writer_color.write(color_img)
            writer_depth.write(depth_colormap_raw)
            
        # 安全關閉所有寫入器
        if writer_main is not None: writer_main.release()
        if writer_color is not None: writer_color.release()
        if writer_depth is not None: writer_depth.release()
        bg_pipeline.stop()
        print("\n🎉 [背景自動拆分成功] 三組影片已安全生成：")
        print(f"   1. 拼接預覽：{p.name}")
        print(f"   2. 純淨彩色：{mp4_color_path.name}")
        print(f"   3. 純淨深度：{mp4_depth_path.name}")
    except Exception as e:
        print(f"\n❌ [背景多路轉檔失敗] 發生錯誤: {e}")

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
                dev = profile.get_device()
                recorder = None 
                
                # 背景轉檔的主路徑
                mp4_filename = f"video_{current_ts_str}.mp4"
                mp4_path = MP4_DIR / mp4_filename
                
                # 🚀 交給改裝後的背景 worker，一次噴出 3 組影片
                convert_thread = threading.Thread(target=bg_convert_worker, args=(current_bag_path, mp4_path))
                convert_thread.daemon = True
                convert_thread.start()
                active_convert_threads.append(convert_thread) 
                
                is_recording = False
                print("⏹️ [Remote/Local 停止錄製] 原始數據已保存。背景【三路獨立影片】自動解包拆分中...")
                
        elif active_cmd == 'q':
            running = False
            break
finally:
    running = False
    try:
        active_convert_threads = [t for t in active_convert_threads if t.is_alive()]
        if len(active_convert_threads) > 0:
            print(f"\n⏳ [安全機制] 正在等待最後 {len(active_convert_threads)} 個三路拆分轉檔執行緒安全寫入...")
            for t in active_convert_threads: t.join() 
    except: pass
    if pipeline_started:
        try: pipeline.stop()
        except: pass
    if GUI_ENABLED:
        cv2.destroyAllWindows()
    print("👋 系統已安全關閉。")
