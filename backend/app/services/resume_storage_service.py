
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.database.resume_models import (
    CandidateResume,
)
from backend.app.services.resume_extraction_service import (
    extract_resume,
    DEFAULT_MAX_RESUME_SIZE_BYTES,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]

PRIVATE_RESUME_DIRECTORY = (
    BACKEND_DIR / "private_storage" / "resumes"
)


class ResumeStorageError(Exception):
    """Raised when private resume storage operations fail."""


def ensure_private_storage():
    PRIVATE_RESUME_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )


def get_private_file_path(storage_key: str) -> Path:
    """
    Resolve a storage key without allowing arbitrary paths.
    """

    try:
        parsed_id = str(uuid4())  # only used to validate UUID format
        del parsed_id

        from uuid import UUID
        UUID(storage_key)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ResumeStorageError("Invalid resume storage key.") from exc

    path = (PRIVATE_RESUME_DIRECTORY / storage_key).resolve()
    root = PRIVATE_RESUME_DIRECTORY.resolve()

    if path.parent != root:
        raise ResumeStorageError("Invalid resume storage location.")

    return path


def save_resume(
    db: Session,
    candidate_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    max_size_bytes: int = DEFAULT_MAX_RESUME_SIZE_BYTES,
) -> CandidateResume:
    """
    Validate, extract and privately store a candidate resume.
    """

    extracted = extract_resume(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        max_size_bytes=max_size_bytes,
    )

    ensure_private_storage()

    resume_id = str(uuid4())
    storage_key = str(uuid4())

    file_path = get_private_file_path(storage_key)

    resume = CandidateResume(
        id=resume_id,
        candidate_id=candidate_id,
        storage_key=storage_key,
        original_filename=Path(filename).name,
        mime_type=content_type,
        size_bytes=len(file_bytes),
        raw_text=extracted.raw_text,
        structured_data=extracted.structured_data,
    )

    try:
        file_path.write_bytes(file_bytes)
        db.add(resume)
        db.commit()
        db.refresh(resume)
        return resume

    except Exception:
        db.rollback()

        if file_path.exists():
            file_path.unlink()

        raise


def get_owned_resume(
    db: Session,
    candidate_id: str,
) -> CandidateResume | None:
    """
    Return the resume belonging to this candidate only.
    """

    return (
        db.query(CandidateResume)
        .filter(CandidateResume.candidate_id == candidate_id)
        .order_by(CandidateResume.created_at.desc())
        .first()
    )


def retrieve_original_resume(
    db: Session,
    candidate_id: str,
) -> bytes | None:
    """
    Retrieve original file bytes for backend use only.
    """

    resume = get_owned_resume(db, candidate_id)

    if resume is None:
        return None

    file_path = get_private_file_path(resume.storage_key)

    if not file_path.is_file():
        raise ResumeStorageError("Stored resume file is missing.")

    return file_path.read_bytes()


def delete_resume(
    db: Session,
    candidate_id: str,
) -> bool:
    """
    Delete only the requesting candidate's resume.
    """

    resume = get_owned_resume(db, candidate_id)

    if resume is None:
        return False

    file_path = get_private_file_path(resume.storage_key)

    try:
        if file_path.exists():
            file_path.unlink()

        db.delete(resume)
        db.commit()
        return True

    except Exception:
        db.rollback()
        raise


def replace_resume(
    db: Session,
    candidate_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    max_size_bytes: int = DEFAULT_MAX_RESUME_SIZE_BYTES,
) -> CandidateResume:
    """
    Replace the candidate's existing resume.
    """

    existing = get_owned_resume(db, candidate_id)

    new_extracted = extract_resume(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        max_size_bytes=max_size_bytes,
    )

    ensure_private_storage()

    new_storage_key = str(uuid4())
    new_file_path = get_private_file_path(new_storage_key)

    new_resume_id = str(uuid4())

    new_resume = CandidateResume(
        id=new_resume_id,
        candidate_id=candidate_id,
        storage_key=new_storage_key,
        original_filename=Path(filename).name,
        mime_type=content_type,
        size_bytes=len(file_bytes),
        raw_text=new_extracted.raw_text,
        structured_data=new_extracted.structured_data,
    )

    old_file_path = (
        get_private_file_path(existing.storage_key)
        if existing is not None
        else None
    )

    try:
        new_file_path.write_bytes(file_bytes)

        if existing is not None:
            existing.storage_key = new_storage_key
            existing.original_filename = Path(filename).name
            existing.mime_type = content_type
            existing.size_bytes = len(file_bytes)
            existing.raw_text = new_extracted.raw_text
            existing.structured_data = new_extracted.structured_data
        else:
            db.add(new_resume)

        db.commit()

        if existing is not None:
            db.refresh(existing)
            result = existing
        else:
            db.refresh(new_resume)
            result = new_resume

        if old_file_path is not None and old_file_path.exists():
            old_file_path.unlink()

        return result

    except Exception:
        db.rollback()

        if new_file_path.exists():
            new_file_path.unlink()

        raise
