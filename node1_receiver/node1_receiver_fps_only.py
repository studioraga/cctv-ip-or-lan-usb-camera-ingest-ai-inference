import cv2
import time
import sys

pipeline = (
    'udpsrc port=5000 buffer-size=4194304 '
    'caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
    'queue leaky=downstream max-size-buffers=2 ! '
    'rtpjpegdepay ! '
    'jpegdec ! '
    'videoconvert ! '
    'video/x-raw,format=BGR ! '
    'appsink drop=true sync=false max-buffers=1'
)

print("[INFO] Opening pipeline:")
print(pipeline)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("[ERROR] Failed to open stream")
    sys.exit(1)

print("[INFO] Stream opened. Measuring FPS. Press Ctrl+C to stop.")

frames = 0
t0 = time.time()
last = t0

try:
    while True:
        ok, frame = cap.read()

        if not ok:
            print("[WARN] no frame")
            time.sleep(0.05)
            continue

        frames += 1
        now = time.time()

        if now - last >= 2.0:
            fps = frames / (now - t0)
            print(f"[INFO] FPS={fps:.2f}, frame={frame.shape}")
            last = now

except KeyboardInterrupt:
    print("\n[INFO] Stopped by user")

finally:
    cap.release()
