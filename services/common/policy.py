from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import yaml


class SecurityPolicy:
    def __init__(self, path: str = "policies/security_policy.yaml"):
        self.path = path
        self.data: Dict[str, Any] = {}
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}

    def allowed_profiles_for_camera(self, camera_id: str) -> List[str]:
        for item in self.data.get("allowed_camera_sources", []):
            if item.get("camera_id") == camera_id:
                return item.get("allowed_profiles", [])
        return []

    def is_profile_allowed(self, camera_id: str, profile: str) -> bool:
        profiles = self.allowed_profiles_for_camera(camera_id)
        return not profiles or profile in profiles

    def is_source_allowed(self, camera_id: str, source_ip: str) -> bool:
        for item in self.data.get("allowed_camera_sources", []):
            if item.get("camera_id") == camera_id:
                return item.get("source_ip") == source_ip
        return True
