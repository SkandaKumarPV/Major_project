
import io
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database.resume_database import ResumeBase
from backend.app.database.resume_models import GuestCandidate
from backend.app.services import resume_storage_service as storage
from backend.app.services.guest_identity_service import hash_access_token
from backend.app.services.resume_extraction_service import DOCX_MIME_TYPE


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    ResumeBase.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()

    monkeypatch.setattr(
        storage,
        "PRIVATE_RESUME_DIRECTORY",
        tmp_path / "private" / "resumes",
    )

    candidate = GuestCandidate(
        id=str(uuid4()),
        token_hash=hash_access_token("test-token"),
    )

    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    yield db, candidate.id

    db.close()
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


def test_save_resume_to_private_storage(db_session):
    db, candidate_id = db_session
    file_bytes = create_docx_bytes()

    resume = storage.save_resume(
        db,
        candidate_id,
        file_bytes,
        "my_resume.docx",
        DOCX_MIME_TYPE,
    )

    file_path = storage.get_private_file_path(resume.storage_key)

    assert file_path.exists()
    assert file_path.read_bytes() == file_bytes
    assert resume.original_filename == "my_resume.docx"
    assert resume.raw_text
    assert resume.structured_data["skills"] == ["Python"]

    assert str(file_path).find("private") != -1


def test_storage_uses_uuid_filename(db_session):
    db, candidate_id = db_session

    resume = storage.save_resume(
        db,
        candidate_id,
        create_docx_bytes(),
        "resume.docx",
        DOCX_MIME_TYPE,
    )

    assert resume.storage_key != "resume.docx"
    assert len(resume.storage_key) == 36


def test_candidate_cannot_retrieve_another_candidates_resume(db_session):
    db, candidate_id = db_session

    storage.save_resume(
        db,
        candidate_id,
        create_docx_bytes(),
        "resume.docx",
        DOCX_MIME_TYPE,
    )

    another_candidate_id = str(uuid4())

    assert storage.get_owned_resume(
        db,
        another_candidate_id,
    ) is None

    assert storage.retrieve_original_resume(
        db,
        another_candidate_id,
    ) is None


def test_retrieve_original_resume(db_session):
    db, candidate_id = db_session
    file_bytes = create_docx_bytes()

    storage.save_resume(
        db,
        candidate_id,
        file_bytes,
        "resume.docx",
        DOCX_MIME_TYPE,
    )

    retrieved = storage.retrieve_original_resume(
        db,
        candidate_id,
    )

    assert retrieved == file_bytes


def test_replace_resume_preserves_one_database_record(db_session):
    db, candidate_id = db_session

    original = storage.save_resume(
        db,
        candidate_id,
        create_docx_bytes(),
        "first.docx",
        DOCX_MIME_TYPE,
    )

    old_path = storage.get_private_file_path(original.storage_key)

    replacement = storage.replace_resume(
        db,
        candidate_id,
        create_docx_bytes(),
        "replacement.docx",
        DOCX_MIME_TYPE,
    )

    assert replacement.id == original.id
    assert replacement.original_filename == "replacement.docx"
    assert not old_path.exists()

    records = db.query(storage.CandidateResume).filter_by(
        candidate_id=candidate_id
    ).all()

    assert len(records) == 1


def test_delete_resume_removes_file_and_database_record(db_session):
    db, candidate_id = db_session

    resume = storage.save_resume(
        db,
        candidate_id,
        create_docx_bytes(),
        "resume.docx",
        DOCX_MIME_TYPE,
    )

    file_path = storage.get_private_file_path(resume.storage_key)

    assert storage.delete_resume(db, candidate_id) is True
    assert not file_path.exists()
    assert storage.get_owned_resume(db, candidate_id) is None


def test_delete_missing_resume_returns_false(db_session):
    db, candidate_id = db_session

    assert storage.delete_resume(db, candidate_id) is False


def test_invalid_storage_key_is_rejected(db_session):
    with pytest.raises(storage.ResumeStorageError):
        storage.get_private_file_path("../../outside.txt")
