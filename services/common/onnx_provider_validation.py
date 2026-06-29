"""ONNX Runtime execution-provider selection and validation helpers."""
from __future__ import annotations

from dataclasses import dataclass


_PROVIDER_ALIASES = {
    "auto": (),
    "cpu": ("CPUExecutionProvider",),
    "cuda": ("CUDAExecutionProvider", "CPUExecutionProvider"),
    "tensorrt": ("TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"),
}


@dataclass(frozen=True)
class ProviderSelection:
    requested: str
    available: tuple[str, ...]
    providers: tuple[str, ...]
    ok: bool
    reason: str


def available_providers() -> tuple[str, ...]:
    try:
        import onnxruntime as ort  # type: ignore
        return tuple(ort.get_available_providers())
    except Exception:
        return ()


def select_onnx_providers(requested: str | None = "auto") -> ProviderSelection:
    req = (requested or "auto").strip().lower()
    available = available_providers()
    if not available:
        return ProviderSelection(req, available, (), False, "onnxruntime is not installed or no providers are available")
    preferred = _PROVIDER_ALIASES.get(req)
    if preferred is None:
        # Accept exact provider names for advanced users.
        preferred = (requested or "", "CPUExecutionProvider")
    if not preferred:
        return ProviderSelection(req, available, available, True, "auto: using ONNX Runtime reported provider order")
    selected = tuple(p for p in preferred if p in available)
    if selected:
        return ProviderSelection(req, available, selected, True, "requested provider is available")
    return ProviderSelection(req, available, (), False, f"requested provider {requested!r} is not available")


def provider_report(requested: str | None = "auto") -> dict:
    s = select_onnx_providers(requested)
    return {
        "requested": s.requested,
        "available": list(s.available),
        "selected": list(s.providers),
        "ok": s.ok,
        "reason": s.reason,
    }
