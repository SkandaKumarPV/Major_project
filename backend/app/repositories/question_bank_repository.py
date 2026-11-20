from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.database.models import Role, InterviewQuestion


class QuestionBankRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_roles(self):
        statement = (
            select(Role)
            .options(selectinload(Role.technologies))
            .order_by(Role.role_name)
        )
        return self.db.scalars(statement).all()

    def get_role_by_name(self, role_name):
        statement = (
            select(Role)
            .options(
                selectinload(Role.technologies),
                selectinload(Role.questions),
            )
            .where(func.lower(Role.role_name) == role_name.strip().lower())
        )
        return self.db.scalar(statement)

    def get_questions_by_difficulty(self, role_id, difficulty, limit=None):
        statement = (
            select(InterviewQuestion)
            .where(
                InterviewQuestion.role_id == role_id,
                InterviewQuestion.difficulty == difficulty.lower(),
            )
            .order_by(InterviewQuestion.id)
        )

        if limit is not None:
            statement = statement.limit(limit)

        return self.db.scalars(statement).all()

    def get_question_counts(self, role_id):
        statement = (
            select(
                InterviewQuestion.difficulty,
                func.count(InterviewQuestion.id),
            )
            .where(InterviewQuestion.role_id == role_id)
            .group_by(InterviewQuestion.difficulty)
        )
        return dict(self.db.execute(statement).all())

    def get_random_unused_question(
        self,
        role_id,
        difficulty,
        excluded_ids=None,
        rng=None,
    ):
        """Return one random unused main question at the requested difficulty."""
        import random

        excluded_ids = [
            int(value)
            for value in (excluded_ids or [])
            if str(value).isdigit()
        ]

        statement = select(InterviewQuestion).where(
            InterviewQuestion.role_id == role_id,
            InterviewQuestion.difficulty == difficulty.lower(),
        )

        if excluded_ids:
            statement = statement.where(
                InterviewQuestion.id.not_in(excluded_ids)
            )

        questions = self.db.scalars(statement).all()

        if not questions:
            return None

        return (rng or random).choice(questions)