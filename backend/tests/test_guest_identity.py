import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.api.guest import (
    get_resume_db,
    router,
)
from backend.app.database.resume_database import (
    create_resume_engine,
    initialize_resume_database,
)
from backend.app.database.resume_models import GuestCandidate
from backend.app.services.guest_identity_service import hash_access_token


@pytest.fixture
def guest_test_environment(tmp_path):
    database_path = tmp_path / "test_interview_data.db"
    engine = create_resume_engine(f"sqlite:///{database_path}")

    initialize_resume_database(target_engine=engine)

    test_app = FastAPI()
    test_app.include_router(router)

    def override_resume_db():
        with Session(engine) as db:
            yield db

    test_app.dependency_overrides[get_resume_db] = override_resume_db

    with TestClient(test_app) as client:
        yield client, engine

    test_app.dependency_overrides.clear()
    engine.dispose()


def test_create_guest_returns_access_token(guest_test_environment):
    client, engine = guest_test_environment

    response = client.post("/api/guest")

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) >= 32
    assert data["token_type"] == "bearer"

    with Session(engine) as db:
        candidates = db.query(GuestCandidate).all()

        assert len(candidates) == 1

        saved_candidate = candidates[0]

        assert saved_candidate.token_hash == hash_access_token(
            data["access_token"]
        )

        # The raw token must never be stored in the database.
        assert saved_candidate.token_hash != data["access_token"]


def test_guest_can_authenticate_with_valid_token(guest_test_environment):
    client, _ = guest_test_environment

    creation_response = client.post("/api/guest")
    token = creation_response.json()["access_token"]

    response = client.get(
        "/api/guest/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_guest_cannot_authenticate_without_token(guest_test_environment):
    client, _ = guest_test_environment

    response = client.get("/api/guest/me")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer invalid-token",
        "Token invalid-token",
        "Bearer",
        "invalid-token",
        "",
    ],
)
def test_guest_rejects_invalid_authorization(
    guest_test_environment,
    authorization,
):
    client, _ = guest_test_environment

    response = client.get(
        "/api/guest/me",
        headers={"Authorization": authorization},
    )

    assert response.status_code == 401


def test_guest_status_does_not_expose_private_identity_data(
    guest_test_environment,
):
    client, _ = guest_test_environment

    creation_response = client.post("/api/guest")
    token = creation_response.json()["access_token"]

    response = client.get(
        "/api/guest/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    # No candidate ID, resume information or token is exposed.
    assert response.json() == {"authenticated": True}