import hashlib
import secrets
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.database.resume_models import GuestCandidate


def hash_access_token(token: str) -> str:
    """Return the SHA-256 hash of a guest access token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_guest_candidate(db: Session) -> tuple[GuestCandidate, str]:
    """
    Create a guest candidate.

    Returns:
        A tuple containing the database candidate and the raw access token.
    """

    access_token = secrets.token_urlsafe(32)

    candidate = GuestCandidate(
        id=str(uuid4()),
        token_hash=hash_access_token(access_token),
    )

    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    # The raw token is returned only once and is not stored in the DB.
    return candidate, access_token


def get_candidate_from_token(
    db: Session,
    access_token: str,
) -> GuestCandidate | None:
    """Resolve a candidate using the hash of their access token."""

    token_hash = hash_access_token(access_token)

    return (
        db.query(GuestCandidate)
        .filter(GuestCandidate.token_hash == token_hash)
        .one_or_none()
    )