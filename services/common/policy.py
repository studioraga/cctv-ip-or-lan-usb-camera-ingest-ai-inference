"""Fail-closed policy loader shared by Node1 and Node2."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


class PolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CameraPolicy:
    camera_id: str
    source_ip: str
    node2_url: str
    allowed_node1_ips: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    allowed_profiles: tuple[str, ...]
    allowed_devices: tuple[str, ...]


class SecurityPolicy:
    """Strict policy accessors.

    Missing file, malformed YAML, missing camera, or an empty allow-list denies the
    operation. This deliberately removes the original fail-open behavior.
    """

    def __init__(self, path: str = "policies/security_policy.yaml"):
        self.path = Path(path)
        self.data = self._load()
        self._cameras = self._parse_cameras()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise PolicyError(f"Policy file not found: {self.path}")
        try:
            loaded = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PolicyError(f"Invalid YAML policy: {exc}") from exc
        if not isinstance(loaded, dict):
            raise PolicyError("Policy root must be a mapping")
        if loaded.get("version") != 2:
            raise PolicyError("Unsupported or missing policy version; expected version: 2")
        return loaded

    @staticmethod
    def _valid_ip(value: str) -> str:
        try:
            return str(ipaddress.ip_address(value))
        except ValueError as exc:
            raise PolicyError(f"Invalid IP address in policy: {value}") from exc

    def _parse_cameras(self) -> dict[str, CameraPolicy]:
        raw = self.data.get("cameras")
        if not isinstance(raw, list) or not raw:
            raise PolicyError("Policy must define a non-empty cameras list")
        result: dict[str, CameraPolicy] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise PolicyError("Each camera policy must be a mapping")
            camera_id = str(item.get("camera_id", "")).strip()
            if not camera_id or camera_id in result:
                raise PolicyError(f"Missing or duplicate camera_id: {camera_id!r}")
            node2_url = str(item.get("node2_url", "")).rstrip("/")
            parsed = urlparse(node2_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise PolicyError(f"Invalid node2_url for {camera_id}")
            source_ip = self._valid_ip(str(item.get("source_ip", "")))
            if parsed.hostname != source_ip:
                raise PolicyError(
                    f"node2_url host must equal source_ip for {camera_id}: "
                    f"{parsed.hostname} != {source_ip}"
                )
            node1_ips = tuple(self._valid_ip(str(v)) for v in item.get("allowed_node1_ips", []))
            ports = tuple(int(v) for v in item.get("allowed_ports", []))
            profiles = tuple(str(v) for v in item.get("allowed_profiles", []))
            devices = tuple(str(v) for v in item.get("allowed_devices", []))
            if not node1_ips or not ports or not profiles or not devices:
                raise PolicyError(f"Camera {camera_id} has an empty required allow-list")
            if any(port < 1 or port > 65535 for port in ports):
                raise PolicyError(f"Camera {camera_id} contains an invalid port")
            result[camera_id] = CameraPolicy(
                camera_id=camera_id,
                source_ip=source_ip,
                node2_url=node2_url,
                allowed_node1_ips=node1_ips,
                allowed_ports=ports,
                allowed_profiles=profiles,
                allowed_devices=devices,
            )
        return result

    def camera(self, camera_id: str) -> CameraPolicy:
        try:
            return self._cameras[camera_id]
        except KeyError as exc:
            raise PolicyError(f"Camera is not authorized: {camera_id}") from exc

    def is_profile_allowed(self, camera_id: str, profile: str) -> bool:
        try:
            return profile in self.camera(camera_id).allowed_profiles
        except PolicyError:
            return False

    def is_source_allowed(self, camera_id: str, source_ip: str) -> bool:
        try:
            return self._valid_ip(source_ip) == self.camera(camera_id).source_ip
        except (PolicyError, ValueError):
            return False

    def is_stream_target_allowed(self, camera_id: str, node1_ip: str, port: int) -> bool:
        try:
            camera = self.camera(camera_id)
            return self._valid_ip(node1_ip) in camera.allowed_node1_ips and int(port) in camera.allowed_ports
        except (PolicyError, ValueError):
            return False

    def is_device_allowed(self, camera_id: str, device: str) -> bool:
        try:
            return device in self.camera(camera_id).allowed_devices
        except PolicyError:
            return False

    def node2_url(self, camera_id: str) -> str:
        return self.camera(camera_id).node2_url

    def media_root(self, media_type: str) -> Path:
        media = self.data.get("media", {})
        key = {"clip": "clip_root", "keyframe": "keyframe_root"}.get(media_type)
        if key is None:
            raise PolicyError(f"Unknown media type: {media_type}")
        value = media.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PolicyError(f"Missing media root: {key}")
        return Path(value)

    def trusted_node1_control_ips(self) -> tuple[str, ...]:
        values = self.data.get("node2_control", {}).get("trusted_client_ips", [])
        return tuple(self._valid_ip(str(v)) for v in values)
