
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.guest import get_resume_db
from backend.app.api.interview_sessions import router
from backend.app.database.resume_models import (
    CandidateResume,
    GuestCandidate,
    InterviewSessionRecord,
)
from backend.app.database.resume_database import ResumeBase
from backend.app.services.guest_identity_service import hash_access_token
from backend.app.services.interview_session_service import (
    append_transcript_message,
)


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

        db.add_all([candidate, other_candidate])
        db.flush()

        resume = CandidateResume(
            id=str(uuid.uuid4()),
            candidate_id=candidate.id,
            storage_key=str(uuid.uuid4()),
            original_filename="candidate.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            raw_text="Private candidate resume text",
            structured_data={"name": "Candidate"},
        )

        other_resume = CandidateResume(
            id=str(uuid.uuid4()),
            candidate_id=other_candidate.id,
            storage_key=str(uuid.uuid4()),
            original_filename="other.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            raw_text="Other candidate resume text",
            structured_data={"name": "Other"},
        )

        db.add_all([resume, other_resume])
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
        "Authorization": f"Bearer {candidate_token}"
    })

    yield {
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
        json={"role_id": "generative_ai_engineer"},
    )

    assert response.status_code == 422


def test_create_session_rejects_another_candidates_resume(api_environment):
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

    response = client.get(f"/api/interview-sessions/{session_id}")

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
        data["room_name"]
    ]


def test_dispatch_rejects_another_candidates_session(api_environment):
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
    assert [item["sequence_number"] for item in response.json()] == [1, 2]
    assert response.json()[0]["speaker"] == "interviewer"
    assert response.json()[1]["speaker"] == "candidate"


def test_end_session_deletes_room_and_persists_ended_status(
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
    assert api_environment["livekit"].ended_rooms == [data["room_name"]]

    with api_environment["session_factory"]() as db:
        saved = db.query(InterviewSessionRecord).filter_by(
            id=data["id"]
        ).one()

        assert saved.status == "ended"
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
