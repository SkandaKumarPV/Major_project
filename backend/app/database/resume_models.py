
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship

from backend.app.database.resume_database import ResumeBase


class GuestCandidate(ResumeBase):
    """
    Represents a temporary guest candidate.

    Only the SHA-256 hash of the authentication token is stored.
    """

    __tablename__ = "guest_candidates"

    id = Column(String(36), primary_key=True)

    token_hash = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    resumes = relationship(
        "CandidateResume",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    interviews = relationship(
        "InterviewSessionRecord",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class CandidateResume(ResumeBase):
    """
    Stores resume metadata and extracted information.

    The original file is stored separately in private storage.
    """

    __tablename__ = "candidate_resumes"

    id = Column(String(36), primary_key=True)

    candidate_id = Column(
        String(36),
        ForeignKey("guest_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    storage_key = Column(
        String(100),
        nullable=False,
        unique=True,
    )

    original_filename = Column(
        String(255),
        nullable=False,
    )

    mime_type = Column(
        String(100),
        nullable=False,
    )

    size_bytes = Column(Integer, nullable=False)

    raw_text = Column(Text, nullable=False)

    structured_data = Column(JSON, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    candidate = relationship(
        "GuestCandidate",
        back_populates="resumes",
    )

    interviews = relationship(
        "InterviewSessionRecord",
        back_populates="resume",
    )

    __table_args__ = (
        UniqueConstraint(
            "id",
            "candidate_id",
            name="uq_resume_id_candidate",
        ),
    )


class InterviewSessionRecord(ResumeBase):
    """
    Persistent backend-owned interview session.

    This model stores interview progress and compact structured memory.
    The full conversation transcript is stored separately.
    """

    __tablename__ = "interview_sessions"

    id = Column(String(36), primary_key=True)

    room_name = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    candidate_id = Column(
        String(36),
        ForeignKey("guest_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    resume_id = Column(
        String(36),
        ForeignKey("candidate_resumes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Nullable to preserve compatibility with existing interview records.
    role_id = Column(String(100), nullable=True)

    status = Column(
        String(30),
        nullable=False,
        default="created",
        server_default=text("'created'"),
        index=True,
    )

    current_stage = Column(
        String(80),
        nullable=True,
    )

    current_main_question_id = Column(
        String(100),
        nullable=True,
    )

    # JSON lists are backend-owned state, not direct LLM instructions.
    used_main_question_ids = Column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )

    follow_up_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    completed_question_ids = Column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )

    completed_stages = Column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )

    # Compact context intended to be selectively provided to the LLM.
    structured_memory = Column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    ended_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    candidate = relationship(
        "GuestCandidate",
        back_populates="interviews",
    )

    resume = relationship(
        "CandidateResume",
        back_populates="interviews",
    )

    transcript_messages = relationship(
        "InterviewTranscriptMessage",
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewTranscriptMessage.sequence_number",
    )


class InterviewTranscriptMessage(ResumeBase):
    """
    Stores one ordered transcript message belonging to an interview.

    This table is deliberately separate from structured interview memory.
    """

    __tablename__ = "interview_transcript_messages"

    id = Column(String(36), primary_key=True)

    interview_session_id = Column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sequence_number = Column(Integer, nullable=False)

    speaker = Column(
        String(20),
        nullable=False,
    )

    message_text = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    interview = relationship(
        "InterviewSessionRecord",
        back_populates="transcript_messages",
    )

    __table_args__ = (
        UniqueConstraint(
            "interview_session_id",
            "sequence_number",
            name="uq_transcript_session_sequence",
        ),
    )


class EvaluationReport(ResumeBase):
    """Candidate-owned completed interview report with two independent scores."""

    __tablename__ = "evaluation_reports"

    id = Column(String(36), primary_key=True)
    candidate_id = Column(
        String(36), ForeignKey("guest_candidates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    interview_session_id = Column(
        String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    resume_id = Column(
        String(36), ForeignKey("candidate_resumes.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    role_id = Column(String(100), nullable=False, index=True)
    completion_status = Column(String(30), nullable=False, default="completed")
    resume_score = Column(Float, nullable=False)
    interview_score = Column(Float, nullable=False)
    resume_report = Column(JSON, nullable=False)
    interview_report = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.current_timestamp())
