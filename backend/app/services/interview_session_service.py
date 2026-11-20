
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.database.resume_models import (
    CandidateResume,
    GuestCandidate,
    InterviewSessionRecord,
    InterviewTranscriptMessage,
)


CREATED_STATUS = "created"
ACTIVE_STATUS = "in_progress"
ENDED_STATUS = "ended"

ALLOWED_SPEAKERS = {
    "candidate",
    "interviewer",
    "assistant",
    "system",
}


class InterviewSessionError(Exception):
    """Base exception for interview-session operations."""


class InterviewSessionNotFoundError(InterviewSessionError):
    """Raised when a session does not exist or is not owned by the caller."""


class InterviewSessionValidationError(InterviewSessionError):
    """Raised when session data or a requested transition is invalid."""


def _utc_now():
    return datetime.now(timezone.utc)


def create_interview_session(
    db: Session,
    *,
    candidate_id: str,
    room_name: str,
    role_id: str,
    resume_id: str,
) -> InterviewSessionRecord:
    """Create an interview session. A candidate-owned resume is mandatory."""

    if not candidate_id or not room_name or not role_id:
        raise InterviewSessionValidationError(
            "Candidate, LiveKit room and role are required."
        )

    if not isinstance(resume_id, str) or not resume_id.strip():
        raise InterviewSessionValidationError(
            "A resume must be selected before starting an interview."
        )

    candidate = db.query(GuestCandidate).filter(
        GuestCandidate.id == candidate_id
    ).first()

    if candidate is None:
        raise InterviewSessionValidationError(
            "The candidate does not exist."
        )

    resume = db.query(CandidateResume).filter(
        CandidateResume.id == resume_id,
        CandidateResume.candidate_id == candidate_id,
    ).first()

    if resume is None:
        raise InterviewSessionValidationError(
            "The selected resume does not exist or does not belong "
            "to this candidate."
        )

    existing_room = db.query(InterviewSessionRecord).filter(
        InterviewSessionRecord.room_name == room_name
    ).first()

    if existing_room is not None:
        raise InterviewSessionValidationError(
            "This LiveKit room is already linked to an interview."
        )

    session = InterviewSessionRecord(
        id=str(uuid4()),
        room_name=room_name,
        candidate_id=candidate_id,
        resume_id=resume_id,
        role_id=role_id,
        status=CREATED_STATUS,
        current_stage="not_started",
        current_main_question_id=None,
        used_main_question_ids=[],
        follow_up_count=0,
        completed_question_ids=[],
        completed_stages=[],
        structured_memory={},
    )

    try:
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    except Exception:
        db.rollback()
        raise


def get_owned_interview_session(
    db: Session,
    *,
    session_id: str,
    candidate_id: str,
) -> InterviewSessionRecord:
    """Return a session only if it belongs to the authenticated candidate."""

    session = db.query(InterviewSessionRecord).filter(
        InterviewSessionRecord.id == session_id,
        InterviewSessionRecord.candidate_id == candidate_id,
    ).first()

    if session is None:
        raise InterviewSessionNotFoundError("Interview session not found.")

    return session


def list_candidate_interview_sessions(
    db: Session,
    *,
    candidate_id: str,
) -> list[InterviewSessionRecord]:
    """List the candidate's sessions, newest first."""

    return (
        db.query(InterviewSessionRecord)
        .filter(InterviewSessionRecord.candidate_id == candidate_id)
        .order_by(InterviewSessionRecord.created_at.desc())
        .all()
    )


def mark_interview_started(
    db: Session,
    *,
    session_id: str,
    candidate_id: str,
) -> InterviewSessionRecord:
    """Start a created session. Repeated calls do not reset its timestamp."""

    session = get_owned_interview_session(
        db,
        session_id=session_id,
        candidate_id=candidate_id,
    )

    if session.status == ENDED_STATUS:
        raise InterviewSessionValidationError(
            "An ended interview cannot be restarted."
        )

    if session.status == CREATED_STATUS:
        session.status = ACTIVE_STATUS
        session.started_at = _utc_now()

        try:
            db.commit()
            db.refresh(session)
        except Exception:
            db.rollback()
            raise

    return session


def update_interview_progress(
    db: Session,
    *,
    session_id: str,
    candidate_id: str,
    current_stage: str | None = None,
    current_main_question_id: str | None = None,
    used_main_question_ids: list[str] | None = None,
    follow_up_count: int | None = None,
    completed_question_ids: list[str] | None = None,
    completed_stages: list[str] | None = None,
    structured_memory: dict | None = None,
) -> InterviewSessionRecord:
    """Update only explicitly supplied progress fields."""

    session = get_owned_interview_session(
        db,
        session_id=session_id,
        candidate_id=candidate_id,
    )

    if session.status == ENDED_STATUS:
        raise InterviewSessionValidationError(
            "An ended interview cannot be modified."
        )

    if follow_up_count is not None and follow_up_count < 0:
        raise InterviewSessionValidationError(
            "Follow-up count cannot be negative."
        )

    list_fields = {
        "used_main_question_ids": used_main_question_ids,
        "completed_question_ids": completed_question_ids,
        "completed_stages": completed_stages,
    }

    for field_name, value in list_fields.items():
        if value is not None and (
            not isinstance(value, list)
            or not all(isinstance(item, str) for item in value)
        ):
            raise InterviewSessionValidationError(
                f"{field_name} must be a list of strings."
            )

    if structured_memory is not None and not isinstance(
        structured_memory, dict
    ):
        raise InterviewSessionValidationError(
            "Structured memory must be an object."
        )

    if current_stage is not None:
        session.current_stage = current_stage

    if current_main_question_id is not None:
        session.current_main_question_id = current_main_question_id

    if used_main_question_ids is not None:
        session.used_main_question_ids = list(used_main_question_ids)

    if follow_up_count is not None:
        session.follow_up_count = follow_up_count

    if completed_question_ids is not None:
        session.completed_question_ids = list(completed_question_ids)

    if completed_stages is not None:
        session.completed_stages = list(completed_stages)

    if structured_memory is not None:
        session.structured_memory = deepcopy(structured_memory)

    try:
        db.commit()
        db.refresh(session)
        return session
    except Exception:
        db.rollback()
        raise


def append_transcript_message(
    db: Session,
    *,
    session_id: str,
    candidate_id: str,
    speaker: str,
    message_text: str,
) -> InterviewTranscriptMessage:
    """Append a transcript entry with a session-local sequence number."""

    session = get_owned_interview_session(
        db,
        session_id=session_id,
        candidate_id=candidate_id,
    )

    if session.status == ENDED_STATUS:
        raise InterviewSessionValidationError(
            "Cannot append transcript to an ended interview."
        )

    normalized_speaker = speaker.strip().lower()

    if normalized_speaker not in ALLOWED_SPEAKERS:
        raise InterviewSessionValidationError(
            "Unsupported transcript speaker."
        )

    if not isinstance(message_text, str) or not message_text.strip():
        raise InterviewSessionValidationError(
            "Transcript message cannot be empty."
        )

    current_max = db.query(
        func.max(InterviewTranscriptMessage.sequence_number)
    ).filter(
        InterviewTranscriptMessage.interview_session_id == session_id
    ).scalar()

    message = InterviewTranscriptMessage(
        id=str(uuid4()),
        interview_session_id=session_id,
        sequence_number=(current_max or 0) + 1,
        speaker=normalized_speaker,
        message_text=message_text.strip(),
    )

    try:
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise


def get_interview_transcript(
    db: Session,
    *,
    session_id: str,
    candidate_id: str,
) -> list[InterviewTranscriptMessage]:
    """Return the complete transcript in its original sequence."""

    get_owned_interview_session(
        db,
        session_id=session_id,
        candidate_id=candidate_id,
    )

    return (
        db.query(InterviewTranscriptMessage)
        .filter(
            InterviewTranscriptMessage.interview_session_id == session_id
        )
        .order_by(InterviewTranscriptMessage.sequence_number.asc())
        .all()
    )


def end_interview_session(
    db: Session,
    *,
    session_id: str,
    candidate_id: str,
) -> InterviewSessionRecord:
    """End a session. Repeated calls preserve the original end timestamp."""

    session = get_owned_interview_session(
        db,
        session_id=session_id,
        candidate_id=candidate_id,
    )

    if session.status != ENDED_STATUS:
        session.status = ENDED_STATUS
        session.ended_at = _utc_now()

        try:
            db.commit()
            db.refresh(session)
        except Exception:
            db.rollback()
            raise

    return session
