
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services import livekit_service


def make_settings(**overrides):
    values = {
        "livekit_url": "wss://test.livekit.cloud",
        "livekit_api_key": "test-key",
        "livekit_api_secret": "test-secret",
        "agent_name": "simple-ai-interviewer",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeAccessToken:
    def __init__(self, *args):
        self.identity = None
        self.name = None
        self.grants = None

    def with_identity(self, identity):
        self.identity = identity
        return self

    def with_name(self, name):
        self.name = name
        return self

    def with_grants(self, grants):
        self.grants = grants
        return self

    def to_jwt(self):
        return "test-candidate-token"


def make_fake_client():
    return SimpleNamespace(
        room=SimpleNamespace(
            create_room=AsyncMock(),
            delete_room=AsyncMock(),
        ),
        agent_dispatch=SimpleNamespace(
            create_dispatch=AsyncMock(
                return_value=SimpleNamespace(id="dispatch-test")
            )
        ),
        aclose=AsyncMock(),
    )


@pytest.fixture
def fake_client(monkeypatch):
    client = make_fake_client()

    monkeypatch.setattr(
        livekit_service.api,
        "LiveKitAPI",
        lambda **kwargs: client,
    )

    monkeypatch.setattr(
        livekit_service.api,
        "AccessToken",
        FakeAccessToken,
    )

    monkeypatch.setattr(
        livekit_service.api,
        "VideoGrants",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    return client


def test_service_requires_livekit_url():
    settings = make_settings(livekit_url="")

    with pytest.raises(ValueError, match="LiveKit URL is required"):
        livekit_service.LiveKitService(settings)


def test_service_requires_api_key():
    settings = make_settings(livekit_api_key="")

    with pytest.raises(ValueError, match="LiveKit API key is required"):
        livekit_service.LiveKitService(settings)


def test_service_requires_api_secret():
    settings = make_settings(livekit_api_secret="")

    with pytest.raises(
        ValueError,
        match="LiveKit API secret is required",
    ):
        livekit_service.LiveKitService(settings)


def test_service_requires_agent_name():
    settings = make_settings(agent_name="")

    with pytest.raises(
        ValueError,
        match="LiveKit agent name is required",
    ):
        livekit_service.LiveKitService(settings)


def test_service_initializes_livekit_client(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    assert service.client is fake_client
    assert service.agent_name == "simple-ai-interviewer"


@pytest.mark.asyncio
async def test_create_session_creates_room_and_candidate_token(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    session = await service.create_session()

    room_request = fake_client.room.create_room.call_args.args[0]

    assert room_request.name == session["room_name"]
    assert room_request.name.startswith("interview-")
    assert room_request.empty_timeout == 300
    assert room_request.max_participants == 2

    assert session["livekit_url"] == "wss://test.livekit.cloud"
    assert session["participant_identity"]
    assert session["token"] == "test-candidate-token"

    # Dispatch must wait until the browser has joined.
    fake_client.agent_dispatch.create_dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_agent_uses_configured_agent_name(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    dispatched = await service.dispatch_agent(
        "interview-test-room"
    )

    request = (
        fake_client.agent_dispatch.create_dispatch.call_args.args[0]
    )

    assert dispatched is True
    assert request.agent_name == "simple-ai-interviewer"
    assert request.room == "interview-test-room"


@pytest.mark.asyncio
async def test_dispatch_agent_does_not_dispatch_same_room_twice(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    first_result = await service.dispatch_agent(
        "interview-test-room"
    )
    second_result = await service.dispatch_agent(
        "interview-test-room"
    )

    assert first_result is True
    assert second_result is False

    fake_client.agent_dispatch.create_dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_agent_rejects_invalid_room_name(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    with pytest.raises(ValueError, match="Invalid interview room name"):
        await service.dispatch_agent("other-room")

    fake_client.agent_dispatch.create_dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_session_deletes_room(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    await service.end_session("interview-test-room")

    request = fake_client.room.delete_room.call_args.args[0]

    assert request.room == "interview-test-room"


@pytest.mark.asyncio
async def test_end_session_rejects_invalid_room_name(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    with pytest.raises(ValueError, match="Invalid interview room name"):
        await service.end_session("other-room")

    fake_client.room.delete_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_releases_livekit_client(fake_client):
    service = livekit_service.LiveKitService(make_settings())

    await service.close()

    fake_client.aclose.assert_awaited_once()
