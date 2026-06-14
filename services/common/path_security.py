"""Secure media path resolution.

The API never accepts a filesystem path. It accepts an opaque database identifier,
fetches the stored path, and then verifies that the canonical target is a regular
file beneath an explicitly configured media root.
"""
from __future__ import annotations

from pathlib import Path


class UnsafeMediaPath(ValueError):
    pass


def resolve_media_path(stored_path: str, allowed_root: str | Path) -> Path:
    if not stored_path or "\x00" in stored_path:
        raise UnsafeMediaPath("empty or invalid stored media path")

    root = Path(allowed_root).expanduser().resolve(strict=True)
    candidate = Path(stored_path).expanduser()
    if not candidate.is_absolute():
        # Repository-relative database paths are resolved from the current working dir.
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=True)

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafeMediaPath("media path escapes the configured root") from exc

    if not candidate.is_file():
        raise UnsafeMediaPath("media target is not a regular file")
    return candidate
