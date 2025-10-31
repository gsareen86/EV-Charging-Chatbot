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


def test_token_creates_room_and_dispatch(monkeypatch):
    fake_api = FakeLiveKitAPI()

    monkeypatch.setattr(server, "LiveKitAPI", lambda *args, **kwargs: fake_api)
    monkeypatch.setattr(server, "TwirpError", FakeTwirpError)

    server._dispatch_cache.clear()

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
    assert "brand-new-room" in server._dispatch_cache
