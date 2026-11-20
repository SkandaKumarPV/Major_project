
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


# backend/ directory
BACKEND_DIR = Path(__file__).resolve().parents[2]

# Separate from role_question_bank.db.
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


def migrate_interview_sessions(database_engine):
    """
    Add Milestone 2.3 columns to an existing interview_sessions table.

    This migration is additive: it does not delete or rewrite existing
    candidate, resume, or interview records.

    The current project uses SQLite for this database.
    """

    if database_engine.dialect.name != "sqlite":
        raise RuntimeError(
            "The interview-data migration currently supports SQLite only."
        )

    inspector = inspect(database_engine)

    if "interview_sessions" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("interview_sessions")
    }

    # Column definitions use SQLite-compatible types and defaults.
    new_columns = {
        "role_id": "VARCHAR(100)",
        "status": "VARCHAR(30) NOT NULL DEFAULT 'created'",
        "current_stage": "VARCHAR(80)",
        "current_main_question_id": "VARCHAR(100)",
        "used_main_question_ids": "JSON NOT NULL DEFAULT '[]'",
        "follow_up_count": "INTEGER NOT NULL DEFAULT 0",
        "completed_question_ids": "JSON NOT NULL DEFAULT '[]'",
        "completed_stages": "JSON NOT NULL DEFAULT '[]'",
        "structured_memory": "JSON NOT NULL DEFAULT '{}'",
        "started_at": "DATETIME",
        "ended_at": "DATETIME",
    }

    with database_engine.begin() as connection:
        for column_name, column_definition in new_columns.items():
            if column_name in existing_columns:
                continue

            connection.execute(
                text(
                    f"ALTER TABLE interview_sessions "
                    f"ADD COLUMN {column_name} {column_definition}"
                )
            )


def initialize_resume_database(target_engine=None):
    """
    Create missing resume/interview tables and migrate existing sessions.

    target_engine is optional and is used by isolated tests.
    """

    # Register all models with ResumeBase before create_all().
    from backend.app.database import resume_models  # noqa: F401

    BACKEND_DIR.joinpath("data").mkdir(
        parents=True,
        exist_ok=True,
    )

    database_engine = target_engine or resume_engine

    # Create missing tables first.
    ResumeBase.metadata.create_all(bind=database_engine)

    # Then add missing columns to any existing interview_sessions table.
    migrate_interview_sessions(database_engine)
