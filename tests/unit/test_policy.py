from pathlib import Path

import pytest

from services.common.policy import PolicyError, SecurityPolicy


VALID = """
version: 2
cameras:
  - camera_id: cam1
    source_ip: 10.0.0.2
    node2_url: http://10.0.0.2:8082
    allowed_node1_ips: [10.0.0.1]
    allowed_ports: [5000]
    allowed_profiles: [mjpeg_720p30]
    allowed_devices: [/dev/video0]
media:
  clip_root: data/clips
  keyframe_root: data/keyframes
node2_control:
  trusted_client_ips: [10.0.0.1, 127.0.0.1]
"""


def write_policy(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_policy_allows_only_explicit_values(tmp_path: Path):
    policy = SecurityPolicy(str(write_policy(tmp_path, VALID)))
    assert policy.is_profile_allowed("cam1", "mjpeg_720p30")
    assert not policy.is_profile_allowed("cam1", "mjpeg_480p30")
    assert not policy.is_profile_allowed("unknown", "mjpeg_720p30")
    assert policy.is_stream_target_allowed("cam1", "10.0.0.1", 5000)
    assert not policy.is_stream_target_allowed("cam1", "10.0.0.99", 5000)
    assert policy.is_device_allowed("cam1", "/dev/video0")
    assert not policy.is_device_allowed("cam1", "/dev/video9")


def test_missing_policy_fails_closed(tmp_path: Path):
    with pytest.raises(PolicyError):
        SecurityPolicy(str(tmp_path / "missing.yaml"))


def test_empty_allow_list_is_rejected(tmp_path: Path):
    bad = VALID.replace("allowed_profiles: [mjpeg_720p30]", "allowed_profiles: []")
    with pytest.raises(PolicyError):
        SecurityPolicy(str(write_policy(tmp_path, bad)))


def test_node2_url_must_match_source_ip(tmp_path: Path):
    bad = VALID.replace("http://10.0.0.2:8082", "http://10.0.0.99:8082")
    with pytest.raises(PolicyError):
        SecurityPolicy(str(write_policy(tmp_path, bad)))
