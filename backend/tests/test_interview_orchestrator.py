
import asyncio
import pytest

from backend.app.core.config import Settings
from backend.app.core.conversation_state import ConversationState
from backend.app.agent.interview_orchestrator import InterviewOrchestrator


class FakeLLM:
    def __init__(self):
        self.received_answers = []

    def generate_response(self, answer):
        self.received_answers.append(answer)
        return "Interesting. What was your biggest challenge?"


@pytest.mark.asyncio
async def test_start_speaks_opening_message():
    spoken_messages = []

    async def speak(text):
        spoken_messages.append(text)

    settings = Settings(silence_timeout_seconds=0.1)
    orchestrator = InterviewOrchestrator(
        settings=settings,
        llm_provider=FakeLLM(),
        speak=speak,
    )

    await orchestrator.start()

    assert spoken_messages == [settings.opening_message]
    assert orchestrator.state.current_state == (
        ConversationState.WAITING_FOR_CANDIDATE
    )


@pytest.mark.asyncio
async def test_candidate_answer_is_processed_after_silence():
    spoken_messages = []
    llm = FakeLLM()

    async def speak(text):
        spoken_messages.append(text)

    settings = Settings(silence_timeout_seconds=0.1)
    orchestrator = InterviewOrchestrator(
        settings=settings,
        llm_provider=llm,
        speak=speak,
    )

    await orchestrator.start()

    orchestrator.speech_started()
    orchestrator.add_transcript("I am a computer science student.")
    orchestrator.speech_stopped()

    await asyncio.sleep(0.2)

    assert llm.received_answers == [
        "I am a computer science student."
    ]
    assert spoken_messages[-1] == (
    "Interesting. What was your biggest challenge?"
)
    assert orchestrator.state.completed_answers == 1


@pytest.mark.asyncio
async def test_interim_transcript_is_not_submitted_to_llm():
    llm = FakeLLM()

    async def speak(text):
        pass

    settings = Settings(silence_timeout_seconds=0.1)
    orchestrator = InterviewOrchestrator(
        settings=settings,
        llm_provider=llm,
        speak=speak,
    )

    await orchestrator.start()

    orchestrator.speech_started()
    orchestrator.add_transcript(
        "I am still speaking",
        is_final=False,
    )
    orchestrator.speech_stopped()

    await asyncio.sleep(0.2)

    assert llm.received_answers == []


@pytest.mark.asyncio
async def test_final_transcript_is_submitted_only_once():
    llm = FakeLLM()

    async def speak(text):
        pass

    settings = Settings(silence_timeout_seconds=0.1)
    orchestrator = InterviewOrchestrator(
        settings=settings,
        llm_provider=llm,
        speak=speak,
    )

    await orchestrator.start()

    orchestrator.speech_started()
    orchestrator.add_transcript("My answer.", is_final=True)
    orchestrator.speech_stopped()

    await asyncio.sleep(0.25)

    assert len(llm.received_answers) == 1


@pytest.mark.asyncio
async def test_ending_interview_prevents_further_processing():
    llm = FakeLLM()

    async def speak(text):
        pass

    settings = Settings(silence_timeout_seconds=0.1)
    orchestrator = InterviewOrchestrator(
        settings=settings,
        llm_provider=llm,
        speak=speak,
    )

    await orchestrator.start()

    orchestrator.speech_started()
    orchestrator.add_transcript("My answer.")
    orchestrator.speech_stopped()

    await orchestrator.end()

    await asyncio.sleep(0.2)

    assert llm.received_answers == []
    assert orchestrator.state.current_state == (
        ConversationState.INTERVIEW_ENDED
    )
