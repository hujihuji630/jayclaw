"""Tests for chat server."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from jay_web_ui.server import ChatServer


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    llm.complete = Mock(return_value=Mock(content="Test response"))
    return llm


def test_server_creation_with_llm(mock_llm):
    """Test creating server with LLM."""
    server = ChatServer(llm=mock_llm, title="Test")
    assert server.title == "Test"
    assert server.llm == mock_llm
    assert server.port == 8000


def test_server_creation_requires_llm_or_agent():
    """Test server requires either LLM or agent."""
    with pytest.raises(ValueError, match="Must provide either llm or agent"):
        ChatServer()


def test_server_creation_with_custom_port(mock_llm):
    """Test server with custom port."""
    server = ChatServer(llm=mock_llm, port=8080)
    assert server.port == 8080


def test_server_creation_with_cors(mock_llm):
    """Test server with CORS enabled."""
    server = ChatServer(llm=mock_llm, cors=True)
    # CORS middleware should be added
    assert any(m.cls.__name__ == "CORSMiddleware" for m in server.app.user_middleware)


_HOST_HEADERS = {"Host": "127.0.0.1:8000"}


def test_server_routes(mock_llm):
    """Test server has required routes."""
    server = ChatServer(llm=mock_llm)
    client = TestClient(server.app)

    # Test home page (Host header required: anti-DNS-rebinding middleware)
    response = client.get("/", headers=_HOST_HEADERS)
    assert response.status_code == 200

    # Test history endpoint
    response = client.get("/api/history", headers=_HOST_HEADERS)
    assert response.status_code == 200
    assert "messages" in response.json()


def test_server_clear_history(mock_llm):
    """Test clearing history."""
    server = ChatServer(llm=mock_llm)
    client = TestClient(server.app)

    # Add some history
    server.history.append(Mock())
    assert len(server.history) > 0

    # Clear history
    response = client.delete("/api/history", headers=_HOST_HEADERS)
    assert response.status_code == 200
    assert len(server.history) == 0


def test_server_format_sse(mock_llm):
    """Test SSE formatting."""
    from jay_web_ui.models import StreamChunk

    server = ChatServer(llm=mock_llm)
    chunk = StreamChunk(type="token", content="Hello")

    sse = server._format_sse(chunk)
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    assert "Hello" in sse


def test_server_with_agent():
    """Test server with agent."""
    mock_agent = Mock()
    mock_agent.run = Mock(return_value=Mock(content="Agent response"))

    server = ChatServer(agent=mock_agent)
    assert server.agent == mock_agent
    assert server.llm is None


def test_server_theme(mock_llm):
    """Test server with custom theme."""
    theme = {"primary_color": "#ff0000"}
    server = ChatServer(llm=mock_llm, theme=theme)
    assert server.theme == theme


@pytest.fixture
def server_with_history(mock_llm):
    """Build a ChatServer with 4 pre-populated messages for D3/D17 tests."""
    from jay_web_ui.models import ChatMessage
    server = ChatServer(llm=mock_llm, title="Test", port=8765)
    server.history.extend([
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="hi"),
        ChatMessage(role="user", content="ping"),
        ChatMessage(role="assistant", content="pong"),
    ])
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    return client, server


def test_history_endpoint_returns_message_ids(server_with_history):
    client, _ = server_with_history
    r = client.get('/api/history')
    assert r.status_code == 200
    messages = r.json()['messages']
    assert messages, 'fixture should have ≥1 message'
    for m in messages:
        assert 'id' in m and m['id'], f'message missing id: {m}'
    # IDs are unique within a history.
    ids = [m['id'] for m in messages]
    assert len(set(ids)) == len(ids)


def test_chat_message_auto_generates_id():
    from jay_web_ui.models import ChatMessage
    a = ChatMessage(role='user', content='hi')
    b = ChatMessage(role='user', content='hi')
    assert a.id and b.id and a.id != b.id


def test_chat_message_explicit_id_round_trips():
    from jay_web_ui.models import ChatMessage
    m = ChatMessage(id='my-custom-id', role='user', content='hi')
    assert m.id == 'my-custom-id'
    assert m.model_dump()['id'] == 'my-custom-id'


def test_truncate_removes_after_id(server_with_history):
    """Truncate keeps messages up to and including the named one; removes everything after."""
    client, server = server_with_history
    ids = [m.id for m in server.history]
    assert len(ids) >= 4, 'fixture should have ≥4 messages'
    target = ids[1]

    r = client.post('/api/messages/truncate', json={'after_id': target})
    assert r.status_code == 200
    payload = r.json()
    assert payload['removed'] == len(ids) - 2  # m2, m3 gone

    after = [m.id for m in server.history]
    assert after == ids[:2]


def test_truncate_unknown_id_returns_400(server_with_history):
    client, _ = server_with_history
    r = client.post('/api/messages/truncate', json={'after_id': 'does-not-exist'})
    assert r.status_code == 400


def test_truncate_missing_body_returns_422(server_with_history):
    """Missing required body field should be a Pydantic validation error (422)."""
    client, _ = server_with_history
    r = client.post('/api/messages/truncate', json={})
    assert r.status_code == 422


def test_export_md_returns_markdown(server_with_history):
    """Export endpoint returns text/markdown with attachment disposition + alternating turns."""
    client, _ = server_with_history
    r = client.get('/api/sessions/current/export.md')
    assert r.status_code == 200
    assert 'text/markdown' in r.headers['content-type']
    cd = r.headers.get('content-disposition', '')
    assert 'attachment' in cd
    assert '.md' in cd
    body = r.text
    # Has at least the user + assistant turn markers (Chinese headings).
    assert '## 你' in body
    assert '## JayClaw' in body


def test_export_md_skips_system_role(server_with_history):
    """System / non-conversational roles should not bleed into the export."""
    client, server = server_with_history
    from jay_web_ui.models import ChatMessage
    server.history.append(ChatMessage(role='system', content='SECRET'))
    r = client.get('/api/sessions/current/export.md')
    assert 'SECRET' not in r.text


def test_export_md_unknown_session_returns_404(server_with_history):
    client, _ = server_with_history
    r = client.get('/api/sessions/some-other-id/export.md')
    assert r.status_code == 404
