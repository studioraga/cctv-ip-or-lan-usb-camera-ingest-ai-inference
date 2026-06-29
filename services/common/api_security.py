"""Small API authorization helpers for local/customer-prem FastAPI services."""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def csv(value: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


@dataclass(frozen=True)
class ApiPrincipal:
    name: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    reason: str
    principal: ApiPrincipal | None = None
    required_roles: tuple[str, ...] = ()


class ApiSecurityConfig:
    """Token + client allow-list + route role map.

    Supported token formats:
      AI_CAMERA_NODE1_API_TOKEN=legacy-admin-token
      AI_CAMERA_NODE1_API_KEYS=name:token:role|role,name2:token2:viewer

    In lab mode, leaving both token variables blank keeps existing demos usable.
    """

    def __init__(
        self,
        *,
        api_keys: Mapping[str, ApiPrincipal] | None = None,
        allowed_clients: Sequence[str] = (),
        enforce_clients: bool = False,
        public_endpoints: Sequence[str] = ("/health", "/metrics"),
        enabled: bool = True,
    ):
        self.api_keys = dict(api_keys or {})
        self.allowed_clients = tuple(allowed_clients)
        self.enforce_clients = bool(enforce_clients or self.allowed_clients)
        self.public_endpoints = tuple(public_endpoints)
        self.enabled = enabled
        self._client_networks = tuple(self._parse_network(v) for v in self.allowed_clients)

    @classmethod
    def from_env(cls, *, service: str = "node1") -> "ApiSecurityConfig":
        if service != "node1":
            raise ValueError("only node1 API security is currently supported")
        keys: dict[str, ApiPrincipal] = {}
        legacy = os.getenv("AI_CAMERA_NODE1_API_TOKEN", "").strip()
        if legacy:
            keys[legacy] = ApiPrincipal("legacy-admin", ("admin", "operator", "viewer", "node2"))
        for spec in csv(os.getenv("AI_CAMERA_NODE1_API_KEYS")):
            # name:token:role1|role2.  Keep tokens colon-free for simple shell env usage.
            parts = spec.split(":", 2)
            if len(parts) != 3:
                continue
            name, token, roles_raw = (p.strip() for p in parts)
            roles = tuple(r.strip() for r in roles_raw.replace(",", "|").split("|") if r.strip())
            if name and token and roles:
                keys[token] = ApiPrincipal(name, roles)
        public = csv(os.getenv("AI_CAMERA_NODE1_PUBLIC_ENDPOINTS", "/health,/metrics")) or ("/health", "/metrics")
        clients = csv(os.getenv("AI_CAMERA_API_CLIENTS"))
        enforce = env_bool("AI_CAMERA_NODE1_ENFORCE_API_CLIENTS", False)
        return cls(api_keys=keys, allowed_clients=clients, enforce_clients=enforce, public_endpoints=public)

    @staticmethod
    def _parse_network(value: str):
        try:
            return ipaddress.ip_network(value, strict=False)
        except ValueError:
            return ipaddress.ip_network(f"{value}/32", strict=False)

    def security_posture(self) -> dict:
        return {
            "enabled": self.enabled,
            "api_keys_configured": bool(self.api_keys),
            "api_key_principals": [p.name for p in self.api_keys.values()],
            "client_allowlist_configured": bool(self.allowed_clients),
            "client_allowlist_enforced": self.enforce_clients,
            "allowed_clients": list(self.allowed_clients),
            "public_endpoints": list(self.public_endpoints),
            "rbac_model": "route-prefix roles: viewer/operator/admin/node2",
        }

    def is_public(self, path: str) -> bool:
        for endpoint in self.public_endpoints:
            if endpoint.endswith("/*"):
                if path.startswith(endpoint[:-1]):
                    return True
            elif path == endpoint:
                return True
        return False

    def _client_allowed(self, client_ip: str | None) -> bool:
        if not self.enforce_clients:
            return True
        if not client_ip:
            return False
        try:
            ip = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(ip in net for net in self._client_networks)

    @staticmethod
    def required_roles(method: str, path: str) -> tuple[str, ...]:
        method = method.upper()
        if path.startswith("/motion/events/node2"):
            return ("node2", "operator", "admin")
        if path.startswith("/security") or path.startswith("/models/verify"):
            return ("admin",)
        if path.startswith("/models"):
            return ("viewer", "operator", "admin")
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            return ("operator", "admin")
        return ("viewer", "operator", "admin", "node2")

    def authorize(self, *, method: str, path: str, client_ip: str | None, headers: Mapping[str, str]) -> AuthDecision:
        required = self.required_roles(method, path)
        if not self.enabled:
            return AuthDecision(True, "security disabled", required_roles=required)
        if self.is_public(path):
            return AuthDecision(True, "public endpoint", required_roles=())
        if not self._client_allowed(client_ip):
            return AuthDecision(False, "client IP is not allow-listed", required_roles=required)
        if not self.api_keys:
            # Lab compatibility: no configured token means IP/policy controls only.
            return AuthDecision(True, "no API keys configured", required_roles=required)
        token = headers.get("x-api-key") or headers.get("X-API-Key") or ""
        principal = self.api_keys.get(token)
        if principal is None:
            return AuthDecision(False, "missing or invalid API key", required_roles=required)
        if not any(role in principal.roles for role in required):
            return AuthDecision(False, "API key lacks required role", principal=principal, required_roles=required)
        return AuthDecision(True, "authorized", principal=principal, required_roles=required)
