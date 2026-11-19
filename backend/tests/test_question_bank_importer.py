
import json

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.database.models import Role, InterviewQuestion
from app.services import question_bank_importer


def test_import_is_idempotent(tmp_path, monkeypatch):

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    Base.metadata.create_all(engine)

    TestSession = sessionmaker(bind=engine)

    monkeypatch.setattr(
        question_bank_importer,
        "SessionLocal",
        TestSession
    )

    role_data = {
        "role_name": "Test Engineer",
        "role_details": "Test role.",
        "technologies": ["Python"],
        "questions": {
            "easy": [{"question": "Easy question?"}],
            "medium": [{"question": "Medium question?"}],
            "hard": [{"question": "Hard question?"}]
        }
    }

    json_file = tmp_path / "test_engineer.json"

    json_file.write_text(
        json.dumps(role_data),
        encoding="utf-8"
    )

    # First import
    question_bank_importer.import_role_file(json_file)

    # Second import
    question_bank_importer.import_role_file(json_file)

    with TestSession() as db:

        role_count = db.scalar(
            select(func.count()).select_from(Role)
        )

        question_count = db.scalar(
            select(func.count()).select_from(InterviewQuestion)
        )

        assert role_count == 1
        assert question_count == 3

    engine.dispose()
