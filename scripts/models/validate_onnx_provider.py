#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.common.onnx_provider_validation import provider_report


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate ONNX Runtime provider availability")
    ap.add_argument("--provider", default="auto", help="auto, cpu, cuda, tensorrt, or exact ONNX Runtime provider name")
    ap.add_argument("--require", action="store_true", help="return non-zero when requested provider is unavailable")
    args = ap.parse_args()
    report = provider_report(args.provider)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] or not args.require else 1


if __name__ == "__main__":
    raise SystemExit(main())
