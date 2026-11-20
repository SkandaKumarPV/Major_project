import uuid
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.guest import get_resume_db
from backend.app.api.interview_sessions import router
from backend.app.database.resume_database import ResumeBase
from backend.app.database.resume_models import (
    CandidateResume,
    EvaluationReport,
    GuestCandidate,
    InterviewSessionRecord,
    InterviewTranscriptMessage,
)
from backend.app.services import evaluation_report_service
from backend.app.services.guest_identity_service import hash_access_token
from backend.app.services.interview_session_service import (
    append_transcript_message,
)


# =========================================================
# FAKE LIVEKIT SERVICE
# =========================================================

class FakeLiveKitService:
    def __init__(self):
        self.agent_name = "simple-ai-interviewer"
        self.dispatched_rooms = []
        self.ended_rooms = []
        self.create_error = None
        self.dispatch_error = None
        self.end_error = None

    async def create_session(self):
        if self.create_error:
            raise self.create_error

        room_name = f"interview-{uuid.uuid4()}"

        return {
            "livekit_url": "wss://test.livekit.cloud",
            "room_name": room_name,
            "participant_identity": "candidate-test",
            "token": "test-livekit-token",
        }

    async def dispatch_agent(self, room_name):
        if self.dispatch_error:
            raise self.dispatch_error

        self.dispatched_rooms.append(room_name)
        return True

    async def end_session(self, room_name):
        if self.end_error:
            raise self.end_error

        self.ended_rooms.append(room_name)


# =========================================================
# MILESTONE 2.6 — FAKE EVALUATION PROVIDER
# =========================================================

class FakeEvaluationProvider:
    """
    Deterministic evaluation provider.

    Returns:
        1. Resume suitability evaluation.
        2. Interview performance evaluation.

    No external LLM API calls are made during these tests.
    """

    def __init__(self):
        self.calls = []

        self.responses = [
            {
                "score": 8.1,

                "strengths": [
                    {
                        "claim": "Python experience",
                        "evidence": "Python, FastAPI",
                    },
                ],

                "missing_or_weak_skills": [
                    "Deployment experience is not clearly evidenced.",
                ],

                "experience_alignment": [
                    {
                        "claim": "Relevant RAG project",
                        "evidence": (
                            "Built a RAG application using Python and FastAPI."
                        ),
                    },
                ],

                "improvement_areas": [
                    "Add details about deployment experience.",
                ],

                "score_rationale": (
                    "The resume contains relevant backend and RAG evidence."
                ),
            },

            {
                "score": 7.6,

                "technical_strengths": [
                    "Explained the basic RAG architecture.",
                ],

                "weak_or_incorrect_answers": [
                    "Retrieval evaluation could be explained in more detail.",
                ],

                "missing_concepts": [
                    "Precision and recall.",
                ],

                "answer_by_answer_feedback": [
                    {
                        "question": "Explain a RAG application.",
                        "assessment": "Partially correct.",
                        "feedback": (
                            "You described the retrieval and generation flow."
                        ),
                        "missing_concepts": [
                            "Context construction",
                        ],
                        "correctness": "partially_correct",
                        "evidence": (
                            "I built a RAG application using Python and FastAPI."
                        ),
                    },
                    {
                        "question": "What is a vector database?",
                        "assessment": "Technically correct.",
                        "feedback": (
                            "You correctly described embeddings and similarity."
                        ),
                        "missing_concepts": [],
                        "correctness": "technically_correct",
                        "evidence": (
                            "Vector databases store embeddings for similarity search."
                        ),
                    },
                    {
                        "question": "How would you evaluate retrieval?",
                        "assessment": "Incomplete.",
                        "feedback": (
                            "Include measurable retrieval evaluation metrics."
                        ),
                        "missing_concepts": [
                            "Precision",
                            "Recall",
                        ],
                        "correctness": "insufficient_evidence",
                        "evidence": (
                            "I would evaluate retrieval using precision and recall."
                        ),
                    },
                ],

                "reasoning_and_justification": (
                    "The candidate demonstrated a reasonable understanding "
                    "of retrieval and generation."
                ),

                "recommendations": [
                    "Study retrieval evaluation metrics.",
                ],

                "score_rationale": (
                    "The candidate demonstrated partial-to-good "
                    "technical understanding."
                ),
            },
        ]

    def generate_structured_response(
        self,
        system_prompt,
        conversation_context=None,
    ):
        self.calls.append({
            "system_prompt": system_prompt,
            "conversation_context": deepcopy(
                conversation_context
            ),
        })

        if not self.responses:
            raise AssertionError(
                "Unexpected additional evaluation LLM call."
            )

        return self.responses.pop(0)


# =========================================================
# TEST ENVIRONMENT
# =========================================================

@pytest.fixture
def api_environment():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    ResumeBase.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    candidate_token = "candidate-test-token"
    other_token = "other-candidate-token"

    with TestingSession() as db:
        candidate = GuestCandidate(
            id=str(uuid.uuid4()),
            token_hash=hash_access_token(candidate_token),
        )

        other_candidate = GuestCandidate(
            id=str(uuid.uuid4()),
            token_hash=hash_access_token(other_token),
        )

        db.add_all([
            candidate,
            other_candidate,
        ])

        db.flush()

        resume = CandidateResume(
            id=str(uuid.uuid4()),
            candidate_id=candidate.id,
            storage_key=str(uuid.uuid4()),
            original_filename="candidate.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            raw_text="Private candidate resume text",
            structured_data={
                "name": "Candidate",
            },
        )

        other_resume = CandidateResume(
            id=str(uuid.uuid4()),
            candidate_id=other_candidate.id,
            storage_key=str(uuid.uuid4()),
            original_filename="other.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            raw_text="Other candidate resume text",
            structured_data={
                "name": "Other",
            },
        )

        db.add_all([
            resume,
            other_resume,
        ])

        db.commit()

        candidate_id = candidate.id
        other_candidate_id = other_candidate.id
        resume_id = resume.id
        other_resume_id = other_resume.id

    app = FastAPI()
    app.include_router(router)

    livekit = FakeLiveKitService()
    app.state.livekit_service = livekit

    def override_db():
        db = TestingSession()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_resume_db] = override_db

    client = TestClient(app)

    client.headers.update({
        "Authorization": f"Bearer {candidate_token}",
    })

    yield {
        "app": app,
        "client": client,
        "engine": engine,
        "session_factory": TestingSession,
        "livekit": livekit,
        "candidate_id": candidate_id,
        "other_candidate_id": other_candidate_id,
        "candidate_token": candidate_token,
        "other_token": other_token,
        "resume_id": resume_id,
        "other_resume_id": other_resume_id,
    }

    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


# =========================================================
# EXISTING MILESTONE 2.5 — SESSION CREATION
# =========================================================

def test_create_session_requires_guest_authentication(api_environment):
    client = api_environment["client"]
    client.headers.pop("Authorization")

    response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    assert response.status_code == 401


def test_create_session_requires_resume_id(api_environment):
    response = api_environment["client"].post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
        },
    )

    assert response.status_code == 422


def test_create_session_rejects_another_candidates_resume(
    api_environment,
):
    response = api_environment["client"].post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["other_resume_id"],
        },
    )

    assert response.status_code == 422


def test_create_session_persists_record_and_returns_connection(
    api_environment,
):
    response = api_environment["client"].post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["room_name"].startswith("interview-")
    assert data["role_id"] == "generative_ai_engineer"
    assert data["resume_id"] == api_environment["resume_id"]
    assert data["status"] == "created"

    assert data["livekit_url"] == "wss://test.livekit.cloud"
    assert data["token"] == "test-livekit-token"

    with api_environment["session_factory"]() as db:
        saved = db.query(InterviewSessionRecord).filter_by(
            id=data["id"]
        ).one()

        assert saved.candidate_id == api_environment["candidate_id"]
        assert saved.resume_id == api_environment["resume_id"]
        assert saved.room_name == data["room_name"]


# =========================================================
# EXISTING MILESTONE 2.5 — SESSION RETRIEVAL
# =========================================================

def test_get_session_returns_only_owned_session(api_environment):
    client = api_environment["client"]

    create_response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    session_id = create_response.json()["id"]

    response = client.get(
        f"/api/interview-sessions/{session_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == session_id

    client.headers["Authorization"] = (
        f"Bearer {api_environment['other_token']}"
    )

    other_response = client.get(
        f"/api/interview-sessions/{session_id}"
    )

    assert other_response.status_code == 404


def test_list_sessions_returns_only_current_candidates_sessions(
    api_environment,
):
    client = api_environment["client"]

    create_response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    session_id = create_response.json()["id"]

    response = client.get("/api/interview-sessions")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == session_id


# =========================================================
# EXISTING MILESTONE 2.5 — LIVEKIT DISPATCH
# =========================================================

def test_dispatch_starts_owned_session(api_environment):
    client = api_environment["client"]

    create_response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    data = create_response.json()

    response = client.post(
        f"/api/interview-sessions/{data['id']}/dispatch"
    )

    assert response.status_code == 202
    assert response.json()["status"] == "in_progress"
    assert response.json()["dispatched"] is True

    assert api_environment["livekit"].dispatched_rooms == [
        data["room_name"],
    ]


def test_dispatch_rejects_another_candidates_session(
    api_environment,
):
    client = api_environment["client"]

    create_response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    session_id = create_response.json()["id"]

    client.headers["Authorization"] = (
        f"Bearer {api_environment['other_token']}"
    )

    response = client.post(
        f"/api/interview-sessions/{session_id}/dispatch"
    )

    assert response.status_code == 404

    assert api_environment["livekit"].dispatched_rooms == []


# =========================================================
# EXISTING MILESTONE 2.5 — TRANSCRIPT
# =========================================================

def test_transcript_endpoint_returns_ordered_owned_messages(
    api_environment,
):
    client = api_environment["client"]

    create_response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    session_id = create_response.json()["id"]

    with api_environment["session_factory"]() as db:
        append_transcript_message(
            db,
            session_id=session_id,
            candidate_id=api_environment["candidate_id"],
            speaker="interviewer",
            message_text="Please introduce yourself.",
        )

        append_transcript_message(
            db,
            session_id=session_id,
            candidate_id=api_environment["candidate_id"],
            speaker="candidate",
            message_text="I am a computer science student.",
        )

    response = client.get(
        f"/api/interview-sessions/{session_id}/transcript"
    )

    assert response.status_code == 200

    assert [
        item["sequence_number"]
        for item in response.json()
    ] == [1, 2]

    assert response.json()[0]["speaker"] == "interviewer"
    assert response.json()[1]["speaker"] == "candidate"


# =========================================================
# EXISTING MILESTONE 2.5 — END INTERVIEW
# =========================================================

def test_end_session_deletes_room_and_persists_interrupted_status(
    api_environment,
):
    client = api_environment["client"]

    create_response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    data = create_response.json()

    response = client.delete(
        f"/api/interview-sessions/{data['id']}"
    )

    assert response.status_code == 204

    assert api_environment["livekit"].ended_rooms == [
        data["room_name"],
    ]

    with api_environment["session_factory"]() as db:
        saved = db.query(InterviewSessionRecord).filter_by(
            id=data["id"]
        ).one()

        assert saved.status == "interrupted"
        assert saved.ended_at is not None


def test_livekit_creation_failure_does_not_create_database_session(
    api_environment,
):
    client = api_environment["client"]

    api_environment["livekit"].create_error = RuntimeError(
        "LiveKit unavailable"
    )

    response = client.post(
        "/api/interview-sessions",
        json={
            "role_id": "generative_ai_engineer",
            "resume_id": api_environment["resume_id"],
        },
    )

    assert response.status_code == 502

    with api_environment["session_factory"]() as db:
        assert db.query(InterviewSessionRecord).count() == 0


# =========================================================
# MILESTONE 2.6 — COMPLETED INTERVIEW FIXTURE
# =========================================================

def create_completed_interview_for_report(api_environment):
    """
    Create a completed interview with exactly three distinct
    completed main technical questions and an ordered transcript.
    """

    session_id = str(uuid.uuid4())

    with api_environment["session_factory"]() as db:
        resume = db.query(CandidateResume).filter_by(
            id=api_environment["resume_id"],
            candidate_id=api_environment["candidate_id"],
        ).one()

        resume.structured_data = {
            "skills": [
                "Python, FastAPI",
            ],

            "projects": [
                "Built a RAG application using Python and FastAPI.",
            ],

            "work_experience": [],

            "education": [
                "B.Sc. Computer Science",
            ],

            "certifications": [],
        }

        session = InterviewSessionRecord(
            id=session_id,
            room_name=f"report-room-{uuid.uuid4()}",
            candidate_id=api_environment["candidate_id"],
            resume_id=api_environment["resume_id"],
            role_id="generative_ai_engineer",
            status="completed",
            current_stage="completed",
            current_main_question_id=None,

            used_main_question_ids=[
                "question-001",
                "question-002",
                "question-003",
            ],

            follow_up_count=0,

            completed_question_ids=[
                "question-001",
                "question-002",
                "question-003",
            ],

            completed_stages=[
                "introduction",
                "resume_discussion",
                "technical_interview",
            ],

            structured_memory={
                "technical_interview": {
                    "stage_complete": True,

                    "completed_main_question_ids": [
                        "question-001",
                        "question-002",
                        "question-003",
                    ],

                    "turn_assessments": [
                        {
                            "question_id": "question-001",
                            "assessment": "Partially correct",
                        },
                        {
                            "question_id": "question-002",
                            "assessment": "Correct",
                        },
                        {
                            "question_id": "question-003",
                            "assessment": "Incomplete",
                        },
                    ],
                },
            },
        )

        db.add(session)
        db.flush()

        transcript = [
            (
                "interviewer",
                "Please introduce yourself.",
            ),
            (
                "candidate",
                "I am a computer science student interested in AI.",
            ),
            (
                "interviewer",
                "Explain your RAG application.",
            ),
            (
                "candidate",
                "I built a RAG application using Python and FastAPI.",
            ),
            (
                "interviewer",
                "What is a vector database?",
            ),
            (
                "candidate",
                "Vector databases store embeddings for similarity search.",
            ),
            (
                "interviewer",
                "How would you evaluate retrieval?",
            ),
            (
                "candidate",
                "I would evaluate retrieval using precision and recall.",
            ),
        ]

        for index, (speaker, message_text) in enumerate(
            transcript,
            start=1,
        ):
            db.add(
                InterviewTranscriptMessage(
                    id=str(uuid.uuid4()),
                    interview_session_id=session_id,
                    sequence_number=index,
                    speaker=speaker,
                    message_text=message_text,
                )
            )

        db.commit()

    return session_id


def create_incomplete_interview_for_report(api_environment):
    """Create an interview that has completed only two main questions."""

    session_id = str(uuid.uuid4())

    with api_environment["session_factory"]() as db:
        session = InterviewSessionRecord(
            id=session_id,
            room_name=f"incomplete-report-room-{uuid.uuid4()}",
            candidate_id=api_environment["candidate_id"],
            resume_id=api_environment["resume_id"],
            role_id="generative_ai_engineer",
            status="in_progress",
            current_stage="main_questions",
            current_main_question_id="question-003",

            used_main_question_ids=[
                "question-001",
                "question-002",
            ],

            follow_up_count=0,

            completed_question_ids=[
                "question-001",
                "question-002",
            ],

            completed_stages=[
                "introduction",
            ],

            structured_memory={
                "technical_interview": {
                    "stage_complete": False,

                    "completed_main_question_ids": [
                        "question-001",
                        "question-002",
                    ],
                },
            },
        )

        db.add(session)
        db.commit()

    return session_id


# =========================================================
# MILESTONE 2.6 — EVALUATION CONFIGURATION
# =========================================================

def configure_fake_evaluation(api_environment, monkeypatch):
    """
    Inject a fake LLM provider and deterministic role lookup.

    This prevents API tests from accessing external LLM services
    or requiring the role-question-bank database.
    """

    provider = FakeEvaluationProvider()

    api_environment["app"].state.llm_provider = provider

    monkeypatch.setattr(
        evaluation_report_service,
        "_role_details",
        lambda role_id: {
            "id": str(role_id),
            "name": "Generative AI Engineer",
            "details": (
                "Develop generative AI and retrieval applications."
            ),
            "technologies": [
                "Python",
                "FastAPI",
                "LLMs",
                "Vector Databases",
            ],
        },
    )

    return provider


# =========================================================
# MILESTONE 2.6 — REPORT GENERATION
# =========================================================

def test_generate_report_returns_two_independent_scores(
    api_environment,
    monkeypatch,
):
    provider = configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["interview_session_id"] == session_id
    assert data["resume_id"] == api_environment["resume_id"]
    assert data["role_id"] == "generative_ai_engineer"

    assert data["completion_status"] == "completed"

    assert data["resume_score"] == 8.1
    assert data["interview_score"] == 7.6

    assert data["resume_score"] != data["interview_score"]

    assert data["resume_report"]["score"] == 8.1
    assert data["interview_report"]["score"] == 7.6

    assert len(provider.calls) == 2


def test_generate_report_persists_report_in_database(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 200

    report_id = response.json()["id"]

    with api_environment["session_factory"]() as db:
        saved = db.query(EvaluationReport).filter_by(
            id=report_id
        ).one()

        assert saved.candidate_id == api_environment["candidate_id"]
        assert saved.interview_session_id == session_id
        assert saved.resume_id == api_environment["resume_id"]

        assert saved.resume_score == 8.1
        assert saved.interview_score == 7.6


def test_generate_report_includes_answer_feedback(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 200

    feedback = response.json()["interview_report"][
        "answer_by_answer_feedback"
    ]

    assert len(feedback) == 3

    assert feedback[0]["correctness"] == "partially_correct"
    assert feedback[1]["correctness"] == "technically_correct"
    assert feedback[2]["correctness"] == "insufficient_evidence"


# =========================================================
# MILESTONE 2.6 — REPORT RETRIEVAL
# =========================================================

def test_get_report_returns_existing_candidate_report(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    generate_response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert generate_response.status_code == 200

    response = api_environment["client"].get(
        f"/api/interview-sessions/{session_id}/report"
    )

    assert response.status_code == 200

    assert (
        response.json()["interview_session_id"]
        == session_id
    )

    assert response.json()["resume_score"] == 8.1
    assert response.json()["interview_score"] == 7.6


def test_get_report_returns_404_before_generation(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    response = api_environment["client"].get(
        f"/api/interview-sessions/{session_id}/report"
    )

    assert response.status_code == 404


# =========================================================
# MILESTONE 2.6 — CANDIDATE OWNERSHIP
# =========================================================

def test_candidate_cannot_retrieve_another_candidates_report(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    generate_response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert generate_response.status_code == 200

    api_environment["client"].headers["Authorization"] = (
        f"Bearer {api_environment['other_token']}"
    )

    response = api_environment["client"].get(
        f"/api/interview-sessions/{session_id}/report"
    )

    assert response.status_code == 404


def test_candidate_cannot_generate_another_candidates_report(
    api_environment,
    monkeypatch,
):
    provider = configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    api_environment["client"].headers["Authorization"] = (
        f"Bearer {api_environment['other_token']}"
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 404

    # Ownership is checked before any LLM evaluation call.
    assert provider.calls == []


def test_report_endpoints_require_guest_authentication(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    api_environment["client"].headers.pop("Authorization")

    get_response = api_environment["client"].get(
        f"/api/interview-sessions/{session_id}/report"
    )

    generate_response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert get_response.status_code == 401
    assert generate_response.status_code == 401


# =========================================================
# MILESTONE 2.6 — INCOMPLETE INTERVIEW PROTECTION
# =========================================================

def test_incomplete_interview_cannot_generate_report(
    api_environment,
    monkeypatch,
):
    provider = configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_incomplete_interview_for_report(
        api_environment
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 409

    # The incomplete interview must not be sent for evaluation.
    assert provider.calls == []

    with api_environment["session_factory"]() as db:
        report_count = db.query(EvaluationReport).filter_by(
            interview_session_id=session_id
        ).count()

        assert report_count == 0


# =========================================================
# MILESTONE 2.6 — REPORT RESPONSE PRIVACY
# =========================================================

def test_report_response_does_not_expose_raw_resume_or_internal_data(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 200

    data = response.json()

    assert "raw_text" not in data
    assert "structured_data" not in data
    assert "raw_resume_text" not in data
    assert "prompt" not in data
    assert "system_prompt" not in data
    assert "structured_memory" not in data

    serialized = str(data).lower()

    assert "private candidate resume text" not in serialized
    assert "candidate-test-token" not in serialized


def test_report_response_contains_only_candidate_facing_sections(
    api_environment,
    monkeypatch,
):
    configure_fake_evaluation(
        api_environment,
        monkeypatch,
    )

    session_id = create_completed_interview_for_report(
        api_environment
    )

    response = api_environment["client"].post(
        f"/api/interview-sessions/{session_id}/report/generate"
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "id",
        "interview_session_id",
        "resume_id",
        "role_id",
        "completion_status",
        "resume_score",
        "interview_score",
        "resume_report",
        "interview_report",
        "created_at",
    }