
from livekit.plugins import cartesia
from livekit.plugins.cartesia import tts as cartesia_tts

from backend.app.core.config import Settings


# Compatibility fix for the installed Cartesia plugin version.
CARTESIA_API_VERSION = "2025-04-16"


class CartesiaService:
    def __init__(self, settings: Settings):
        if not settings.cartesia_api_key:
            raise ValueError("Cartesia API key is required")

        if not settings.cartesia_model:
            raise ValueError("Cartesia model is required")

        if not settings.cartesia_voice_id:
            raise ValueError("Cartesia voice ID is required")

        # Override the older API version used internally by plugin 1.2.8.
        cartesia_tts.API_VERSION = CARTESIA_API_VERSION

        self.tts = cartesia.TTS(
            api_key=settings.cartesia_api_key,
            model=settings.cartesia_model,
            voice=settings.cartesia_voice_id,
            language="en",
        )
