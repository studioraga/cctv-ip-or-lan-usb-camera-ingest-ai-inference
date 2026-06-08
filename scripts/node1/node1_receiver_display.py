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

print("[INFO] OpenCV:", cv2.__version__)
print("[INFO] Opening pipeline:")
print(pipeline)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("[ERROR] Failed to open Node2 MJPEG RTP stream")
    sys.exit(1)

print("[INFO] Stream opened. Press ESC to exit, or Ctrl+C in terminal.")

frames = 0
t0 = time.time()

try:
    while True:
        ok, frame = cap.read()

        if not ok:
            print("[WARN] no frame")
            time.sleep(0.05)
            continue

        frames += 1

        if frames % 100 == 0:
            dt = time.time() - t0
            print(f"[INFO] Received FPS={frames / dt:.2f}, frame={frame.shape}")

        cv2.imshow("Node2 C922 stream on Node1", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            print("[INFO] ESC pressed. Exiting.")
            break

except KeyboardInterrupt:
    print("\n[INFO] Stopped by user")

finally:
    cap.release()
    cv2.destroyAllWindows()
