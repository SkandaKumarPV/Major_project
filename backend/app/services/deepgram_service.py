
from livekit.plugins import deepgram

from backend.app.core.config import Settings


class DeepgramService:
    def __init__(self, settings: Settings):
        if not settings.deepgram_api_key:
            raise ValueError("Deepgram API key is required")

        self.stt = deepgram.STT(
            api_key=settings.deepgram_api_key,
            model="nova-3",
            language="en-IN",
            interim_results=True,
            punctuate=True,
        )
