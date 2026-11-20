import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.resume_database import ResumeBase
from backend.app.database import resume_models  # noqa: F401
from backend.app.database.resume_models import (
    CandidateResume,
    GuestCandidate,
)
from backend.app.services.interview_session_service import (
    InterviewSessionNotFoundError,
    InterviewSessionValidationError,
    append_transcript_message,
    create_interview_session,
    end_interview_session,
    get_interview_transcript,
    get_owned_interview_session,
    mark_interview_started,
    update_interview_progress,
)


# =========================================================
# TEST DATABASE
# =========================================================

@pytest.fixture
def db_session(tmp_path):
    database_path = tmp_path / "interview_service_test.db"

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    ResumeBase.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        engine.dispose()


# =========================================================
# TEST CANDIDATES AND RESUMES
# =========================================================

@pytest.fixture
def candidates(db_session):
    candidate_a = GuestCandidate(
        id=str(uuid.uuid4()),
        token_hash="a" * 64,
    )

    candidate_b = GuestCandidate(
        id=str(uuid.uuid4()),
        token_hash="b" * 64,
    )

    db_session.add_all([
        candidate_a,
        candidate_b,
    ])

    db_session.commit()

    return candidate_a, candidate_b


@pytest.fixture
def resumes(db_session, candidates):
    candidate_a, candidate_b = candidates

    resume_a = CandidateResume(
        id=str(uuid.uuid4()),
        candidate_id=candidate_a.id,
        storage_key=str(uuid.uuid4()),
        original_filename="candidate-a.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        raw_text="Candidate A resume text",
        structured_data={
            "skills": ["Python", "FastAPI"],
            "projects": ["Backend application"],
        },
    )

    resume_b = CandidateResume(
        id=str(uuid.uuid4()),
        candidate_id=candidate_b.id,
        storage_key=str(uuid.uuid4()),
        original_filename="candidate-b.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        raw_text="Candidate B resume text",
        structured_data={
            "skills": ["Java"],
            "projects": ["Java application"],
        },
    )

    db_session.add_all([
        resume_a,
        resume_b,
    ])

    db_session.commit()

    return resume_a, resume_b


# =========================================================
# HELPERS
# =========================================================

def create_session(db_session, candidate, resume):
    return create_interview_session(
        db_session,
        candidate_id=candidate.id,
        room_name=f"interview-{uuid.uuid4()}",
        role_id="generative_ai_engineer",
        resume_id=resume.id,
    )


def mark_technical_interview_completed(
    db_session,
    session,
    candidate,
    question_ids=None,
):
    """
    Set the exact state required for a completed technical interview.
    """

    if question_ids is None:
        question_ids = [
            "question-001",
            "question-002",
            "question-003",
        ]

    return update_interview_progress(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        current_stage="completed",
        structured_memory={
            "technical_interview": {
                "stage_complete": True,
                "completed_main_question_ids": question_ids,
            }
        },
    )


# =========================================================
# SESSION CREATION
# =========================================================

def test_create_persists_session_and_required_resume(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    assert session.id
    assert session.candidate_id == candidate.id
    assert session.resume_id == resume.id

    assert session.role_id == "generative_ai_engineer"
    assert session.status == "created"

    assert session.current_stage == "not_started"
    assert session.current_main_question_id is None

    assert session.used_main_question_ids == []
    assert session.follow_up_count == 0

    assert session.completed_question_ids == []
    assert session.completed_stages == []

    assert session.structured_memory == {}

    assert session.started_at is None
    assert session.ended_at is None


def test_create_rejects_missing_resume(
    db_session,
    candidates,
):
    candidate, _ = candidates

    with pytest.raises(TypeError):
        create_interview_session(
            db_session,
            candidate_id=candidate.id,
            room_name=f"interview-{uuid.uuid4()}",
            role_id="generative_ai_engineer",
        )


def test_create_rejects_blank_resume_id(
    db_session,
    candidates,
):
    candidate, _ = candidates

    with pytest.raises(InterviewSessionValidationError):
        create_interview_session(
            db_session,
            candidate_id=candidate.id,
            room_name=f"interview-{uuid.uuid4()}",
            role_id="generative_ai_engineer",
            resume_id=" ",
        )


def test_create_rejects_resume_owned_by_another_candidate(
    db_session,
    candidates,
    resumes,
):
    _, candidate_b = candidates
    resume_a, _ = resumes

    with pytest.raises(InterviewSessionValidationError):
        create_session(
            db_session,
            candidate_b,
            resume_a,
        )


# =========================================================
# CANDIDATE OWNERSHIP
# =========================================================

def test_candidate_cannot_access_another_candidates_session(
    db_session,
    candidates,
    resumes,
):
    candidate_a, candidate_b = candidates
    resume_a, _ = resumes

    session = create_session(
        db_session,
        candidate_a,
        resume_a,
    )

    with pytest.raises(InterviewSessionNotFoundError):
        get_owned_interview_session(
            db_session,
            session_id=session.id,
            candidate_id=candidate_b.id,
        )


# =========================================================
# SESSION START
# =========================================================

def test_start_is_idempotent_and_persists_timestamp(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    started = mark_interview_started(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    first_timestamp = started.started_at

    started_again = mark_interview_started(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert started_again.status == "in_progress"
    assert started_again.started_at == first_timestamp
    assert first_timestamp is not None


# =========================================================
# INTERVIEW PROGRESS
# =========================================================

def test_progress_and_structured_memory_are_persisted(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    updated = update_interview_progress(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        current_stage="main_questions",
        current_main_question_id="question-001",
        used_main_question_ids=["question-001"],
        follow_up_count=1,
        completed_question_ids=[],
        completed_stages=["introduction"],
        structured_memory={
            "candidate_summary": "Backend developer",
            "last_answer_summary": "Explained API design",
        },
    )

    assert updated.current_stage == "main_questions"

    assert updated.current_main_question_id == "question-001"
    assert updated.used_main_question_ids == ["question-001"]

    assert updated.follow_up_count == 1
    assert updated.completed_stages == ["introduction"]

    assert updated.structured_memory["candidate_summary"] == (
        "Backend developer"
    )


def test_progress_rejects_negative_follow_up_count(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    with pytest.raises(InterviewSessionValidationError):
        update_interview_progress(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            follow_up_count=-1,
        )


def test_progress_rejects_boolean_follow_up_count(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    with pytest.raises(InterviewSessionValidationError):
        update_interview_progress(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            follow_up_count=True,
        )


def test_progress_rejects_non_integer_follow_up_count(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    with pytest.raises(InterviewSessionValidationError):
        update_interview_progress(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            follow_up_count=1.5,
        )


# =========================================================
# TRANSCRIPT
# =========================================================

def test_transcript_is_separate_and_ordered(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    append_transcript_message(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        speaker="interviewer",
        message_text="Please introduce yourself.",
    )

    append_transcript_message(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        speaker="candidate",
        message_text="I am a computer science student.",
    )

    update_interview_progress(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        structured_memory={
            "summary": "Candidate introduced themselves."
        },
    )

    transcript = get_interview_transcript(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert len(transcript) == 2

    assert [
        item.sequence_number for item in transcript
    ] == [1, 2]

    assert [
        item.speaker for item in transcript
    ] == [
        "interviewer",
        "candidate",
    ]

    assert transcript[1].message_text == (
        "I am a computer science student."
    )

    assert session.structured_memory == {
        "summary": "Candidate introduced themselves."
    }


def test_transcript_is_isolated_between_candidates(
    db_session,
    candidates,
    resumes,
):
    candidate_a, candidate_b = candidates
    resume_a, _ = resumes

    session = create_session(
        db_session,
        candidate_a,
        resume_a,
    )

    with pytest.raises(InterviewSessionNotFoundError):
        get_interview_transcript(
            db_session,
            session_id=session.id,
            candidate_id=candidate_b.id,
        )


def test_transcript_rejects_invalid_speaker_type(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    with pytest.raises(InterviewSessionValidationError):
        append_transcript_message(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            speaker=None,
            message_text="Test message",
        )


# =========================================================
# MILESTONE 2.6 — INCOMPLETE INTERVIEWS
# =========================================================

def test_incomplete_interview_is_marked_interrupted(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended.status == "interrupted"
    assert ended.ended_at is not None


def test_interview_with_only_two_questions_is_interrupted(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    update_interview_progress(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        current_stage="completed",
        structured_memory={
            "technical_interview": {
                "stage_complete": True,
                "completed_main_question_ids": [
                    "question-001",
                    "question-002",
                ],
            }
        },
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended.status == "interrupted"


@pytest.mark.parametrize(
    "question_ids",
    [
        [],
        ["question-001"],
        ["question-001", "question-002"],
        [
            "question-001",
            "question-002",
            "question-002",
        ],
        [
            "question-001",
            "question-002",
            "question-003",
            "question-004",
        ],
    ],
)
def test_interview_requires_exactly_three_distinct_questions(
    db_session,
    candidates,
    resumes,
    question_ids,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    update_interview_progress(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        current_stage="completed",
        structured_memory={
            "technical_interview": {
                "stage_complete": True,
                "completed_main_question_ids": question_ids,
            }
        },
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended.status == "interrupted"


def test_interview_without_completion_flag_is_interrupted(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    update_interview_progress(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        current_stage="completed",
        structured_memory={
            "technical_interview": {
                "stage_complete": False,
                "completed_main_question_ids": [
                    "question-001",
                    "question-002",
                    "question-003",
                ],
            }
        },
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended.status == "interrupted"


# =========================================================
# MILESTONE 2.6 — COMPLETED INTERVIEWS
# =========================================================

def test_three_completed_questions_mark_interview_completed(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    mark_technical_interview_completed(
        db_session,
        session,
        candidate,
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended.status == "completed"
    assert ended.ended_at is not None


def test_completed_interview_preserves_original_end_timestamp(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    mark_technical_interview_completed(
        db_session,
        session,
        candidate,
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    first_timestamp = ended.ended_at

    ended_again = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended_again.status == "completed"
    assert ended_again.ended_at == first_timestamp


# =========================================================
# TERMINAL SESSION PROTECTION
# =========================================================

def test_interrupted_session_is_idempotent_and_blocks_updates(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    ended = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    first_timestamp = ended.ended_at

    ended_again = end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    assert ended_again.status == "interrupted"
    assert ended_again.ended_at == first_timestamp
    assert first_timestamp is not None

    with pytest.raises(InterviewSessionValidationError):
        append_transcript_message(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            speaker="candidate",
            message_text="A late message",
        )

    with pytest.raises(InterviewSessionValidationError):
        mark_interview_started(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
        )

    with pytest.raises(InterviewSessionValidationError):
        update_interview_progress(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            current_stage="main_questions",
        )


def test_completed_session_blocks_future_transcript_messages(
    db_session,
    candidates,
    resumes,
):
    candidate, _ = candidates
    resume, _ = resumes

    session = create_session(
        db_session,
        candidate,
        resume,
    )

    mark_technical_interview_completed(
        db_session,
        session,
        candidate,
    )

    end_interview_session(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
    )

    with pytest.raises(InterviewSessionValidationError):
        append_transcript_message(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            speaker="candidate",
            message_text="A late answer",
        )

    with pytest.raises(InterviewSessionValidationError):
        update_interview_progress(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            current_stage="main_questions",
        )


def test_candidate_cannot_end_another_candidates_session(
    db_session,
    candidates,
    resumes,
):
    candidate_a, candidate_b = candidates
    resume_a, _ = resumes

    session = create_session(
        db_session,
        candidate_a,
        resume_a,
    )

    with pytest.raises(InterviewSessionNotFoundError):
        end_interview_session(
            db_session,
            session_id=session.id,
            candidate_id=candidate_b.id,
        )