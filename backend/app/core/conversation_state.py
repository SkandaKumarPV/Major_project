
from enum import Enum
from dataclasses import dataclass


class ConversationState(Enum):
    INITIALIZING = "initializing"
    AI_SPEAKING = "ai_speaking"
    WAITING_FOR_CANDIDATE = "waiting_for_candidate"
    CANDIDATE_SPEAKING = "candidate_speaking"
    WAITING_FOR_SILENCE = "waiting_for_silence"
    PROCESSING_ANSWER = "processing_answer"
    INTERVIEW_ENDED = "interview_ended"
    ERROR = "error"


@dataclass
class InterviewState:
    current_state: ConversationState = (
        ConversationState.WAITING_FOR_CANDIDATE
    )
    completed_answers: int = 0

    def transition_to(self, new_state: ConversationState):
        if self.current_state == ConversationState.INTERVIEW_ENDED:
            raise RuntimeError("Interview has already ended")

        self.current_state = new_state

    def answer_completed(self):
        if self.current_state == ConversationState.INTERVIEW_ENDED:
            raise RuntimeError(
                "Cannot complete an answer after interview ends"
            )

        if self.current_state != ConversationState.PROCESSING_ANSWER:
            raise RuntimeError(
                "Cannot complete an answer unless it is being processed"
            )

        self.completed_answers += 1

    def end_interview(self):
        self.current_state = ConversationState.INTERVIEW_ENDED
