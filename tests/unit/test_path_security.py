from pathlib import Path

import pytest

from services.common.path_security import UnsafeMediaPath, resolve_media_path


def test_resolves_regular_file_under_root(tmp_path: Path, monkeypatch):
    root = tmp_path / "data" / "clips"
    root.mkdir(parents=True)
    clip = root / "cam1" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)
    assert resolve_media_path("data/clips/cam1/clip.mp4", root) == clip.resolve()


def test_rejects_path_escape(tmp_path: Path):
    root = tmp_path / "clips"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    with pytest.raises(UnsafeMediaPath):
        resolve_media_path(str(secret), root)


def test_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "clips"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    link = root / "link.mp4"
    link.symlink_to(secret)
    with pytest.raises(UnsafeMediaPath):
        resolve_media_path(str(link), root)


def test_missing_file_is_rejected(tmp_path: Path):
    root = tmp_path / "clips"
    root.mkdir()
    with pytest.raises((UnsafeMediaPath, FileNotFoundError)):
        resolve_media_path(str(root / "missing.mp4"), root)
