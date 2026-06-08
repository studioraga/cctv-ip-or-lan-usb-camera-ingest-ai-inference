#!/usr/bin/env bash
set -euo pipefail

NODE1_IP="192.168.29.20"

taskset -c 0-3 gst-launch-1.0 -e \
  v4l2src device=/dev/video0 io-mode=2 ! \
  image/jpeg,width=1280,height=720,framerate=30/1 ! \
  jpegdec ! \
  videoconvert ! \
  video/x-raw,format=NV12 ! \
  nvvidconv ! \
  'video/x-raw(memory:NVMM),format=NV12' ! \
  nvv4l2h264enc maxperf-enable=1 insert-sps-pps=1 iframeinterval=30 bitrate=4000000 ! \
  h264parse ! \
  rtph264pay config-interval=1 pt=96 ! \
  udpsink host=$NODE1_IP port=5000 sync=false async=false
