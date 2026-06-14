#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.common.policy import SecurityPolicy


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fail-closed camera policy")
    parser.add_argument("--policy", default="policies/security_policy.yaml")
    args = parser.parse_args()
    policy = SecurityPolicy(args.policy)
    print(f"[OK] policy={args.policy} version={policy.data['version']}")
    for camera_id in sorted(policy._cameras):  # validation/reporting utility
        camera = policy.camera(camera_id)
        print(
            f"[CAMERA] id={camera.camera_id} node2={camera.node2_url} "
            f"profiles={','.join(camera.allowed_profiles)} devices={','.join(camera.allowed_devices)}"
        )
    for media_type in ("clip", "keyframe"):
        print(f"[MEDIA] {media_type}_root={policy.media_root(media_type)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
