from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.app.database.resume_database import get_resume_db
from backend.app.database.resume_models import GuestCandidate
from backend.app.services.guest_identity_service import (
    create_guest_candidate,
    get_candidate_from_token,
)


router = APIRouter(
    prefix="/api/guest",
    tags=["guest"],
)


class GuestIdentityResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GuestStatusResponse(BaseModel):
    authenticated: bool


def get_current_candidate(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_resume_db),
) -> GuestCandidate:
    """Authenticate a guest using an Authorization Bearer token."""

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = parts[1]

    candidate = get_candidate_from_token(db, access_token)

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unknown guest access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return candidate


@router.post(
    "",
    response_model=GuestIdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_guest(
    db: Session = Depends(get_resume_db),
):
    """Create a new guest candidate identity."""

    _, access_token = create_guest_candidate(db)

    return GuestIdentityResponse(
        access_token=access_token,
    )


@router.get(
    "/me",
    response_model=GuestStatusResponse,
)
def get_guest_status(
    candidate: GuestCandidate = Depends(get_current_candidate),
):
    """Verify the guest's access token without exposing resume data."""

    return GuestStatusResponse(
        authenticated=True,
    )