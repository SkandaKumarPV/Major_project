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
from backend.app.services.interview_transcript_recorder import (
    InterviewTranscriptRecorder,
)
from backend.app.services.interview_runtime_service import (
    InterviewRuntimeService,
)

logger = logging.getLogger("ai-interviewer")


def prewarm(proc):
    """Load VAD once when the worker process starts."""
    proc.userdata["vad"] = silero.VAD.load()


def build_agent_session(
    settings,
    vad,
    llm_provider=None,
    response_handler=None,
):
    """Create a LiveKit session using the configured AI services."""

    deepgram_service = DeepgramService(settings)
    cartesia_service = CartesiaService(settings)

    if llm_provider is None:
        llm_provider = LLMProvider(settings)

    if response_handler is None:
        livekit_llm = LiveKitLLM(llm_provider)
    else:
        livekit_llm = LiveKitLLM(
            llm_provider,
            response_handler=response_handler,
        )

    return AgentSession(
        turn_detection="manual",
        stt=deepgram_service.stt,
        vad=vad,
        llm=livekit_llm,
        tts=cartesia_service.tts,
        allow_interruptions=False,
    )


def create_interviewer_agent():
    """Create the AI interviewer agent."""

    return Agent(
        instructions=(
            "You are a professional AI interviewer. "
            "The backend controls the interview workflow and supplies "
            "the next question after each finalized candidate answer. "
            "Speak the supplied response naturally and clearly. "
            "Do not independently invent questions, skip stages, "
            "or ask multiple questions at once."
        )
    )


async def entrypoint(ctx):
    """Run one persistent interview session for an assigned room."""

    settings = Settings.from_environment()

    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        raise RuntimeError(
            "VAD is not initialized. Check the worker prewarm function."
        )

    room_name = getattr(ctx.room, "name", None)
    if not isinstance(room_name, str) or not room_name.strip():
        raise RuntimeError(
            "LiveKit room name is required for a persistent interview."
        )

    llm_provider = LLMProvider(settings)

    # Resolve the persistent session, candidate-owned resume and role
    # before the voice session starts.
    runtime = InterviewRuntimeService(
        room_name=room_name,
        llm_provider=llm_provider,
    )

    session = build_agent_session(
        settings,
        vad,
        llm_provider=llm_provider,
        response_handler=runtime.process_candidate_answer,
    )

    # AgentSession.start connects the room.
    await session.start(
        agent=create_interviewer_agent(),
        room=ctx.room,
    )

    # The participant is available only after the room is connected.
    publisher = LiveKitEventPublisher(
        ctx.room.local_participant
    )

    transcript_recorder = InterviewTranscriptRecorder(
        room_name=room_name,
    )

    controller = LiveKitSessionController(
        session=session,
        silence_timeout_seconds=settings.silence_timeout_seconds,
        transcript_timeout_seconds=2,
        on_transcript=publisher.publish_transcript,
        on_status=publisher.publish_status,
        on_candidate_transcript=(
            transcript_recorder.record_candidate_transcript
        ),
        on_conversation_item=(
            transcript_recorder.record_conversation_item
        ),
    )

    ctx.add_shutdown_callback(controller.close)
    ctx.add_shutdown_callback(publisher.close)
    ctx.add_shutdown_callback(transcript_recorder.close)

    # Stage 1 always begins with the backend-generated introduction.
    opening = runtime.start()

    speech_handle = session.say(
        opening,
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
    cli.run_app(build_worker_options(settings))


if __name__ == "__main__":
    main()