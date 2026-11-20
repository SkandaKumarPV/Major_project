
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app.api.guest import get_current_candidate
from backend.app.database.resume_database import get_resume_db
from backend.app.database.resume_models import (
    GuestCandidate,
    InterviewSessionRecord,
)
from backend.app.services.interview_session_service import (
    InterviewSessionNotFoundError,
    InterviewSessionValidationError,
    create_interview_session,
    end_interview_session,
    get_interview_transcript,
    get_owned_interview_session,
    list_candidate_interview_sessions,
    mark_interview_started,
)

logger = logging.getLogger("ai-interviewer-session-api")

router = APIRouter(
    prefix="/api/interview-sessions",
    tags=["interview-sessions"],
)


class CreateInterviewSessionRequest(BaseModel):
    role_id: str = Field(min_length=1)
    resume_id: str = Field(min_length=1)


class InterviewSessionResponse(BaseModel):
    id: str
    room_name: str
    role_id: str
    resume_id: str
    status: str
    current_stage: str | None
    current_main_question_id: str | None
    used_main_question_ids: list[str]
    follow_up_count: int
    completed_question_ids: list[str]
    completed_stages: list[str]
    created_at: object
    started_at: object | None
    ended_at: object | None

    model_config = ConfigDict(from_attributes=True)


class InterviewSessionCreatedResponse(InterviewSessionResponse):
    livekit_url: str
    participant_identity: str
    token: str


class TranscriptMessageResponse(BaseModel):
    id: str
    sequence_number: int
    speaker: str
    message_text: str
    created_at: object

    model_config = ConfigDict(from_attributes=True)


class DispatchInterviewResponse(BaseModel):
    session_id: str
    room_name: str
    agent_name: str
    dispatched: bool
    status: str


def _get_livekit_service(request: Request):
    service = getattr(request.app.state, "livekit_service", None)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit service is unavailable.",
        )

    return service


def _get_owned_session_or_404(
    db: Session,
    session_id: str,
    candidate_id: str,
) -> InterviewSessionRecord:
    try:
        return get_owned_interview_session(
            db,
            session_id=session_id,
            candidate_id=candidate_id,
        )
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found.",
        ) from exc


@router.post(
    "",
    response_model=InterviewSessionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate_interview_session(
    payload: CreateInterviewSessionRequest,
    request: Request,
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    """
    Explicitly create a new candidate-owned interview session.

    A resume belonging to the authenticated candidate is mandatory.
    """

    livekit = _get_livekit_service(request)

    try:
        connection = await livekit.create_session()
    except Exception as exc:
        logger.exception("LiveKit room creation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to create the LiveKit interview room.",
        ) from exc

    try:
        session = create_interview_session(
            db,
            candidate_id=candidate.id,
            room_name=connection["room_name"],
            role_id=payload.role_id,
            resume_id=payload.resume_id,
        )
    except InterviewSessionValidationError as exc:
        try:
            await livekit.end_session(connection["room_name"])
        except Exception:
            logger.exception(
                "Could not clean up LiveKit room after session validation failed"
            )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        try:
            await livekit.end_session(connection["room_name"])
        except Exception:
            logger.exception(
                "Could not clean up LiveKit room after database failure"
            )

        logger.exception("Persistent interview session creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the interview session.",
        ) from exc

    return InterviewSessionCreatedResponse(
        id=session.id,
        room_name=session.room_name,
        role_id=session.role_id,
        resume_id=session.resume_id,
        status=session.status,
        current_stage=session.current_stage,
        current_main_question_id=session.current_main_question_id,
        used_main_question_ids=session.used_main_question_ids or [],
        follow_up_count=session.follow_up_count,
        completed_question_ids=session.completed_question_ids or [],
        completed_stages=session.completed_stages or [],
        created_at=session.created_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        livekit_url=connection["livekit_url"],
        participant_identity=connection["participant_identity"],
        token=connection["token"],
    )


@router.get(
    "",
    response_model=list[InterviewSessionResponse],
)
def get_my_interview_sessions(
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    """Return only the authenticated candidate's interview history."""

    return list_candidate_interview_sessions(
        db,
        candidate_id=candidate.id,
    )


@router.get(
    "/{session_id}",
    response_model=InterviewSessionResponse,
)
def get_my_interview_session(
    session_id: str,
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    """Retrieve one interview session owned by the authenticated candidate."""

    return _get_owned_session_or_404(
        db,
        session_id,
        candidate.id,
    )


@router.post(
    "/{session_id}/dispatch",
    response_model=DispatchInterviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def dispatch_my_interviewer(
    session_id: str,
    request: Request,
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    """
    Dispatch the interviewer only to a room owned by this candidate.

    The session becomes active after successful dispatch.
    """

    session = _get_owned_session_or_404(
        db,
        session_id,
        candidate.id,
    )

    if session.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An ended interview cannot be dispatched.",
        )

    livekit = _get_livekit_service(request)

    try:
        dispatched = await livekit.dispatch_agent(session.room_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Interviewer dispatch failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to dispatch the interviewer.",
        ) from exc

    try:
        session = mark_interview_started(
            db,
            session_id=session.id,
            candidate_id=candidate.id,
        )
    except InterviewSessionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return DispatchInterviewResponse(
        session_id=session.id,
        room_name=session.room_name,
        agent_name=livekit.agent_name,
        dispatched=dispatched,
        status=session.status,
    )


@router.get(
    "/{session_id}/transcript",
    response_model=list[TranscriptMessageResponse],
)
def get_my_interview_transcript(
    session_id: str,
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    """Return the ordered transcript for the candidate's own session."""

    try:
        return get_interview_transcript(
            db,
            session_id=session_id,
            candidate_id=candidate.id,
        )
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found.",
        ) from exc


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def end_my_interview_session(
    session_id: str,
    request: Request,
    candidate: GuestCandidate = Depends(get_current_candidate),
    db: Session = Depends(get_resume_db),
):
    """End only the interview session owned by the authenticated candidate."""

    session = _get_owned_session_or_404(
        db,
        session_id,
        candidate.id,
    )

    if session.status == "ended":
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    livekit = _get_livekit_service(request)

    try:
        await livekit.end_session(session.room_name)
    except Exception as exc:
        logger.exception("LiveKit room deletion failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to end the LiveKit interview room.",
        ) from exc

    try:
        end_interview_session(
            db,
            session_id=session.id,
            candidate_id=candidate.id,
        )
    except InterviewSessionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
