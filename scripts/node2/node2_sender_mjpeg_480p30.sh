#!/usr/bin/env bash
set -euo pipefail

NODE1_IP="192.168.29.20"
PORT=5000

echo "[INFO] Sending C922 MJPEG 640x480@30 to ${NODE1_IP}:${PORT}"

taskset -c 0-3 gst-launch-1.0 -v -e \
  v4l2src device=/dev/video0 io-mode=2 do-timestamp=true ! \
  image/jpeg,width=640,height=480,framerate=30/1 ! \
  rtpjpegpay pt=26 ! \
  udpsink host=${NODE1_IP} port=${PORT} sync=false async=false
