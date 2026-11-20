from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)

from sqlalchemy.orm import relationship

from backend.app.database.resume_database import ResumeBase


class GuestCandidate(ResumeBase):
    """
    Represents a guest candidate.

    The authentication token itself is never stored here.
    Only its SHA-256 hash is stored.
    """

    __tablename__ = "guest_candidates"

    id = Column(
        String(36),
        primary_key=True,
    )

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

    The original file is stored separately in private local storage.
    storage_key is an opaque identifier, not an absolute file path.
    """

    __tablename__ = "candidate_resumes"

    id = Column(
        String(36),
        primary_key=True,
    )

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

    size_bytes = Column(
        Integer,
        nullable=False,
    )

    raw_text = Column(
        Text,
        nullable=False,
    )

    structured_data = Column(
        JSON,
        nullable=False,
    )

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
    Connects a candidate to an interview and optionally to a resume.

    The application service must verify that the selected resume belongs
    to the same candidate before creating this relationship.
    """

    __tablename__ = "interview_sessions"

    id = Column(
        String(36),
        primary_key=True,
    )

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

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    candidate = relationship(
        "GuestCandidate",
        back_populates="interviews",
    )

    resume = relationship(
        "CandidateResume",
        back_populates="interviews",
    )