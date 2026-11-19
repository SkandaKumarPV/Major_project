
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint
)

from sqlalchemy.orm import relationship

from app.database.database import Base


class Role(Base):

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)

    role_name = Column(
        String(150),
        unique=True,
        nullable=False,
        index=True
    )

    role_details = Column(
        Text,
        nullable=False
    )

    technologies = relationship(
        "RoleTechnology",
        back_populates="role",
        cascade="all, delete-orphan"
    )

    questions = relationship(
        "InterviewQuestion",
        back_populates="role",
        cascade="all, delete-orphan"
    )


class RoleTechnology(Base):

    __tablename__ = "role_technologies"

    id = Column(Integer, primary_key=True, index=True)

    role_id = Column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )

    technology = Column(
        String(150),
        nullable=False
    )

    role = relationship(
        "Role",
        back_populates="technologies"
    )

    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "technology",
            name="uq_role_technology"
        ),
    )


class InterviewQuestion(Base):

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)

    role_id = Column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )

    question_text = Column(
        Text,
        nullable=False
    )

    difficulty = Column(
        String(20),
        nullable=False
    )

    role = relationship(
        "Role",
        back_populates="questions"
    )

    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "question_text",
            name="uq_role_question"
        ),

        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')",
            name="ck_question_difficulty"
        ),
    )
