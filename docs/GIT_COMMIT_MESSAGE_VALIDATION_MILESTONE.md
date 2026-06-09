# Suggested Git commit message

```text
Validate Node1/Node2 AI camera service-layer baseline

- Document validated Node1/Node2 LAN camera pipeline in README
- Add detailed VALIDATION.md with incremental bring-up, issues, fixes, and proof points
- Validate Logitech C922 USB/V4L2 camera streaming from Node2 Jetson to Node1 receiver
- Validate MJPEG RTP profiles for 480p30, 720p30, 720p60, and 1080p30
- Validate YUYV 640x480 raw RTP debug profile with YUY2-to-UYVY conversion
- Validate Node2 FastAPI control agent start/stop/switch-profile flow
- Validate Node1 FastAPI API gateway health, camera inventory, Node2 status, and control path
- Validate Prometheus metrics endpoints for Node1 receiver and Node2 control agent
- Validate SQLite event schema with cameras, clips, and events tables
- Validate motion-triggered event persistence with linked keyframes and MP4 clips
- Add threaded Node1 receiver capture loop to avoid OpenCV cap.read() hangs after stream stop
- Add startup/no-frame watchdog controls for robust headless receiver operation
- Add CI/CD validation plan and initial static/node-local validation scripts

Validated on local LAN:
- Node1 receiver/API gateway: 192.168.29.20
- Node2 Jetson C922 streamer/control agent: 192.168.29.188
```

Optional shorter subject:

```text
Validate local-first Node1/Node2 AI camera baseline
```
