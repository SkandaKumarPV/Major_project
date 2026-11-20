from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.database.resume_database import (
    DEFAULT_RESUME_DATABASE_URL,
    create_resume_engine,
    initialize_resume_database,
)
from backend.app.database.resume_models import (
    CandidateResume,
    EvaluationReport,
    GuestCandidate,
    InterviewSessionRecord,
    InterviewTranscriptMessage,
)


def test_resume_database_uses_a_separate_database():
    assert "interview_data.db" in DEFAULT_RESUME_DATABASE_URL
    assert "role_question_bank.db" not in DEFAULT_RESUME_DATABASE_URL


def test_resume_database_creates_expected_tables(tmp_path):
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
            "evaluation_reports",
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
            completed_question_ids=[
                "question_10",
                "question_11",
            ],
            completed_stages=["introduction"],
            structured_memory={
                "candidate_summary": "Experienced with Python and RAG.",
                "topics_discussed": ["Python", "RAG"],
                "important_context": [
                    "Built a document retrieval system"
                ],
            },
            started_at=datetime.now(timezone.utc),
        )

        with Session(engine) as db:
            db.add(interview)
            db.commit()

        # Simulate a new database session after reconnecting.
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
            assert saved.ended_at is None

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

        messages = [
            InterviewTranscriptMessage(
                id=str(uuid4()),
                interview=interview,
                sequence_number=1,
                speaker="interviewer",
                message_text="Tell me about yourself.",
            ),
            InterviewTranscriptMessage(
                id=str(uuid4()),
                interview=interview,
                sequence_number=2,
                speaker="candidate",
                message_text="I am a computer science student.",
            ),
            InterviewTranscriptMessage(
                id=str(uuid4()),
                interview=interview,
                sequence_number=3,
                speaker="interviewer",
                message_text="What technologies have you used?",
            ),
        ]

        with Session(engine) as db:
            db.add(interview)
            db.add_all(messages)
            db.commit()

        # Retrieve the transcript independently after reopening the session.
        with Session(engine) as db:
            saved_interview = db.get(
                InterviewSessionRecord,
                session_id,
            )

            saved_messages = (
                db.query(InterviewTranscriptMessage)
                .filter_by(interview_session_id=session_id)
                .order_by(
                    InterviewTranscriptMessage.sequence_number
                )
                .all()
            )

            assert saved_interview is not None
            assert len(saved_messages) == 3

            assert [
                message.sequence_number
                for message in saved_messages
            ] == [1, 2, 3]

            assert [
                message.speaker
                for message in saved_messages
            ] == [
                "interviewer",
                "candidate",
                "interviewer",
            ]

            assert [
                message.message_text
                for message in saved_messages
            ] == [
                "Tell me about yourself.",
                "I am a computer science student.",
                "What technologies have you used?",
            ]

            assert saved_interview.structured_memory == {
                "candidate_summary": "Candidate knows Python.",
            }

            assert all(
                message.created_at is not None
                for message in saved_messages
            )

    finally:
        engine.dispose()


# =========================================================
# MILESTONE 2.6 — EVALUATION REPORT PERSISTENCE
# =========================================================

def test_evaluation_report_persists_after_database_reconnection(
    tmp_path,
):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    candidate_id = str(uuid4())
    resume_id = str(uuid4())
    session_id = str(uuid4())
    report_id = str(uuid4())

    resume_report = {
        "score": 8.2,
        "strengths": [
            {
                "claim": "Python experience",
                "evidence": "Python, FastAPI",
            }
        ],
        "missing_or_weak_skills": [
            "Deployment experience is not clearly evidenced."
        ],
        "experience_alignment": [],
        "improvement_areas": [
            "Provide more detail about deployment."
        ],
        "score_rationale": "Relevant backend experience is evidenced.",
    }

    interview_report = {
        "score": 7.4,
        "technical_strengths": [
            "Explained the basic RAG architecture."
        ],
        "weak_or_incorrect_answers": [
            "Retrieval evaluation was incomplete."
        ],
        "missing_concepts": [
            "Precision and recall",
        ],
        "answer_by_answer_feedback": [
            {
                "question": "Explain RAG.",
                "correctness": "partially_correct",
                "feedback": "Explain the complete retrieval flow.",
                "evidence": "A RAG application retrieves documents.",
                "missing_concepts": ["Context construction"],
            }
        ],
        "reasoning_and_justification": (
            "The candidate demonstrated partial understanding."
        ),
        "recommendations": [
            "Study retrieval evaluation metrics."
        ],
        "score_rationale": (
            "The candidate demonstrated reasonable technical knowledge."
        ),
    }

    try:
        initialize_resume_database(target_engine=engine)

        candidate = GuestCandidate(
            id=candidate_id,
            token_hash="e" * 64,
        )

        resume = CandidateResume(
            id=resume_id,
            candidate=candidate,
            storage_key=f"{resume_id}.pdf",
            original_filename="report-test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            raw_text="Private resume text.",
            structured_data={
                "skills": ["Python", "FastAPI"],
                "projects": [],
                "work_experience": [],
                "education": [],
                "certifications": [],
            },
        )

        interview = InterviewSessionRecord(
            id=session_id,
            room_name="evaluation-report-test-room",
            candidate=candidate,
            resume=resume,
            role_id="generative_ai_engineer",
            status="completed",
            current_stage="completed",
            structured_memory={
                "technical_interview": {
                    "stage_complete": True,
                    "completed_main_question_ids": [
                        "question-001",
                        "question-002",
                        "question-003",
                    ],
                }
            },
        )

        report = EvaluationReport(
            id=report_id,
            candidate_id=candidate_id,
            interview_session_id=session_id,
            resume_id=resume_id,
            role_id="generative_ai_engineer",
            completion_status="completed",
            resume_score=8.2,
            interview_score=7.4,
            resume_report=resume_report,
            interview_report=interview_report,
        )

        with Session(engine) as db:
            db.add(interview)
            db.flush()

            db.add(report)
            db.commit()

        # Reopen the database to verify durable report persistence.
        with Session(engine) as db:
            saved_report = db.get(
                EvaluationReport,
                report_id,
            )

            assert saved_report is not None

            assert saved_report.candidate_id == candidate_id
            assert saved_report.interview_session_id == session_id
            assert saved_report.resume_id == resume_id
            assert saved_report.role_id == "generative_ai_engineer"

            assert saved_report.completion_status == "completed"

            # The two scores must remain separate.
            assert saved_report.resume_score == 8.2
            assert saved_report.interview_score == 7.4

            assert saved_report.resume_report["score"] == 8.2
            assert saved_report.interview_report["score"] == 7.4

            assert (
                saved_report.resume_report["strengths"][0]["claim"]
                == "Python experience"
            )

            assert (
                saved_report.interview_report[
                    "missing_concepts"
                ]
                == ["Precision and recall"]
            )

    finally:
        engine.dispose()


def test_evaluation_report_session_association_is_unique(tmp_path):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    try:
        initialize_resume_database(target_engine=engine)

        candidate = GuestCandidate(
            id=str(uuid4()),
            token_hash="f" * 64,
        )

        resume = CandidateResume(
            id=str(uuid4()),
            candidate=candidate,
            storage_key=f"{uuid4()}.pdf",
            original_filename="unique-report.pdf",
            mime_type="application/pdf",
            size_bytes=512,
            raw_text="Resume text.",
            structured_data={"skills": ["Python"]},
        )

        interview = InterviewSessionRecord(
            id=str(uuid4()),
            room_name="unique-report-room",
            candidate=candidate,
            resume=resume,
            role_id="generative_ai_engineer",
            status="completed",
        )

        with Session(engine) as db:
            db.add(interview)
            db.flush()

            first_report = EvaluationReport(
                id=str(uuid4()),
                candidate_id=candidate.id,
                interview_session_id=interview.id,
                resume_id=resume.id,
                role_id="generative_ai_engineer",
                completion_status="completed",
                resume_score=8.0,
                interview_score=7.0,
                resume_report={"score": 8.0},
                interview_report={"score": 7.0},
            )

            db.add(first_report)
            db.commit()

            duplicate_report = EvaluationReport(
                id=str(uuid4()),
                candidate_id=candidate.id,
                interview_session_id=interview.id,
                resume_id=resume.id,
                role_id="generative_ai_engineer",
                completion_status="completed",
                resume_score=9.0,
                interview_score=9.0,
                resume_report={"score": 9.0},
                interview_report={"score": 9.0},
            )

            db.add(duplicate_report)

            try:
                db.commit()
                pytest.fail(
                    "A second report for the same interview was accepted."
                )

            except Exception:
                db.rollback()

            saved_count = db.query(EvaluationReport).filter_by(
                interview_session_id=interview.id
            ).count()

            assert saved_count == 1

    finally:
        engine.dispose()


# =========================================================
# LEGACY DATABASE MIGRATION
# =========================================================

def test_existing_interview_database_is_migrated_without_losing_records(
    tmp_path,
):
    database_path = tmp_path / "interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    candidate_id = str(uuid4())
    session_id = str(uuid4())

    try:
        # Simulate the previous schema before the newer milestones.
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE guest_candidates (
                        id VARCHAR(36) PRIMARY KEY,
                        token_hash VARCHAR(64) NOT NULL UNIQUE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE interview_sessions (
                        id VARCHAR(36) PRIMARY KEY,
                        room_name VARCHAR(255) NOT NULL UNIQUE,
                        candidate_id VARCHAR(36) NOT NULL,
                        resume_id VARCHAR(36),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    INSERT INTO guest_candidates (id, token_hash)
                    VALUES (:candidate_id, :token_hash)
                    """
                ),
                {
                    "candidate_id": candidate_id,
                    "token_hash": "d" * 64,
                },
            )

            connection.execute(
                text(
                    """
                    INSERT INTO interview_sessions
                    (id, room_name, candidate_id)
                    VALUES (:session_id, :room_name, :candidate_id)
                    """
                ),
                {
                    "session_id": session_id,
                    "room_name": "old-interview-room",
                    "candidate_id": candidate_id,
                },
            )

        # Initialization adds missing columns and creates missing tables.
        initialize_resume_database(target_engine=engine)

        with Session(engine) as db:
            saved = db.get(
                InterviewSessionRecord,
                session_id,
            )

            assert saved is not None
            assert saved.room_name == "old-interview-room"
            assert saved.candidate_id == candidate_id

            # Existing records receive safe defaults.
            assert saved.status == "created"
            assert saved.used_main_question_ids == []
            assert saved.follow_up_count == 0
            assert saved.completed_question_ids == []
            assert saved.completed_stages == []
            assert saved.structured_memory == {}

            # New nullable fields remain unset for legacy records.
            assert saved.role_id is None
            assert saved.started_at is None
            assert saved.ended_at is None

        # Milestone 2.6 report table must also be created.
        tables = set(inspect(engine).get_table_names())

        assert "evaluation_reports" in tables
        assert "interview_transcript_messages" in tables

        # A second initialization must be safe.
        initialize_resume_database(target_engine=engine)

        with Session(engine) as db:
            saved_again = db.get(
                InterviewSessionRecord,
                session_id,
            )

            assert saved_again is not None
            assert saved_again.room_name == "old-interview-room"

    finally:
        engine.dispose()