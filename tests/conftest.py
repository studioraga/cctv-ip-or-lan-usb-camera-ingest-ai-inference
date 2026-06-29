from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


import pytest


# Tests should be deterministic even when the developer shell has sourced
# deploy/ai-camera.env. Individual tests can still set these variables with
# their own monkeypatch fixture after this autouse fixture has cleared them.
_AI_CAMERA_ENV_VARS_TO_ISOLATE = (
    "AI_CAMERA_NODE1_API_TOKEN",
    "AI_CAMERA_NODE1_API_KEYS",
    "AI_CAMERA_NODE1_PUBLIC_ENDPOINTS",
    "AI_CAMERA_NODE1_ENFORCE_API_CLIENTS",
    "AI_CAMERA_API_CLIENTS",
    "AI_CAMERA_NODE_API_SIGNING_SECRET",
    "AI_CAMERA_NODE1_REQUIRE_SIGNED_NODE2",
    "AI_CAMERA_NODE2_REQUIRE_SIGNED_CONTROL",
    "AI_CAMERA_NODE2_TO_NODE1_API_KEY",
)


@pytest.fixture(autouse=True)
def isolate_ai_camera_env_for_tests(monkeypatch):
    for name in _AI_CAMERA_ENV_VARS_TO_ISOLATE:
        monkeypatch.delenv(name, raising=False)
