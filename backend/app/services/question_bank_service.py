
import random

from app.repositories.question_bank_repository import (
    QuestionBankRepository
)


class QuestionBankService:

    VALID_DIFFICULTIES = {"easy", "medium", "hard"}

    def __init__(self, db):

        self.repository = QuestionBankRepository(db)

    def get_available_roles(self):

        roles = self.repository.get_all_roles()

        return [
            {
                "id": role.id,
                "role_name": role.role_name,
                "role_details": role.role_details,
                "technologies": [
                    tech.technology
                    for tech in role.technologies
                ]
            }
            for role in roles
        ]

    def get_role_details(self, role_name):

        role = self.repository.get_role_by_name(role_name)

        if role is None:
            raise ValueError("Job role not found.")

        counts = self.repository.get_question_counts(role.id)

        return {
            "id": role.id,
            "role_name": role.role_name,
            "role_details": role.role_details,
            "technologies": [
                tech.technology
                for tech in role.technologies
            ],
            "question_counts": {
                "easy": counts.get("easy", 0),
                "medium": counts.get("medium", 0),
                "hard": counts.get("hard", 0)
            }
        }

    def get_questions(self, role_name, difficulty):

        difficulty = difficulty.lower()

        if difficulty not in self.VALID_DIFFICULTIES:
            raise ValueError("Invalid difficulty level.")

        role = self.repository.get_role_by_name(role_name)

        if role is None:
            raise ValueError("Job role not found.")

        questions = self.repository.get_questions_by_difficulty(
            role.id,
            difficulty
        )

        return [
            {
                "id": question.id,
                "question": question.question_text,
                "difficulty": question.difficulty
            }
            for question in questions
        ]

    def select_random_questions(
        self,
        role_name,
        difficulty,
        count=1
    ):

        if count < 1:
            raise ValueError("Count must be at least 1.")

        questions = self.get_questions(
            role_name,
            difficulty
        )

        if count > len(questions):
            raise ValueError(
                f"Requested {count} questions, "
                f"but only {len(questions)} are available."
            )

        return random.sample(questions, count)
