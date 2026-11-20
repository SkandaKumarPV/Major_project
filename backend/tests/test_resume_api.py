
import io
from uuid import uuid4

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.guest import get_current_candidate
from backend.app.api.resumes import router
from backend.app.database.resume_database import get_resume_db, ResumeBase
from backend.app.database.resume_models import GuestCandidate
from backend.app.services.guest_identity_service import hash_access_token
from backend.app.services import resume_storage_service as storage
from backend.app.services.resume_extraction_service import DOCX_MIME_TYPE


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    ResumeBase.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()

    token = "test-guest-token"
    candidate = GuestCandidate(
        id=str(uuid4()),
        token_hash=hash_access_token(token),
    )
    db.add(candidate)
    db.commit()
    db.close()

    monkeypatch.setattr(
        storage,
        "PRIVATE_RESUME_DIRECTORY",
        tmp_path / "private" / "resumes",
    )

    app = FastAPI()
    app.include_router(router)

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_resume_db] = override_db

    test_client = TestClient(app)
    test_client.headers.update({
        "Authorization": f"Bearer {token}",
    })

    yield test_client

    test_client.close()
    engine.dispose()


def create_docx_bytes():
    document = Document()
    document.add_paragraph("Name: Alex Kumar")
    document.add_paragraph("alex@example.com")
    document.add_heading("Technical Skills", level=1)
    document.add_paragraph("Python")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload_file(client, filename="resume.docx", content=None):
    return client.post(
        "/api/resumes",
        files={
            "file": (
                filename,
                content if content is not None else create_docx_bytes(),
                DOCX_MIME_TYPE,
            )
        },
    )


def test_resume_status_without_upload(client):
    response = client.get("/api/resumes/me")

    assert response.status_code == 200
    assert response.json() == {
        "uploaded": False,
        "filename": None,
        "status": "missing",
    }


def test_upload_resume_returns_only_public_metadata(client):
    response = upload_file(client)

    assert response.status_code == 201

    data = response.json()

    assert data == {
        "uploaded": True,
        "filename": "resume.docx",
        "status": "uploaded",
    }

    response_text = response.text.lower()

    assert "raw_text" not in response_text
    assert "structured_data" not in response_text
    assert "storage_key" not in response_text
    assert "candidate_id" not in response_text
    assert "alex@example.com" not in response_text


def test_candidate_cannot_upload_second_resume_without_replacing(client):
    first = upload_file(client, "first.docx")
    second = upload_file(client, "second.docx")

    assert first.status_code == 201
    assert second.status_code == 409


def test_replace_resume(client):
    first = upload_file(client, "first.docx")
    assert first.status_code == 201

    response = client.put(
        "/api/resumes/me",
        files={
            "file": (
                "replacement.docx",
                create_docx_bytes(),
                DOCX_MIME_TYPE,
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "replacement.docx"

    status_response = client.get("/api/resumes/me")
    assert status_response.json()["filename"] == "replacement.docx"


def test_delete_resume(client):
    upload_response = upload_file(client)
    assert upload_response.status_code == 201

    delete_response = client.delete("/api/resumes/me")
    assert delete_response.status_code == 204

    status_response = client.get("/api/resumes/me")

    assert status_response.status_code == 200
    assert status_response.json()["uploaded"] is False


def test_invalid_resume_is_rejected(client):
    response = client.post(
        "/api/resumes",
        files={
            "file": (
                "resume.pdf",
                b"not-a-pdf",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400


def test_oversized_resume_is_rejected(client):
    from backend.app.services.resume_extraction_service import (
        DEFAULT_MAX_RESUME_SIZE_BYTES,
    )

    response = client.post(
        "/api/resumes",
        files={
            "file": (
                "resume.docx",
                b"x" * (DEFAULT_MAX_RESUME_SIZE_BYTES + 1),
                DOCX_MIME_TYPE,
            )
        },
    )

    assert response.status_code == 413


def test_resume_api_requires_guest_authentication():
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.get("/api/resumes/me")

    assert response.status_code == 401
