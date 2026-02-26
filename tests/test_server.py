from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend import server
from livekit.api.twirp_client import TwirpErrorCode


class FakeTwirpError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class FakeAgentDispatch:
    def __init__(self):
        self.create_calls = []

    async def list_dispatch(self, room_name: str):
        raise FakeTwirpError(TwirpErrorCode.NOT_FOUND, "room missing")

    async def create_dispatch(self, request):
        self.create_calls.append(request)


class FakeRoom:
    def __init__(self):
        self.created_rooms = []

    async def create_room(self, request):
        self.created_rooms.append(request.name)


class FakeLiveKitAPI:
    def __init__(self, *args, **kwargs):
        self.agent_dispatch = FakeAgentDispatch()
        self.room = FakeRoom()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _clear_dispatch_cache():
    server._dispatch_cache.clear()


def test_token_creates_room_and_dispatch(monkeypatch):
    fake_api = FakeLiveKitAPI()

    monkeypatch.setattr(server, "LiveKitAPI", lambda *args, **kwargs: fake_api)
    monkeypatch.setattr(server, "TwirpError", FakeTwirpError)

    _clear_dispatch_cache()

    client = TestClient(server.app)

    response = client.post(
        "/api/token",
        json={"roomName": "brand-new-room", "participantName": "Alice"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["roomName"] == "brand-new-room"
    assert payload["participantName"] == "Alice"
    assert "token" in payload

    assert fake_api.room.created_rooms == ["brand-new-room"]
    assert len(fake_api.agent_dispatch.create_calls) == 1
    assert server._is_room_cached("brand-new-room")


def test_health_check():
    client = TestClient(server.app)
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "EV Charging Chatbot API"
    assert "livekit_url" in payload
    assert "deployment" in payload


def test_config_endpoint():
    client = TestClient(server.app)
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert "en" in payload["supported_languages"]
    assert "hi" in payload["supported_languages"]
    assert "livekit_url" in payload
    assert "deployment" in payload


def test_token_missing_fields():
    client = TestClient(server.app)

    # Missing participantName
    response = client.post("/api/token", json={"roomName": "test-room"})
    assert response.status_code == 422

    # Missing roomName
    response = client.post("/api/token", json={"participantName": "Alice"})
    assert response.status_code == 422

    # Empty body
    response = client.post("/api/token", json={})
    assert response.status_code == 422


def test_token_invalid_room_name():
    client = TestClient(server.app)

    # Room name with special characters
    response = client.post(
        "/api/token",
        json={"roomName": "room with spaces!", "participantName": "Alice"},
    )
    assert response.status_code == 422

    # Room name too long (over 64 chars)
    response = client.post(
        "/api/token",
        json={"roomName": "a" * 65, "participantName": "Alice"},
    )
    assert response.status_code == 422

    # Empty room name
    response = client.post(
        "/api/token",
        json={"roomName": "", "participantName": "Alice"},
    )
    assert response.status_code == 422


def test_token_invalid_participant_name():
    client = TestClient(server.app)

    # Participant name with script injection attempt
    response = client.post(
        "/api/token",
        json={"roomName": "test-room", "participantName": "<script>alert(1)</script>"},
    )
    assert response.status_code == 422


def test_serve_index():
    client = TestClient(server.app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_serve_static_404():
    client = TestClient(server.app)
    response = client.get("/nonexistent-file.xyz")
    assert response.status_code == 404


def test_path_traversal_blocked():
    client = TestClient(server.app)
    response = client.get("/../../../etc/passwd")
    assert response.status_code in (403, 404)


def test_dispatch_cache_ttl():
    """Test that the bounded dispatch cache works correctly."""
    _clear_dispatch_cache()

    server._cache_room("room-1")
    assert server._is_room_cached("room-1")

    # Verify cache eviction at max size
    for i in range(server._DISPATCH_CACHE_MAX_SIZE + 5):
        server._cache_room(f"room-{i}")

    assert len(server._dispatch_cache) <= server._DISPATCH_CACHE_MAX_SIZE

    _clear_dispatch_cache()


def test_token_valid_names(monkeypatch):
    """Test that valid room/participant names with hyphens and underscores are accepted."""
    fake_api = FakeLiveKitAPI()
    monkeypatch.setattr(server, "LiveKitAPI", lambda *args, **kwargs: fake_api)
    monkeypatch.setattr(server, "TwirpError", FakeTwirpError)
    _clear_dispatch_cache()

    client = TestClient(server.app)
    response = client.post(
        "/api/token",
        json={"roomName": "my-room_123", "participantName": "user_42"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["roomName"] == "my-room_123"
    assert payload["participantName"] == "user_42"
