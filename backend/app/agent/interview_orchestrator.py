
import asyncio
from collections.abc import Awaitable, Callable

from backend.app.core.config import Settings
from backend.app.core.conversation_state import (
    ConversationState,
    InterviewState,
)
from backend.app.core.silence_detector import SilenceDetector


class InterviewOrchestrator:
    def __init__(
        self,
        settings: Settings,
        llm_provider,
        speak: Callable[[str], Awaitable[None]],
    ):
        self.settings = settings
        self.llm_provider = llm_provider
        self.speak = speak

        self.state = InterviewState(
            current_state=ConversationState.INITIALIZING
        )

        self._transcript_parts = []
        self._processing_lock = asyncio.Lock()
        self._started = False

        self.silence_detector = SilenceDetector(
            timeout_seconds=settings.silence_timeout_seconds,
            on_finalize=self._finalize_answer,
        )

    async def start(self):
        if self._started:
            raise RuntimeError("Interview has already started")

        self._started = True

        self.state.transition_to(ConversationState.AI_SPEAKING)

        await self.speak(self.settings.opening_message)

        if self.state.current_state == ConversationState.INTERVIEW_ENDED:
            return

        self.state.transition_to(
            ConversationState.WAITING_FOR_CANDIDATE
        )

    def speech_started(self):
        if self.state.current_state in (
            ConversationState.INTERVIEW_ENDED,
            ConversationState.INITIALIZING,
            ConversationState.AI_SPEAKING,
            ConversationState.PROCESSING_ANSWER,
        ):
            return

        self.silence_detector.speech_started()

        self.state.transition_to(
            ConversationState.CANDIDATE_SPEAKING
        )

    def add_transcript(
        self,
        text: str,
        is_final: bool = True,
    ):
        if self.state.current_state in (
            ConversationState.INTERVIEW_ENDED,
            ConversationState.AI_SPEAKING,
            ConversationState.PROCESSING_ANSWER,
        ):
            return

        if not is_final or not text.strip():
            return

        self._transcript_parts.append(text.strip())

    def speech_stopped(self):
        if self.state.current_state != (
            ConversationState.CANDIDATE_SPEAKING
        ):
            return

        self.state.transition_to(
            ConversationState.WAITING_FOR_SILENCE
        )

        self.silence_detector.speech_stopped()

    async def _finalize_answer(self):
        async with self._processing_lock:
            if self.state.current_state in (
                ConversationState.INTERVIEW_ENDED,
                ConversationState.AI_SPEAKING,
            ):
                return

            answer = " ".join(self._transcript_parts).strip()

            if not answer:
                self._transcript_parts.clear()

                if self.state.current_state == (
                    ConversationState.WAITING_FOR_SILENCE
                ):
                    self.state.transition_to(
                        ConversationState.WAITING_FOR_CANDIDATE
                    )

                return

            self._transcript_parts.clear()

            self.state.transition_to(
                ConversationState.PROCESSING_ANSWER
            )

            response = await asyncio.to_thread(
                self.llm_provider.generate_response,
                answer,
            )

            if self.state.current_state == (
                ConversationState.INTERVIEW_ENDED
            ):
                return

            self.state.answer_completed()

            self.state.transition_to(
                ConversationState.AI_SPEAKING
            )

            await self.speak(response)

            if self.state.current_state == (
                ConversationState.INTERVIEW_ENDED
            ):
                return

            self.state.transition_to(
                ConversationState.WAITING_FOR_CANDIDATE
            )

    async def end(self):
        await self.silence_detector.close()
        self.state.end_interview()
