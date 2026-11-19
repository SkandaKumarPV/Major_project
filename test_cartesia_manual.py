import asyncio
import aiohttp

from backend.app.core.config import Settings
from livekit.plugins import cartesia
from livekit.plugins.cartesia import tts as cartesia_tts

async def main():
    settings = Settings.from_environment()

    # Diagnostic only: test the newer Cartesia API version.
    cartesia_tts.API_VERSION = "2025-04-16"

    print("API key loaded:", bool(settings.cartesia_api_key))
    print("Model:", settings.cartesia_model)
    print("Voice ID loaded:", bool(settings.cartesia_voice_id))
    print("Testing Cartesia API version:", cartesia_tts.API_VERSION)

    async with aiohttp.ClientSession() as http_session:
        tts = cartesia.TTS(
            api_key=settings.cartesia_api_key,
            model=settings.cartesia_model,
            voice=settings.cartesia_voice_id,
            language="en",
            http_session=http_session,
        )

        total_bytes = 0
        chunk_count = 0

        try:
            print("\nSending synthesis request...")
            stream = tts.synthesize(
                "Hello! This is a test of the AI interviewer voice."
            )

            async for event in stream:
                frame = getattr(event, "frame", None)
                if frame is not None:
                    total_bytes += len(frame.data)
                    chunk_count += 1

            print("\nSYNTHESIS FINISHED")
            print("Audio chunks:", chunk_count)
            print("Audio bytes:", total_bytes)
            print("RESULT:", "SUCCESS" if total_bytes > 0 else "NO AUDIO")

        except Exception as exc:
            print("\nCARTESIA REQUEST FAILED")
            print("Error type:", type(exc).__name__)
            print("Error:", str(exc))

        finally:
            await tts.aclose()

if __name__ == "__main__":
    asyncio.run(main())
