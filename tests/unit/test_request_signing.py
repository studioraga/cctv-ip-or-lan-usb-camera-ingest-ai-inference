from services.common.request_signing import signed_headers, verify_signature


def test_signed_request_roundtrip():
    body = b'{"ok":true}'
    headers = signed_headers("secret", "POST", "/motion/events/node2", body, timestamp=1000, nonce="abc")
    result = verify_signature("secret", "POST", "/motion/events/node2", headers, body, now=1000)
    assert result.ok


def test_signed_request_rejects_tampered_body():
    headers = signed_headers("secret", "POST", "/x", b"a", timestamp=1000, nonce="abc")
    result = verify_signature("secret", "POST", "/x", headers, b"b", now=1000)
    assert not result.ok
    assert "body" in result.reason
