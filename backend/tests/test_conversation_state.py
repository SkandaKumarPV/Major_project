
import pytest

from backend.app.core.conversation_state import (
    ConversationState,
    InterviewState,
)


def test_initial_state_is_waiting_for_candidate():
    state = InterviewState()
    assert state.current_state == ConversationState.WAITING_FOR_CANDIDATE


def test_state_can_change_to_ai_speaking():
    state = InterviewState()
    state.transition_to(ConversationState.AI_SPEAKING)
    assert state.current_state == ConversationState.AI_SPEAKING


def test_state_tracks_completed_answers():
    state = InterviewState()
    state.transition_to(ConversationState.PROCESSING_ANSWER)
    state.answer_completed()
    assert state.completed_answers == 1


def test_interview_cannot_transition_after_ending():
    state = InterviewState()
    state.end_interview()

    with pytest.raises(RuntimeError):
        state.transition_to(ConversationState.AI_SPEAKING)


def test_interview_cannot_complete_answer_after_ending():
    state = InterviewState()
    state.end_interview()

    with pytest.raises(RuntimeError):
        state.answer_completed()


def test_answer_cannot_be_completed_without_processing():
    state = InterviewState()

    with pytest.raises(RuntimeError):
        state.answer_completed()


def test_completed_answer_count_starts_at_zero():
    state = InterviewState()
    assert state.completed_answers == 0
