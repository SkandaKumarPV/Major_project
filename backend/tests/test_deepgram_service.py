
import pytest

from backend.app.core.config import Settings
from backend.app.services.deepgram_service import DeepgramService


def make_settings():
    return Settings(
        deepgram_api_key="test-deepgram-key",
    )


def test_service_requires_api_key():
    settings = make_settings()
    settings.deepgram_api_key = ""

    with pytest.raises(ValueError, match="Deepgram API key"):
        DeepgramService(settings)


def test_service_creates_deepgram_stt(monkeypatch):
    settings = make_settings()
    captured = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "backend.app.services.deepgram_service.deepgram.STT",
        FakeSTT,
    )

    service = DeepgramService(settings)

    assert service.stt is not None
    assert captured["api_key"] == "test-deepgram-key"
    assert captured["model"] == "nova-3"
    assert captured["language"] == "en-IN"


def test_service_enables_interim_transcripts(monkeypatch):
    settings = make_settings()
    captured = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "backend.app.services.deepgram_service.deepgram.STT",
        FakeSTT,
    )

    DeepgramService(settings)

    assert captured["interim_results"] is True


def test_service_enables_punctuation(monkeypatch):
    settings = make_settings()
    captured = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "backend.app.services.deepgram_service.deepgram.STT",
        FakeSTT,
    )

    DeepgramService(settings)

    assert captured["punctuate"] is True
