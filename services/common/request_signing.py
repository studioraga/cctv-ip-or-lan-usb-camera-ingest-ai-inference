"""HMAC request signing helpers for local Node1/Node2 control traffic.

This is intentionally small and dependency-free.  It gives the lab a production-
shaped signed-call path before full mTLS is wired through a reverse proxy or
service mesh.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Mapping

HEADER_TIMESTAMP = "x-ai-camera-timestamp"
HEADER_NONCE = "x-ai-camera-nonce"
HEADER_BODY_SHA256 = "x-ai-camera-body-sha256"
HEADER_SIGNATURE = "x-ai-camera-signature"
SIGNATURE_VERSION = "v1"


@dataclass(frozen=True)
class SignatureResult:
    ok: bool
    reason: str = ""


def _body_digest(body: bytes | str | None) -> str:
    if body is None:
        data = b""
    elif isinstance(body, bytes):
        data = body
    else:
        data = body.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_payload(method: str, path: str, timestamp: str, nonce: str, body_sha256: str) -> bytes:
    return "\n".join([method.upper(), path, timestamp, nonce, body_sha256]).encode("utf-8")


def sign_components(secret: str, method: str, path: str, timestamp: str, nonce: str, body_sha256: str) -> str:
    if not secret:
        raise ValueError("signing secret is required")
    digest = hmac.new(secret.encode("utf-8"), canonical_payload(method, path, timestamp, nonce, body_sha256), hashlib.sha256).hexdigest()
    return f"{SIGNATURE_VERSION}:{digest}"


def signed_headers(secret: str, method: str, path: str, body: bytes | str | None = b"", *, timestamp: int | None = None, nonce: str | None = None) -> dict[str, str]:
    ts = str(int(time.time() if timestamp is None else timestamp))
    n = nonce or secrets.token_hex(16)
    body_sha = _body_digest(body)
    sig = sign_components(secret, method, path, ts, n, body_sha)
    return {
        "X-AI-Camera-Timestamp": ts,
        "X-AI-Camera-Nonce": n,
        "X-AI-Camera-Body-SHA256": body_sha,
        "X-AI-Camera-Signature": sig,
    }


def verify_signature(secret: str, method: str, path: str, headers: Mapping[str, str], body: bytes | str | None = b"", *, now: int | None = None, max_skew_sec: int = 300) -> SignatureResult:
    if not secret:
        return SignatureResult(False, "signing secret is not configured")
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    timestamp = lower.get(HEADER_TIMESTAMP, "")
    nonce = lower.get(HEADER_NONCE, "")
    supplied_body_sha = lower.get(HEADER_BODY_SHA256, "")
    supplied_sig = lower.get(HEADER_SIGNATURE, "")
    if not timestamp or not nonce or not supplied_body_sha or not supplied_sig:
        return SignatureResult(False, "missing signed request headers")
    try:
        ts_int = int(timestamp)
    except ValueError:
        return SignatureResult(False, "invalid timestamp")
    current = int(time.time() if now is None else now)
    if abs(current - ts_int) > int(max_skew_sec):
        return SignatureResult(False, "timestamp outside allowed skew")
    actual_body_sha = _body_digest(body)
    if not hmac.compare_digest(supplied_body_sha, actual_body_sha):
        return SignatureResult(False, "body digest mismatch")
    expected_sig = sign_components(secret, method, path, timestamp, nonce, supplied_body_sha)
    if not hmac.compare_digest(supplied_sig, expected_sig):
        return SignatureResult(False, "signature mismatch")
    return SignatureResult(True, "ok")
