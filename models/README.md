# Models

Place local-only model artifacts here. Do not commit large model files to Git by default.

Suggested layout:

```text
models/
  object_detection/
    yolo*.onnx
  embeddings/
  face/
```

The first working validation path is receiver-side `--motion-events`, which does not require a model. Add a YOLO ONNX model later and wire model-specific preprocessing/postprocessing in `services/node1_inference_worker/detectors/yolo_onnx.py`.
