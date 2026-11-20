import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.database.models import (
    Role,
    RoleTechnology,
    InterviewQuestion,
)
from app.services.question_bank_service import (
    QuestionBankService,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    db = TestingSession()

    role = Role(
        role_name="Generative AI Engineer",
        role_details="Develops LLM-powered applications.",
    )

    db.add(role)
    db.flush()

    db.add(
        RoleTechnology(
            role_id=role.id,
            technology="Python",
        )
    )

    db.add_all([
        InterviewQuestion(
            role_id=role.id,
            question_text=f"Easy scenario question {i}",
            difficulty="easy",
        )
        for i in range(1, 11)
    ])

    db.add_all([
        InterviewQuestion(
            role_id=role.id,
            question_text=f"Medium scenario question {i}",
            difficulty="medium",
        )
        for i in range(1, 11)
    ])

    db.add_all([
        InterviewQuestion(
            role_id=role.id,
            question_text=f"Hard scenario question {i}",
            difficulty="hard",
        )
        for i in range(1, 11)
    ])

    db.commit()

    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_get_role_details(db_session):
    service = QuestionBankService(db_session)

    role = service.get_role_details(
        "Generative AI Engineer"
    )

    assert role["role_name"] == "Generative AI Engineer"
    assert "Python" in role["technologies"]

    assert role["question_counts"]["easy"] == 10
    assert role["question_counts"]["medium"] == 10
    assert role["question_counts"]["hard"] == 10


def test_get_easy_questions(db_session):
    service = QuestionBankService(db_session)

    questions = service.get_questions(
        "Generative AI Engineer",
        "easy",
    )

    assert len(questions) == 10


def test_get_medium_questions(db_session):
    service = QuestionBankService(db_session)

    questions = service.get_questions(
        "Generative AI Engineer",
        "medium",
    )

    assert len(questions) == 10


def test_get_hard_questions(db_session):
    service = QuestionBankService(db_session)

    questions = service.get_questions(
        "Generative AI Engineer",
        "hard",
    )

    assert len(questions) == 10


def test_random_question_selection(db_session):
    service = QuestionBankService(db_session)

    questions = service.select_random_questions(
        "Generative AI Engineer",
        "easy",
        count=5,
    )

    assert len(questions) == 5

    ids = [
        question["id"]
        for question in questions
    ]

    assert len(ids) == len(set(ids))


def test_invalid_difficulty(db_session):
    service = QuestionBankService(db_session)

    with pytest.raises(ValueError):
        service.get_questions(
            "Generative AI Engineer",
            "expert",
        )


def test_invalid_role(db_session):
    service = QuestionBankService(db_session)

    with pytest.raises(ValueError):
        service.get_role_details(
            "Unknown Engineer"
        )


def test_select_more_questions_than_available(db_session):
    service = QuestionBankService(db_session)

    with pytest.raises(ValueError):
        service.select_random_questions(
            "Generative AI Engineer",
            "easy",
            count=15,
        )


@pytest.mark.parametrize(
    "difficulty",
    ["easy", "medium", "hard"],
)
def test_select_random_unused_question_for_each_difficulty(
    db_session,
    difficulty,
):
    service = QuestionBankService(db_session)

    first = service.select_random_unused_question(
        "Generative AI Engineer",
        difficulty,
        excluded_ids=[],
    )

    second = service.select_random_unused_question(
        "Generative AI Engineer",
        difficulty,
        excluded_ids=[first["id"]],
    )

    assert first["difficulty"] == difficulty
    assert second["difficulty"] == difficulty
    assert first["id"] != second["id"]


def test_select_random_unused_question_fails_when_all_questions_used(
    db_session,
):
    service = QuestionBankService(db_session)

    all_ids = [
        question["id"]
        for question in service.get_questions(
            "Generative AI Engineer",
            "easy",
        )
    ]

    with pytest.raises(
        ValueError,
        match="No unused easy questions",
    ):
        service.select_random_unused_question(
            "Generative AI Engineer",
            "easy",
            excluded_ids=all_ids,
        )