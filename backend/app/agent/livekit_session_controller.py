
from collections.abc import Callable

from backend.app.core.silence_detector import SilenceDetector


class LiveKitSessionController:
    """
    Connects LiveKit session events to our custom silence detector.

    LiveKit handles STT, LLM, and TTS.
    This controller decides when a candidate turn is committed.
    """

    def __init__(
        self,
        session,
        silence_timeout_seconds: float = 10,
        transcript_timeout_seconds: float = 2,
        on_transcript: Callable | None = None,
        on_status: Callable | None = None,
        on_candidate_transcript: Callable | None = None,
        on_conversation_item: Callable | None = None,
    ):
        self.session = session
        self.transcript_timeout_seconds = transcript_timeout_seconds

        self.on_transcript = on_transcript
        self.on_status = on_status
        self.on_candidate_transcript = on_candidate_transcript
        self.on_conversation_item = on_conversation_item

        self.agent_state = "initializing"
        self.user_state = "listening"

        self.silence_detector = SilenceDetector(
            timeout_seconds=silence_timeout_seconds,
            on_finalize=self._commit_candidate_turn,
        )

        # Register synchronous LiveKit event callbacks.
        self.session.on(
            "user_state_changed",
            self._on_user_state_changed,
        )

        self.session.on(
            "agent_state_changed",
            self._on_agent_state_changed,
        )

        self.session.on(
            "user_input_transcribed",
            self._on_transcript,
        )

        self.session.on(
            "conversation_item_added",
            self._on_conversation_item_added,
        )

    def _notify_status(self, status: str):
        if self.on_status:
            self.on_status(status)

    def _on_user_state_changed(self, event):
        self.user_state = event.new_state

        # Do not start a candidate timer while the AI is speaking.
        if self.agent_state == "speaking":
            return

        if event.new_state == "speaking":
            self.silence_detector.speech_started()
            self._notify_status("CANDIDATE_SPEAKING")

        elif event.new_state == "listening":
            if event.old_state == "speaking":
                self.silence_detector.speech_stopped()
                self._notify_status("WAITING_FOR_SILENCE")

    def _on_agent_state_changed(self, event):
        self.agent_state = event.new_state

        if event.new_state == "speaking":
            # Cancel any candidate silence timer while AI audio plays.
            self.silence_detector.cancel()
            self._notify_status("AI_SPEAKING")

        elif event.new_state == "listening":
            self._notify_status("CANDIDATE_LISTENING")

    def _on_transcript(self, event):
        transcript = event.transcript
        is_final = event.is_final

        # Forward interim and final transcripts to the UI publisher.
        if self.on_transcript:
            self.on_transcript(transcript, is_final)

        # Forward both to the recorder.
        # The recorder itself is responsible for ignoring interim text.
        if self.on_candidate_transcript:
            self.on_candidate_transcript(transcript, is_final)

    def _on_conversation_item_added(self, event):
        # The recorder filters conversation items by role.
        # This allows it to save interviewer messages without
        # duplicating candidate transcripts.
        if self.on_conversation_item:
            self.on_conversation_item(event)

    async def _commit_candidate_turn(self):
        if self.agent_state == "speaking":
            return

        self._notify_status("PROCESSING_ANSWER")

        # This is the single point where the candidate turn is committed.
        # LiveKit then invokes our configured LLM and TTS.
        self.session.commit_user_turn(
            transcript_timeout=self.transcript_timeout_seconds
        )

    async def close(self):
        await self.silence_detector.close()
