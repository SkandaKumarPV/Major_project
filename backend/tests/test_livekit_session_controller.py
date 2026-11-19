
import asyncio
from types import SimpleNamespace

import pytest

from backend.app.agent.livekit_session_controller import (
    LiveKitSessionController,
)


class FakeAgentSession:
    def __init__(self):
        self.callbacks = {}
        self.committed_turns = []

    def on(self, event_name, callback):
        self.callbacks[event_name] = callback

    def emit_event(self, event_name, event):
        self.callbacks[event_name](event)

    def commit_user_turn(self, *, transcript_timeout):
        self.committed_turns.append(transcript_timeout)


@pytest.mark.asyncio
async def test_candidate_speech_starts_silence_detection():
    session = FakeAgentSession()

    statuses = []

    controller = LiveKitSessionController(
        session,
        silence_timeout_seconds=0.05,
        on_status=statuses.append,
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    assert statuses[-1] == "CANDIDATE_SPEAKING"

    await controller.close()


@pytest.mark.asyncio
async def test_candidate_turn_committed_after_silence():
    session = FakeAgentSession()

    statuses = []

    controller = LiveKitSessionController(
        session,
        silence_timeout_seconds=0.05,
        transcript_timeout_seconds=1.5,
        on_status=statuses.append,
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="speaking",
            new_state="listening",
        ),
    )

    await asyncio.sleep(0.1)

    assert session.committed_turns == [1.5]
    assert "PROCESSING_ANSWER" in statuses

    await controller.close()


@pytest.mark.asyncio
async def test_new_speech_resets_silence_timer():
    session = FakeAgentSession()

    controller = LiveKitSessionController(
        session,
        silence_timeout_seconds=0.1,
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="speaking",
            new_state="listening",
        ),
    )

    await asyncio.sleep(0.06)

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="speaking",
            new_state="listening",
        ),
    )

    await asyncio.sleep(0.06)

    assert session.committed_turns == []

    await asyncio.sleep(0.06)

    assert len(session.committed_turns) == 1

    await controller.close()


@pytest.mark.asyncio
async def test_ai_speaking_cancels_candidate_silence_timer():
    session = FakeAgentSession()

    controller = LiveKitSessionController(
        session,
        silence_timeout_seconds=0.1,
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    session.emit_event(
        "user_state_changed",
        SimpleNamespace(
            old_state="speaking",
            new_state="listening",
        ),
    )

    session.emit_event(
        "agent_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    await asyncio.sleep(0.15)

    assert session.committed_turns == []

    await controller.close()


def test_transcript_callback_receives_text_and_final_flag():
    session = FakeAgentSession()

    transcripts = []

    controller = LiveKitSessionController(
        session,
        on_transcript=lambda text, is_final: transcripts.append(
            (text, is_final)
        ),
    )

    session.emit_event(
        "user_input_transcribed",
        SimpleNamespace(
            transcript="I am a computer science student.",
            is_final=False,
        ),
    )

    session.emit_event(
        "user_input_transcribed",
        SimpleNamespace(
            transcript="I am a computer science student.",
            is_final=True,
        ),
    )

    assert transcripts == [
        ("I am a computer science student.", False),
        ("I am a computer science student.", True),
    ]


def test_agent_speaking_status_is_reported():
    session = FakeAgentSession()

    statuses = []

    controller = LiveKitSessionController(
        session,
        on_status=statuses.append,
    )

    session.emit_event(
        "agent_state_changed",
        SimpleNamespace(
            old_state="listening",
            new_state="speaking",
        ),
    )

    assert statuses == ["AI_SPEAKING"]
