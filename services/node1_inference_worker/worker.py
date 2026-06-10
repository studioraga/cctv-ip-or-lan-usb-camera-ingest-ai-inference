#!/usr/bin/env python3
"""Node1 inference worker scaffold.

For the first integration pass, receiver-side `--motion-events` validates event DB,
keyframes, and clip capture. This worker is the extension point for dedicated
object detection models such as YOLO ONNX.
"""

import argparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--db-path", default="data/events/ai_camera.db")
    args = ap.parse_args()
    print(f"[INFO] inference worker scaffold running db={args.db_path} model={args.model}")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
