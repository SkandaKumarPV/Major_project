import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# backend/ directory
BACKEND_DIR = Path(__file__).resolve().parents[2]

# This database is separate from role_question_bank.db.
DEFAULT_RESUME_DATABASE_URL = (
    f"sqlite:///{BACKEND_DIR / 'data' / 'interview_data.db'}"
)

RESUME_DATABASE_URL = os.getenv(
    "INTERVIEW_DATABASE_URL",
    DEFAULT_RESUME_DATABASE_URL,
)


def create_resume_engine(database_url: str):
    """Create an engine for the private interview-data database."""

    connect_args = {}

    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    return create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


# Separate engine, session factory and model Base.
resume_engine = create_resume_engine(RESUME_DATABASE_URL)

ResumeSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=resume_engine,
)

ResumeBase = declarative_base()


def get_resume_db():
    """Provide a database session for resume-related operations."""

    db = ResumeSessionLocal()

    try:
        yield db
    finally:
        db.close()


def initialize_resume_database(target_engine=None):
    """
    Create resume-related tables.

    target_engine is optional and is useful for isolated tests.
    """

    # Register all resume models with ResumeBase.
    from backend.app.database import resume_models  # noqa: F401

    BACKEND_DIR.joinpath("data").mkdir(
        parents=True,
        exist_ok=True,
    )

    database_engine = target_engine or resume_engine

    ResumeBase.metadata.create_all(bind=database_engine)