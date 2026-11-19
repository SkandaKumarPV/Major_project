
import json
from pathlib import Path

from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.models import (
    Role,
    RoleTechnology,
    InterviewQuestion
)


ROLES_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "roles"
)

EXPECTED_DIFFICULTIES = {"easy", "medium", "hard"}


def validate_role_data(data):

    required_fields = {
        "role_name",
        "role_details",
        "technologies",
        "questions"
    }

    if not isinstance(data, dict):
        raise ValueError("Role data must be a JSON object.")

    missing = required_fields - data.keys()

    if missing:
        raise ValueError(f"Missing fields: {missing}")

    if not isinstance(data["role_name"], str) or not data["role_name"].strip():
        raise ValueError("Invalid role_name.")

    if not isinstance(data["role_details"], str) or not data["role_details"].strip():
        raise ValueError("Invalid role_details.")

    technologies = data["technologies"]

    if (
        not isinstance(technologies, list)
        or not technologies
        or any(not isinstance(t, str) or not t.strip() for t in technologies)
    ):
        raise ValueError("Technologies must be a non-empty list of strings.")

    if len({t.strip().casefold() for t in technologies}) != len(technologies):
        raise ValueError("Duplicate technologies found.")

    questions = data["questions"]

    if not isinstance(questions, dict):
        raise ValueError("Questions must be an object.")

    if set(questions.keys()) != EXPECTED_DIFFICULTIES:
        raise ValueError(
            "Questions must contain exactly easy, medium and hard."
        )

    all_question_texts = []

    for difficulty, question_list in questions.items():

        if not isinstance(question_list, list) or not question_list:
            raise ValueError(
                f"{difficulty} must contain at least one question."
            )

        for item in question_list:

            if not isinstance(item, dict):
                raise ValueError("Each question must be an object.")

            if set(item.keys()) != {"question"}:
                raise ValueError(
                    "Each question must contain only the question field."
                )

            question = item["question"]

            if not isinstance(question, str) or not question.strip():
                raise ValueError("Question text cannot be empty.")

            all_question_texts.append(question.strip().casefold())

    if len(set(all_question_texts)) != len(all_question_texts):
        raise ValueError("Duplicate questions found within this role.")

    return True


def import_role_file(file_path):

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    validate_role_data(data)

    with SessionLocal.begin() as db:

        role_name = data["role_name"].strip()

        role = db.scalar(
            select(Role).where(Role.role_name == role_name)
        )

        if role is None:

            role = Role(
                role_name=role_name,
                role_details=data["role_details"]
            )

            db.add(role)
            db.flush()

        else:
            role.role_details = data["role_details"]

        # Synchronize technologies
        existing_technologies = {
            tech.technology.casefold(): tech
            for tech in role.technologies
        }

        incoming_technologies = {
            tech.strip().casefold(): tech.strip()
            for tech in data["technologies"]
        }

        for key, technology in incoming_technologies.items():

            if key not in existing_technologies:
                db.add(
                    RoleTechnology(
                        role_id=role.id,
                        technology=technology
                    )
                )

        for key, technology in existing_technologies.items():

            if key not in incoming_technologies:
                db.delete(technology)

        # Import questions
        existing_questions = {
            question.question_text.casefold(): question
            for question in role.questions
        }

        for difficulty, question_list in data["questions"].items():

            for item in question_list:

                question_text = item["question"].strip()

                key = question_text.casefold()

                existing = existing_questions.get(key)

                if existing is None:

                    db.add(
                        InterviewQuestion(
                            role_id=role.id,
                            question_text=question_text,
                            difficulty=difficulty
                        )
                    )

                else:
                    existing.question_text = question_text
                    existing.difficulty = difficulty

    print(f"Successfully imported: {role_name}")


def import_all_roles():

    if not ROLES_DIRECTORY.exists():
        raise FileNotFoundError(ROLES_DIRECTORY)

    json_files = sorted(ROLES_DIRECTORY.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No JSON files found in {ROLES_DIRECTORY}"
        )

    # Validate all files before importing any of them.
    for file_path in json_files:

        with open(file_path, "r", encoding="utf-8") as file:
            validate_role_data(json.load(file))

    for file_path in json_files:
        import_role_file(file_path)

    print("\nQuestion bank import completed.")
