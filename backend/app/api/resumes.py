from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.guest import get_current_candidate
from backend.app.database.resume_database import get_resume_db
from backend.app.database.resume_models import GuestCandidate
from backend.app.services.resume_extraction_service import (
    DEFAULT_MAX_RESUME_SIZE_BYTES,
    ResumeExtractionError,
)
from backend.app.services import resume_storage_service as storage


router = APIRouter(prefix="/api/resumes", tags=["resumes"])


class ResumeStatusResponse(BaseModel):
    uploaded: bool
    filename: str | None = None
    status: str


def process_upload_error(exc: Exception):
    if isinstance(exc, ResumeExtractionError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to process the resume.",
    ) from exc


async def read_resume_upload(file: UploadFile) -> bytes:
    content = await file.read(DEFAULT_MAX_RESUME_SIZE_BYTES + 1)

    if len(content) > DEFAULT_MAX_RESUME_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The resume exceeds the maximum allowed file size.",
        )

    return content


@router.post("", response_model=ResumeStatusResponse,
             status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    if storage.get_owned_resume(db, candidate.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A resume already exists. Use the replace endpoint.",
        )

    file_bytes = await read_resume_upload(file)

    try:
        resume = storage.save_resume(
            db=db,
            candidate_id=candidate.id,
            file_bytes=file_bytes,
            filename=file.filename or "",
            content_type=file.content_type or "",
        )
    except ResumeExtractionError as exc:
        process_upload_error(exc)
    except Exception as exc:
        process_upload_error(exc)

    return ResumeStatusResponse(
        uploaded=True,
        filename=resume.original_filename,
        status="uploaded",
    )


@router.get("/me", response_model=ResumeStatusResponse)
def get_resume_status(
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    resume = storage.get_owned_resume(db, candidate.id)

    if resume is None:
        return ResumeStatusResponse(
            uploaded=False,
            filename=None,
            status="missing",
        )

    return ResumeStatusResponse(
        uploaded=True,
        filename=resume.original_filename,
        status="uploaded",
    )


@router.put("/me", response_model=ResumeStatusResponse)
async def replace_candidate_resume(
    file: UploadFile = File(...),
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    file_bytes = await read_resume_upload(file)

    try:
        resume = storage.replace_resume(
            db=db,
            candidate_id=candidate.id,
            file_bytes=file_bytes,
            filename=file.filename or "",
            content_type=file.content_type or "",
        )
    except ResumeExtractionError as exc:
        process_upload_error(exc)
    except Exception as exc:
        process_upload_error(exc)

    return ResumeStatusResponse(
        uploaded=True,
        filename=resume.original_filename,
        status="uploaded",
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def remove_candidate_resume(
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    storage.delete_resume(db, candidate.id)
    return None