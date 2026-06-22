# Object detection models

This directory is intentionally source-controlled only through this README.
Large model files such as `*.onnx`, TensorRT `*.engine`, and `*.plan` are ignored by `.gitignore`.

Default Node1 Step 12 model:

```bash
./scripts/models/download_yolo_onnx.sh
```

The script downloads the default YOLO ONNX model to:

```text
models/object_detection/yolo11n.onnx
```

It also writes the repo-relative path into `deploy/ai-camera.env`:

```text
AI_CAMERA_YOLO_MODEL=models/object_detection/yolo11n.onnx
```
