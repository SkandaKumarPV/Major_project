
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# Project root: backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]

# Default local database
DEFAULT_DATABASE_URL = (
    f"sqlite:///{BACKEND_DIR / 'data' / 'role_question_bank.db'}"
)

# Allow future database replacement using environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    DEFAULT_DATABASE_URL
)

# SQLite-specific configuration
connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Create database engine
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

# Database session
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for SQLAlchemy models
Base = declarative_base()


def get_db():
    """Provide a database session."""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def initialize_database():
    """Create database tables."""

    BACKEND_DIR.joinpath("data").mkdir(
        parents=True,
        exist_ok=True
    )

    from app.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
