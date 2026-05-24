"""Tests for the Host-header anti-DNS-rebinding middleware.

Pins behaviour:
- When server binds to 127.0.0.1 / localhost, requests without a recognized
  Host header are 400-rejected.
- When server binds to 0.0.0.0 / a real IP, the middleware is NOT installed
  (operator is opting into LAN/public exposure).
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from jay_web_ui.server import ChatServer


@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.config = Mock(model="test-model")
    llm.complete = Mock(return_value=Mock(content="hi"))
    return llm


def test_host_header_check_blocks_evil_host(mock_llm):
    """A request claiming Host: evil.com is rejected with 400."""
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=8000)
    client = TestClient(server.app)

    resp = client.get("/api/history", headers={"Host": "evil.com"})
    assert resp.status_code == 400
    assert "unexpected Host" in resp.json()["detail"]


def test_host_header_check_blocks_dns_rebind_with_port(mock_llm):
    """Even evil.com:8000 (the same port we're on) is refused."""
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=8000)
    client = TestClient(server.app)

    resp = client.get("/api/history", headers={"Host": "evil.com:8000"})
    assert resp.status_code == 400


def test_host_header_check_allows_localhost_with_port(mock_llm):
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=8000)
    client = TestClient(server.app)

    resp = client.get("/api/history", headers={"Host": "localhost:8000"})
    assert resp.status_code == 200


def test_host_header_check_allows_127_with_port(mock_llm):
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=8000)
    client = TestClient(server.app)

    resp = client.get("/api/history", headers={"Host": "127.0.0.1:8000"})
    assert resp.status_code == 200


def test_host_header_check_allows_portless_localhost(mock_llm):
    """Browsers strip the default port for some schemes — tolerate it."""
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=8000)
    client = TestClient(server.app)

    resp = client.get("/api/history", headers={"Host": "localhost"})
    assert resp.status_code == 200


def test_host_header_check_uses_configured_port(mock_llm):
    """Different port → only that port is considered valid."""
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=12345)
    client = TestClient(server.app)

    # Right host, wrong port (we are on 12345, not 8000)
    resp = client.get("/api/history", headers={"Host": "127.0.0.1:8000"})
    assert resp.status_code == 400

    # Right host, right port
    resp = client.get("/api/history", headers={"Host": "127.0.0.1:12345"})
    assert resp.status_code == 200


def test_host_header_check_disabled_when_binding_lan(mock_llm):
    """When binding to 0.0.0.0, operator opts out of the rebinding guard."""
    server = ChatServer(llm=mock_llm, host="0.0.0.0", port=8000)
    client = TestClient(server.app)

    # No Host header check — random host should pass through
    resp = client.get("/api/history", headers={"Host": "evil.com"})
    assert resp.status_code == 200


def test_host_header_check_no_header_passes(mock_llm):
    """An empty / missing Host header isn't treated as an attack — TestClient
    typically supplies one but we explicitly allow the empty case so legitimate
    HTTP/1.0 clients aren't broken."""
    server = ChatServer(llm=mock_llm, host="127.0.0.1", port=8000)
    client = TestClient(server.app)

    # TestClient sets Host automatically; we have to override with empty
    resp = client.get("/api/history", headers={"Host": ""})
    assert resp.status_code == 200
