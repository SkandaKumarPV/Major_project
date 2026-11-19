
import logging

from livekit.agents import (
    Agent,
    AgentSession,
    WorkerOptions,
    cli,
)
from livekit.plugins import silero

from backend.app.core.config import Settings
from backend.app.agent.livekit_session_controller import (
    LiveKitSessionController,
)
from backend.app.services.deepgram_service import DeepgramService
from backend.app.services.cartesia_service import CartesiaService
from backend.app.services.llm_provider import LLMProvider
from backend.app.services.livekit_llm import LiveKitLLM
from backend.app.services.livekit_event_publisher import (
    LiveKitEventPublisher,
)


logger = logging.getLogger("ai-interviewer")


def prewarm(proc):
    """Load VAD once when the worker process starts."""
    proc.userdata["vad"] = silero.VAD.load()


def build_agent_session(settings, vad):
    """Create a LiveKit session using our selected AI services."""

    deepgram_service = DeepgramService(settings)
    cartesia_service = CartesiaService(settings)
    llm_provider = LLMProvider(settings)

    return AgentSession(
        turn_detection="manual",
        stt=deepgram_service.stt,
        vad=vad,
        llm=LiveKitLLM(llm_provider),
        tts=cartesia_service.tts,
        allow_interruptions=False,
    )


def create_interviewer_agent():
    """Create the AI interviewer with its conversation instructions."""

    return Agent(
        instructions=(
            "You are a professional AI interviewer. "
            "Listen carefully to the candidate's answers. "
            "Respond naturally and briefly. "
            "Acknowledge the candidate's answer and ask one "
            "relevant follow-up interview question. "
            "Ask only one question at a time."
        )
    )


async def entrypoint(ctx):
    """Run one interview session for an assigned LiveKit room."""

    settings = Settings.from_environment()

    vad = ctx.proc.userdata.get("vad")

    if vad is None:
        raise RuntimeError(
            "VAD is not initialized. Check the worker prewarm function."
        )

    session = build_agent_session(settings, vad)

    # IMPORTANT:
    # AgentSession.start() connects the agent to the assigned room.
    # The local participant is unavailable before this completes.
    await session.start(
        agent=create_interviewer_agent(),
        room=ctx.room,
    )

    # The room is now connected.
    # It is safe to access the local participant.
    publisher = LiveKitEventPublisher(
        ctx.room.local_participant
    )

    controller = LiveKitSessionController(
        session=session,
        silence_timeout_seconds=settings.silence_timeout_seconds,
        transcript_timeout_seconds=2,
        on_transcript=publisher.publish_transcript,
        on_status=publisher.publish_status,
    )

    # Register cleanup callbacks.
    ctx.add_shutdown_callback(controller.close)
    ctx.add_shutdown_callback(publisher.close)

    # Speak the opening introduction.
    speech_handle = session.say(
        settings.opening_message,
        allow_interruptions=False,
    )

    await speech_handle.wait_for_playout()


def build_worker_options(settings):
    """Configure the LiveKit worker."""

    return WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        ws_url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        agent_name=settings.agent_name,
    )


def main():
    """Start the LiveKit agent worker."""

    settings = Settings.from_environment()
    options = build_worker_options(settings)

    cli.run_app(options)


if __name__ == "__main__":
    main()
