import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.models import Role, RoleTechnology
from backend.app.database.resume_database import ResumeBase
from backend.app.database.resume_models import (
    CandidateResume,
    GuestCandidate,
    InterviewSessionRecord,
)
from backend.app.services.interview_session_service import (
    create_interview_session,
    get_interview_transcript,
)
from backend.app.services.interview_transcript_recorder import (
    InterviewTranscriptRecorder,
)
from backend.app.services.interview_runtime_service import (
    InterviewRuntimeService,
)
from app.database.models import (
    Role,
    RoleTechnology,
    InterviewQuestion,
)

class FakeLLMProvider:
    def generate_response(self, prompt, conversation_context=None):
        return (
            '{"decision":"project_question",'
            '"question":"What was the most challenging part of that project?",'
            '"selected_project":null,'
            '"candidate_claim_quote":null,'
            '"resume_evidence_quote":null}'
        )


@pytest.fixture
def runtime_environment(tmp_path, monkeypatch):
    resume_engine = create_engine(
        f"sqlite:///{tmp_path / 'interview_data.db'}",
        connect_args={"check_same_thread": False},
    )

    role_engine = create_engine(
        f"sqlite:///{tmp_path / 'roles.db'}",
        connect_args={"check_same_thread": False},
    )

    ResumeBase.metadata.create_all(bind=resume_engine)
    Base.metadata.create_all(bind=role_engine)

    ResumeTestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=resume_engine,
    )

    RoleTestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=role_engine,
    )

    from backend.app.services import interview_runtime_service

    monkeypatch.setattr(
        interview_runtime_service,
        "ResumeSessionLocal",
        ResumeTestingSession,
    )

    monkeypatch.setattr(
        interview_runtime_service,
        "SessionLocal",
        RoleTestingSession,
    )

    candidate_id = str(uuid.uuid4())
    resume_id = str(uuid.uuid4())
    room_name = "runtime-persistence-test"

    with RoleTestingSession() as role_db:
        role = Role(
            role_name="Generative AI Engineer",
            role_details="Build and evaluate AI-powered applications.",
        )

        role_db.add(role)
        role_db.flush()

        role_db.add(
            RoleTechnology(
                role_id=role.id,
                technology="Python",
            )
        )
        test_questions = [
            (
                "What are the main differences between a list and a tuple in Python?",
                "easy",
            ),
            (
                "How would you handle exceptions when calling an external API?",
                "easy",
            ),
            (
                "What is the purpose of a virtual environment in Python?",
                "easy",
            ),
            (
                "How would you design a retrieval-augmented generation pipeline?",
                "medium",
            ),
            (
                "How would you evaluate the quality of a RAG application?",
                "medium",
            ),
            (
                "How would you reduce hallucinations in a production LLM system?",
                "hard",
            ),
        ]

        for question_text, difficulty in test_questions:
            role_db.add(
                InterviewQuestion(
                    role_id=role.id,
                    question_text=question_text,
                    difficulty=difficulty,
                )
            )
        role_db.commit()
        role_id = str(role.id)

    with ResumeTestingSession() as resume_db:
        resume_db.add(
            GuestCandidate(
                id=candidate_id,
                token_hash="a" * 64,
            )
        )

        resume_db.flush()

        resume_db.add(
            CandidateResume(
                id=resume_id,
                candidate_id=candidate_id,
                storage_key=str(uuid.uuid4()),
                original_filename="candidate.pdf",
                mime_type="application/pdf",
                size_bytes=128,
                raw_text="Private resume text",
                structured_data={
                    "name": "Candidate",
                    "skills": ["Python"],
                    "projects": [],
                },
            )
        )

        resume_db.commit()

        interview = create_interview_session(
            resume_db,
            candidate_id=candidate_id,
            room_name=room_name,
            role_id=role_id,
            resume_id=resume_id,
        )

        session_id = interview.id

    yield {
        "resume_session": ResumeTestingSession,
        "candidate_id": candidate_id,
        "session_id": session_id,
        "room_name": room_name,
        "llm": FakeLLMProvider(),
    }

    resume_engine.dispose()
    role_engine.dispose()


def read_persisted_state(environment):
    with environment["resume_session"]() as db:
        interview = (
            db.query(InterviewSessionRecord)
            .filter(
                InterviewSessionRecord.id
                == environment["session_id"]
            )
            .one()
        )

        transcript = get_interview_transcript(
            db,
            session_id=environment["session_id"],
            candidate_id=environment["candidate_id"],
        )

        return interview, transcript


def make_runtime(environment):
    return InterviewRuntimeService(
        room_name=environment["room_name"],
        llm_provider=environment["llm"],
    )


def test_start_persists_opening_prompt_and_stage(runtime_environment):
    runtime = make_runtime(runtime_environment)

    opening = runtime.start()

    interview, transcript = read_persisted_state(runtime_environment)

    assert opening in transcript[0].message_text
    assert transcript[0].speaker == "interviewer"

    assert interview.current_stage == "introduction"

    assert (
        interview.structured_memory["resume_discussion"]["stage"]
        == "introduction"
    )


def test_reconnect_restores_stage_and_replays_existing_opening(
    runtime_environment,
):
    first_runtime = make_runtime(runtime_environment)

    opening = first_runtime.start()

    reconnected_runtime = make_runtime(runtime_environment)

    replayed = reconnected_runtime.start()

    assert replayed == opening
    assert reconnected_runtime.discussion.cross_question_count == 0
    assert reconnected_runtime.discussion.stage.value == "introduction"


def test_candidate_turn_and_next_prompt_survive_reconnect(
    runtime_environment,
):
    runtime = make_runtime(runtime_environment)

    runtime.start()

    next_question = runtime.process_candidate_answer(
        "I am a computer science student and I enjoy building Python projects."
    )

    interview, transcript = read_persisted_state(runtime_environment)

    assert [item.speaker for item in transcript] == [
        "interviewer",
        "candidate",
        "interviewer",
    ]

    assert transcript[1].message_text.startswith(
        "I am a computer science"
    )

    assert transcript[2].message_text == next_question
    assert interview.follow_up_count == 1

    reconnected_runtime = make_runtime(runtime_environment)

    assert reconnected_runtime.start() == next_question
    assert reconnected_runtime.discussion.cross_question_count == 1

    assert len(
        reconnected_runtime.discussion.conversation_history
    ) == 3


def test_transition_occurs_only_after_second_cross_question_answer(
    runtime_environment,
):
    runtime = make_runtime(runtime_environment)

    runtime.start()

    first_question = runtime.process_candidate_answer(
        "Here is my background."
    )

    second_question = runtime.process_candidate_answer(
        "The project used Python and an API."
    )

    assert first_question
    assert second_question

    assert runtime.discussion.cross_question_count == 2
    assert runtime.discussion.stage.value == "resume_discussion"

    transition = runtime.process_candidate_answer(
        "The main challenge was handling inconsistent API responses."
    )

    assert "technical interview" in transition.lower()

    assert (
        runtime.discussion.stage.value
        == "technical_interview"
    )

    interview, transcript = read_persisted_state(runtime_environment)

    assert interview.current_stage == "technical_interview"

    assert "resume_discussion" in interview.completed_stages

    assert transcript[-2].message_text == (
        "The main challenge was handling inconsistent API responses."
    )

    assert transcript[-1].message_text == transition

    reconnected_runtime = make_runtime(runtime_environment)

    assert reconnected_runtime.start() == transition


def test_livekit_recorder_does_not_duplicate_runtime_persisted_prompt(
    runtime_environment,
):
    runtime = make_runtime(runtime_environment)

    opening = runtime.start()

    recorder = InterviewTranscriptRecorder(
        room_name=runtime_environment["room_name"],
        session_factory=runtime_environment["resume_session"],
    )

    recorder.record_conversation_item(
        SimpleNamespace(
            item=SimpleNamespace(
                role="assistant",
                text_content=opening,
            )
        )
    )

    _, transcript = read_persisted_state(runtime_environment)

    assert len(transcript) == 1
    assert transcript[0].message_text == opening

    recorder.close()


def test_runtime_accepts_candidate_transcript_saved_before_answer_processing(
    runtime_environment,
):
    runtime = make_runtime(runtime_environment)

    runtime.start()

    recorder = InterviewTranscriptRecorder(
        room_name=runtime_environment["room_name"],
        session_factory=runtime_environment["resume_session"],
    )

    candidate_answer = (
        "I am studying computer science and use Python."
    )

    recorder.record_candidate_transcript(
        candidate_answer,
        is_final=True,
    )

    next_question = runtime.process_candidate_answer(
        candidate_answer
    )

    _, transcript = read_persisted_state(runtime_environment)

    assert [item.speaker for item in transcript] == [
        "interviewer",
        "candidate",
        "interviewer",
    ]

    assert transcript[1].message_text == candidate_answer
    assert transcript[2].message_text == next_question

    recorder.close()