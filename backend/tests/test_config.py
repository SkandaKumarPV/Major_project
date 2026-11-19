
from backend.app.core.config import Settings


def test_default_silence_timeout():
    settings = Settings()
    assert settings.silence_timeout_seconds == 10


def test_default_opening_message():
    settings = Settings()
    assert settings.opening_message == (
        "Hello! Welcome to your interview. "
        "I'm your AI interviewer. "
        "To begin, could you please introduce yourself?"
    )


def test_llm_provider_is_configurable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "test-provider")
    settings = Settings()
    assert settings.llm_provider == "test-provider"

def test_default_agent_name(monkeypatch):
    monkeypatch.delenv("LIVEKIT_AGENT_NAME", raising=False)

    settings = Settings()

    assert settings.agent_name == "simple-ai-interviewer"
