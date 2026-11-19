
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.services.livekit_service import LiveKitService


@pytest.mark.asyncio
async def test_end_session_deletes_room(monkeypatch):
    fake_client = SimpleNamespace(
        room=SimpleNamespace(
            delete_room=AsyncMock()
        ),
        aclose=AsyncMock(),
    )

    monkeypatch.setattr(
        "backend.app.services.livekit_service.api.LiveKitAPI",
        lambda **kwargs: fake_client,
    )

    settings = SimpleNamespace(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
    )

    service = LiveKitService(settings)

    await service.end_session("interview-test-room")

    request = fake_client.room.delete_room.call_args.args[0]

    assert request.room == "interview-test-room"


@pytest.mark.asyncio
async def test_end_session_rejects_non_interview_room(monkeypatch):
    fake_client = SimpleNamespace(
        room=SimpleNamespace(
            delete_room=AsyncMock()
        ),
        aclose=AsyncMock(),
    )

    monkeypatch.setattr(
        "backend.app.services.livekit_service.api.LiveKitAPI",
        lambda **kwargs: fake_client,
    )

    settings = SimpleNamespace(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
    )

    service = LiveKitService(settings)

    with pytest.raises(ValueError, match="Invalid interview room name"):
        await service.end_session("unrelated-room")

    fake_client.room.delete_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_releases_livekit_client(monkeypatch):
    fake_client = SimpleNamespace(
        room=SimpleNamespace(),
        aclose=AsyncMock(),
    )

    monkeypatch.setattr(
        "backend.app.services.livekit_service.api.LiveKitAPI",
        lambda **kwargs: fake_client,
    )

    settings = SimpleNamespace(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
    )

    service = LiveKitService(settings)

    await service.close()

    fake_client.aclose.assert_awaited_once()
