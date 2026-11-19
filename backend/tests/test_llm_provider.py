
import pytest

from backend.app.core.config import Settings
from backend.app.services.llm_provider import LLMProvider


def make_settings():
    return Settings(
        llm_provider="nvidia",
        llm_model="nvidia/nemotron-3-ultra-550b-a55b",
        llm_api_key="test-api-key",
        llm_base_url="https://integrate.api.nvidia.com/v1",
    )


def test_provider_requires_api_key():
    settings = make_settings()
    settings.llm_api_key = ""

    with pytest.raises(ValueError, match="API key"):
        LLMProvider(settings)


def test_provider_requires_model():
    settings = make_settings()
    settings.llm_model = ""

    with pytest.raises(ValueError, match="model"):
        LLMProvider(settings)


def test_provider_requires_base_url():
    settings = make_settings()
    settings.llm_base_url = ""

    with pytest.raises(ValueError, match="base URL"):
        LLMProvider(settings)


def test_generate_response_returns_llm_answer(monkeypatch):
    settings = make_settings()
    provider = LLMProvider(settings)

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "That's interesting. "
                                "What did you learn from that experience?"
                            )
                        }
                    }
                ]
            }

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "backend.app.services.llm_provider.requests.post",
        fake_post,
    )

    response = provider.generate_response(
        "I have experience working with robotic arms."
    )

    assert response == (
        "That's interesting. "
        "What did you learn from that experience?"
    )

    assert captured["url"] == (
        "https://integrate.api.nvidia.com/v1/chat/completions"
    )

    assert captured["headers"]["Authorization"] == (
        "Bearer test-api-key"
    )

    assert captured["payload"]["model"] == (
        "nvidia/nemotron-3-ultra-550b-a55b"
    )

    assert captured["payload"]["messages"][-1] == {
        "role": "user",
        "content": "I have experience working with robotic arms.",
    }


def test_generate_response_rejects_empty_answer():
    provider = LLMProvider(make_settings())

    with pytest.raises(ValueError, match="answer"):
        provider.generate_response("   ")
