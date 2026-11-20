
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.app.database.resume_database import (
    DEFAULT_RESUME_DATABASE_URL,
    create_resume_engine,
    initialize_resume_database,
)
from backend.app.database.resume_models import (
    CandidateResume,
    GuestCandidate,
    InterviewSessionRecord,
    InterviewTranscriptMessage,
)


def test_resume_database_uses_a_separate_database():
    assert "interview_data.db" in DEFAULT_RESUME_DATABASE_URL
    assert "role_question_bank.db" not in DEFAULT_RESUME_DATABASE_URL


def test_resume_database_creates_only_interview_data_tables(tmp_path):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    try:
        initialize_resume_database(target_engine=engine)

        actual_tables = set(inspect(engine).get_table_names())

        assert actual_tables == {
            "guest_candidates",
            "candidate_resumes",
            "interview_sessions",
            "interview_transcript_messages",
        }

        assert database_path.exists()
        assert not (tmp_path / "role_question_bank.db").exists()
    finally:
        engine.dispose()


def test_candidate_resume_and_interview_relationships(tmp_path):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    try:
        initialize_resume_database(target_engine=engine)

        candidate_id = str(uuid4())
        resume_id = str(uuid4())

        candidate = GuestCandidate(
            id=candidate_id,
            token_hash="a" * 64,
        )

        resume = CandidateResume(
            id=resume_id,
            candidate=candidate,
            storage_key=f"{resume_id}.pdf",
            original_filename="candidate_resume.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            raw_text="Candidate resume raw text.",
            structured_data={
                "candidate_name": "Example Candidate",
                "skills": ["Python", "FastAPI"],
                "education": [],
                "projects": [],
                "work_experience": [],
                "certifications": [],
            },
        )

        interview = InterviewSessionRecord(
            id=str(uuid4()),
            room_name="interview-test-room",
            candidate=candidate,
            resume=resume,
        )

        with Session(engine) as db:
            db.add(interview)
            db.commit()

            saved_interview = (
                db.query(InterviewSessionRecord)
                .filter_by(room_name="interview-test-room")
                .one()
            )

            assert saved_interview.candidate.id == candidate_id
            assert saved_interview.resume.id == resume_id
            assert (
                saved_interview.resume.raw_text
                == "Candidate resume raw text."
            )
            assert (
                saved_interview.resume.structured_data["skills"]
                == ["Python", "FastAPI"]
            )

    finally:
        engine.dispose()


def test_interview_state_persists_after_database_reconnection(tmp_path):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    session_id = str(uuid4())
    candidate_id = str(uuid4())

    try:
        initialize_resume_database(target_engine=engine)

        candidate = GuestCandidate(
            id=candidate_id,
            token_hash="b" * 64,
        )

        interview = InterviewSessionRecord(
            id=session_id,
            room_name="persistent-interview-room",
            candidate=candidate,
            role_id="generative_ai_engineer",
            status="active",
            current_stage="main_interview",
            current_main_question_id="question_12",
            used_main_question_ids=["question_12"],
            follow_up_count=1,
            completed_question_ids=["question_10", "question_11"],
            completed_stages=["introduction"],
            structured_memory={
                "candidate_summary": "Experienced with Python and RAG.",
                "topics_discussed": ["Python", "RAG"],
                "important_context": ["Built a document retrieval system"],
            },
            started_at=datetime.now(timezone.utc),
        )

        with Session(engine) as db:
            db.add(interview)
            db.commit()

        # Simulate closing and reopening the database session.
        with Session(engine) as db:
            saved = db.get(InterviewSessionRecord, session_id)

            assert saved is not None
            assert saved.candidate_id == candidate_id
            assert saved.role_id == "generative_ai_engineer"
            assert saved.status == "active"
            assert saved.current_stage == "main_interview"
            assert saved.current_main_question_id == "question_12"
            assert saved.used_main_question_ids == ["question_12"]
            assert saved.follow_up_count == 1
            assert saved.completed_question_ids == [
                "question_10",
                "question_11",
            ]
            assert saved.completed_stages == ["introduction"]
            assert saved.structured_memory["topics_discussed"] == [
                "Python",
                "RAG",
            ]
            assert saved.started_at is not None

    finally:
        engine.dispose()


def test_transcript_persists_separately_from_structured_memory(tmp_path):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    session_id = str(uuid4())

    try:
        initialize_resume_database(target_engine=engine)

        candidate = GuestCandidate(
            id=str(uuid4()),
            token_hash="c" * 64,
        )

        interview = InterviewSessionRecord(
            id=session_id,
            room_name="transcript-test-room",
            candidate=candidate,
            role_id="generative_ai_engineer",
            status="active",
            structured_memory={
                "candidate_summary": "Candidate knows Python.",
            },
        )

        first_message = InterviewTranscriptMessage(
            id=str(uuid4()),
            interview=interview,
            sequence_number=1,
            speaker="interviewer",
            message_text="Tell me about yourself.",
            created_at=datetime.now(timezone.utc),
        )

        second_message = InterviewTranscriptMessage(
            id=str(uuid4()),
            interview=interview,
            sequence_number=2,
            speaker="candidate",
            message_text="I am a computer science student.",
            created_at=datetime.now(timezone.utc),
        )

        third_message = InterviewTranscriptMessage(
            id=str(uuid4()),
            interview=interview,
            sequence_number=3,
            speaker="interviewer",
            message_text="What technologies have you used?",
            created_at=datetime.now(timezone.utc),
        )

        with Session(engine) as db:
            db.add_all([
                interview,
                first_message,
                second_message,
                third_message,
            ])
            db.commit()

        # Reopen the database and retrieve the transcript independently.
        with Session(engine) as db:
            saved_interview = db.get(InterviewSessionRecord, session_id)

            messages = (
                db.query(InterviewTranscriptMessage)
                .filter_by(interview_session_id=session_id)
                .order_by(InterviewTranscriptMessage.sequence_number)
                .all()
            )

            assert saved_interview is not None
            assert len(messages) == 3

            assert [message.sequence_number for message in messages] == [
                1, 2, 3
            ]

            assert [message.speaker for message in messages] == [
                "interviewer",
                "candidate",
                "interviewer",
            ]

            assert [message.message_text for message in messages] == [
                "Tell me about yourself.",
                "I am a computer science student.",
                "What technologies have you used?",
            ]

            # Structured memory and transcript are separate records.
            assert saved_interview.structured_memory == {
                "candidate_summary": "Candidate knows Python.",
            }

            assert all(message.created_at is not None for message in messages)

    finally:
        engine.dispose()
