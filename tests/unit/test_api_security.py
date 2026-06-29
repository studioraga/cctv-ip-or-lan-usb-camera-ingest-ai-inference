from services.common.api_security import ApiPrincipal, ApiSecurityConfig


def test_api_security_allows_public_endpoint_without_token():
    cfg = ApiSecurityConfig(api_keys={"tok": ApiPrincipal("viewer", ("viewer",))})
    decision = cfg.authorize(method="GET", path="/health", client_ip="127.0.0.1", headers={})
    assert decision.allowed


def test_api_security_enforces_rbac_for_write_route():
    cfg = ApiSecurityConfig(api_keys={"tok": ApiPrincipal("viewer", ("viewer",))})
    decision = cfg.authorize(method="POST", path="/capture/sessions", client_ip="127.0.0.1", headers={"X-API-Key": "tok"})
    assert not decision.allowed
    assert "role" in decision.reason


def test_api_security_allows_node2_role_for_motion_webhook():
    cfg = ApiSecurityConfig(api_keys={"tok": ApiPrincipal("node2", ("node2",))})
    decision = cfg.authorize(method="POST", path="/motion/events/node2", client_ip="192.168.29.188", headers={"X-API-Key": "tok"})
    assert decision.allowed


def test_api_security_client_allowlist():
    cfg = ApiSecurityConfig(allowed_clients=("192.168.29.188/32",), enforce_clients=True)
    assert cfg.authorize(method="GET", path="/events", client_ip="192.168.29.188", headers={}).allowed
    assert not cfg.authorize(method="GET", path="/events", client_ip="192.168.29.200", headers={}).allowed
