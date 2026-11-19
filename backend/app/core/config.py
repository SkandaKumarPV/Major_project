
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass
class Settings:
    livekit_url: str = field(
        default_factory=lambda: os.getenv("LIVEKIT_URL", "")
    )
    livekit_api_key: str = field(
        default_factory=lambda: os.getenv("LIVEKIT_API_KEY", "")
    )
    livekit_api_secret: str = field(
        default_factory=lambda: os.getenv("LIVEKIT_API_SECRET", "")
    )

    # Both the worker and API must use exactly the same agent name.
    agent_name: str = field(
        default_factory=lambda: os.getenv(
            "LIVEKIT_AGENT_NAME",
            "simple-ai-interviewer",
        )
    )

    deepgram_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", "")
    )
    cartesia_api_key: str = field(
    default_factory=lambda: os.getenv("CARTESIA_API_KEY", "")
)

    cartesia_model: str = field(
    default_factory=lambda: os.getenv("CARTESIA_MODEL", "sonic-3")
)

    cartesia_voice_id: str = field(
    default_factory=lambda: os.getenv("CARTESIA_VOICE_ID", "")
)

    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "")
    )
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY", "")
    )
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "")
    )

    silence_timeout_seconds: int = field(
        default_factory=lambda: int(
            os.getenv("SILENCE_TIMEOUT_SECONDS", "10")
        )
    )

    opening_message: str = (
        "Hello! Welcome to your interview. "
        "I'm your AI interviewer. "
        "To begin, could you please introduce yourself?"
    )

    @classmethod
    def from_environment(cls):
        load_dotenv()
        return cls()
