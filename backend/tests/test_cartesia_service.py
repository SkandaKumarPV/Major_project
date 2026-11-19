
import pytest

from backend.app.core.config import Settings
from backend.app.services.cartesia_service import CartesiaService


def make_settings():
    return Settings(
        cartesia_api_key="test-cartesia-key",
    )


def test_service_requires_api_key():
    settings = make_settings()
    settings.cartesia_api_key = ""

    with pytest.raises(ValueError, match="Cartesia API key"):
        CartesiaService(settings)


def test_service_creates_cartesia_tts(monkeypatch):
    settings = make_settings()
    captured = {}

    class FakeTTS:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "backend.app.services.cartesia_service.cartesia.TTS",
        FakeTTS,
    )

    service = CartesiaService(settings)

    assert service.tts is not None
    assert captured["api_key"] == "test-cartesia-key"
    assert captured["model"] == "sonic-3"
    assert captured["language"] == "en"


def test_service_uses_cartesia_plugin(monkeypatch):
    settings = make_settings()
    created = []

    class FakeTTS:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(
        "backend.app.services.cartesia_service.cartesia.TTS",
        FakeTTS,
    )

    CartesiaService(settings)

    assert len(created) == 1
