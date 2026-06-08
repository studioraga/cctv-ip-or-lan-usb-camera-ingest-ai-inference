#!/usr/bin/env bash
set -euo pipefail

gst-launch-1.0 -e \
  udpsrc port=5000 caps="application/x-rtp,media=video,encoding-name=JPEG,payload=26" ! \
  rtpjpegdepay ! \
  jpegdec ! \
  videoconvert ! \
  autovideosink sync=false
