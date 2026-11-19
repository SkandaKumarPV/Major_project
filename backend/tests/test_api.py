
import pytest
from fastapi.testclient import TestClient

import backend.app.api.app as api_module


class FakeLiveKitService:
    def __init__(self):
        self.closed = False
        self.create_error = None
        self.dispatch_error = None
        self.end_error = None

        self.agent_name = "simple-ai-interviewer"
        self.dispatched_rooms = []
        self.ended_rooms = []

    async def create_session(self):
        if self.create_error:
            raise self.create_error

        return {
            "livekit_url": "wss://test.livekit.cloud",
            "room_name": "interview-test-room",
            "participant_identity": "candidate-test",
            "token": "test-candidate-token",
        }

    async def dispatch_agent(self, room_name):
        if self.dispatch_error:
            raise self.dispatch_error

        if not room_name.startswith("interview-"):
            raise ValueError("Invalid interview room name")

        self.dispatched_rooms.append(room_name)
        return True

    async def end_session(self, room_name):
        if self.end_error:
            raise self.end_error

        if not room_name.startswith("interview-"):
            raise ValueError("Invalid interview room name")

        self.ended_rooms.append(room_name)

    async def close(self):
        self.closed = True


@pytest.fixture
def api_client(monkeypatch):
    service = FakeLiveKitService()

    monkeypatch.setattr(
        api_module.Settings,
        "from_environment",
        classmethod(lambda cls: object()),
    )

    monkeypatch.setattr(
        api_module,
        "LiveKitService",
        lambda settings: service,
    )

    with TestClient(api_module.app) as client:
        yield client, service


def test_health_endpoint(api_client):
    client, _ = api_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_interview_returns_candidate_connection(api_client):
    client, _ = api_client

    response = client.post("/api/interviews")

    assert response.status_code == 201

    data = response.json()

    assert data["livekit_url"] == "wss://test.livekit.cloud"
    assert data["room_name"] == "interview-test-room"
    assert data["participant_identity"] == "candidate-test"
    assert data["token"] == "test-candidate-token"


def test_dispatch_interviewer_to_candidate_room(api_client):
    client, service = api_client

    response = client.post(
        "/api/interviews/interview-test-room/dispatch"
    )

    assert response.status_code == 202
    assert response.json() == {
        "room_name": "interview-test-room",
        "agent_name": "simple-ai-interviewer",
        "dispatched": True,
    }

    assert service.dispatched_rooms == ["interview-test-room"]


def test_dispatch_interviewer_rejects_invalid_room(api_client):
    client, service = api_client

    response = client.post(
        "/api/interviews/other-room/dispatch"
    )

    assert response.status_code == 400
    assert service.dispatched_rooms == []


def test_dispatch_interviewer_handles_livekit_failure(api_client):
    client, service = api_client

    service.dispatch_error = RuntimeError(
        "Simulated dispatch failure"
    )

    response = client.post(
        "/api/interviews/interview-test-room/dispatch"
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Unable to dispatch the interviewer."
    )


def test_end_interview_deletes_the_requested_room(api_client):
    client, service = api_client

    response = client.delete(
        "/api/interviews/interview-test-room"
    )

    assert response.status_code == 204
    assert service.ended_rooms == ["interview-test-room"]


def test_end_interview_rejects_invalid_room_name(api_client):
    client, service = api_client

    response = client.delete("/api/interviews/other-room")

    assert response.status_code == 400
    assert service.ended_rooms == []


def test_create_interview_handles_livekit_failure(api_client):
    client, service = api_client

    service.create_error = RuntimeError(
        "Simulated LiveKit failure"
    )

    response = client.post("/api/interviews")

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Unable to create the LiveKit interview session."
    )


def test_api_closes_service_on_shutdown(monkeypatch):
    service = FakeLiveKitService()

    monkeypatch.setattr(
        api_module.Settings,
        "from_environment",
        classmethod(lambda cls: object()),
    )

    monkeypatch.setattr(
        api_module,
        "LiveKitService",
        lambda settings: service,
    )

    with TestClient(api_module.app):
        assert service.closed is False

    assert service.closed is True
