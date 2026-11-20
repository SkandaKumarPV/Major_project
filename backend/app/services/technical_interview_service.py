"""Backend-owned adaptive three-question technical interview stage."""

from copy import deepcopy
import json
import random


class TechnicalInterviewError(Exception):
    """Raised when Stage 2 state or a turn is invalid."""


class TechnicalInterviewService:
    MAX_MAIN_QUESTIONS = 3
    MAX_FOLLOW_UPS = 2

    VALID_DIFFICULTIES = {"easy", "medium", "hard"}

    VALID_TURN_TYPES = {
        "answer",
        "greeting",
        "candidate_question",
    }

    def __init__(
        self,
        *,
        llm_provider,
        question_selector,
        role_data: dict,
        resume_data: dict,
        initial_state: dict | None = None,
        conversation_history: list | None = None,
        rng=None,
    ):
        self.llm_provider = llm_provider
        self.question_selector = question_selector

        self.role_data = deepcopy(role_data)
        self.resume_data = deepcopy(resume_data)

        self.conversation_history = deepcopy(
            conversation_history or []
        )

        self.rng = rng or random

        state = deepcopy(initial_state or {})

        self.main_questions = list(
            state.get("main_questions", [])
        )

        self.used_main_question_ids = [
            str(value)
            for value in state.get(
                "used_main_question_ids",
                [],
            )
        ]

        self.completed_main_question_ids = [
            str(value)
            for value in state.get(
                "completed_main_question_ids",
                [],
            )
        ]

        self.current_question = deepcopy(
            state.get("current_question")
        )

        self.current_follow_up_count = int(
            state.get("current_follow_up_count", 0)
        )

        self.current_difficulty = state.get(
            "current_difficulty"
        )

        self.next_difficulty = state.get(
            "next_difficulty"
        )

        self.current_question_complete = bool(
            state.get("current_question_complete", False)
        )

        self.turn_assessments = list(
            state.get("turn_assessments", [])
        )

        self.stage_complete = bool(
            state.get("stage_complete", False)
        )

        self._validate_state()

    def _validate_state(self):
        if len(self.main_questions) > self.MAX_MAIN_QUESTIONS:
            raise TechnicalInterviewError(
                "Stage 2 cannot contain more than three main questions."
            )

        if (
            len(self.used_main_question_ids)
            != len(set(self.used_main_question_ids))
        ):
            raise TechnicalInterviewError(
                "Repeated main question IDs are not allowed."
            )

        if len(self.used_main_question_ids) != len(
            self.main_questions
        ):
            raise TechnicalInterviewError(
                "Persisted question IDs do not match selected main questions."
            )

        if not (
            0
            <= self.current_follow_up_count
            <= self.MAX_FOLLOW_UPS
        ):
            raise TechnicalInterviewError(
                "Invalid follow-up count."
            )

        if (
            self.current_difficulty is not None
            and self.current_difficulty
            not in self.VALID_DIFFICULTIES
        ):
            raise TechnicalInterviewError(
                "Invalid current difficulty."
            )

        if (
            self.next_difficulty is not None
            and self.next_difficulty
            not in self.VALID_DIFFICULTIES
        ):
            raise TechnicalInterviewError(
                "Invalid recommended difficulty."
            )

        if (
            self.stage_complete
            and len(self.completed_main_question_ids)
            != self.MAX_MAIN_QUESTIONS
        ):
            raise TechnicalInterviewError(
                "A completed Stage 2 must contain exactly three completed main questions."
            )

    @property
    def main_question_count(self):
        return len(self.main_questions)

    @property
    def role_name(self):
        return (
            self.role_data.get("role_name")
            or "Generative AI Engineer"
        )

    def start(self):
        """Start Stage 2 or restore the active question."""

        if self.stage_complete:
            return "The technical interview is already complete."

        if self.current_question is not None:
            return self.current_question["question"]

        if self.main_questions:
            self.current_question = deepcopy(
                self.main_questions[-1]
            )
            return self.current_question["question"]

        # Main Question 1 is always Easy.
        question = self._select_main_question("easy")

        self._activate_question(
            question,
            "easy",
        )

        prompt = question["question"]

        self.conversation_history.append({
            "speaker": "interviewer",
            "text": prompt,
        })

        return prompt

    def process_answer(self, candidate_answer: str) -> str:
        """Process one finalized candidate turn."""

        if (
            not isinstance(candidate_answer, str)
            or not candidate_answer.strip()
        ):
            raise ValueError(
                "Candidate answer cannot be empty."
            )

        if (
            self.stage_complete
            or self.current_question is None
        ):
            raise TechnicalInterviewError(
                "There is no active technical question."
            )

        answer = candidate_answer.strip()

        answered_question_id = str(
            self.current_question["id"]
        )

        decision = self._get_turn_decision(answer)

        turn_type = decision.get(
            "turn_type",
            "answer",
        )

        if turn_type not in self.VALID_TURN_TYPES:
            decision = self._safe_decision("answer")
            turn_type = "answer"

        # Greetings and candidate questions are not technical answers.
        if turn_type in {
            "greeting",
            "candidate_question",
        }:
            spoken = self._safe_spoken(
                decision,
                (
                    "Of course. Let's continue with the current "
                    "technical question: "
                    + self.current_question["question"]
                ),
            )

            self.conversation_history.extend([
                {
                    "speaker": "candidate",
                    "text": answer,
                },
                {
                    "speaker": "interviewer",
                    "text": spoken,
                },
            ])

            return spoken

        assessment = decision.get("assessment")

        if not isinstance(assessment, dict):
            assessment = {
                "technical_correctness": "uncertain",
                "reasoning": "uncertain",
                "relevance": "uncertain",
                "summary": "Answer assessed conservatively.",
            }

        follow_up_required = bool(
            decision.get("follow_up_required")
        )

        follow_up_text = decision.get(
            "follow_up_text"
        )

        question_complete = bool(
            decision.get("main_question_complete")
        )

        # Backend hard limit: after two follow-ups,
        # the current main question must be completed.
        if (
            self.current_follow_up_count
            >= self.MAX_FOLLOW_UPS
        ):
            follow_up_required = False
            question_complete = True

        elif follow_up_required:
            if (
                not isinstance(follow_up_text, str)
                or not follow_up_text.strip()
                or not follow_up_text.strip().endswith("?")
            ):
                follow_up_required = False
                question_complete = True
            else:
                question_complete = False

        if follow_up_required:
            spoken = follow_up_text.strip()

        elif question_complete:
            self.current_question_complete = True

            if (
                answered_question_id
                not in self.completed_main_question_ids
            ):
                self.completed_main_question_ids.append(
                    answered_question_id
                )

            if (
                self.main_question_count
                >= self.MAX_MAIN_QUESTIONS
            ):
                self._complete_stage()

                spoken = self._safe_spoken(
                    decision,
                    "Thank you. That completes the technical interview.",
                )

            else:
                recommendation = decision.get(
                    "recommended_next_difficulty"
                )

                if (
                    recommendation
                    not in self.VALID_DIFFICULTIES
                ):
                    recommendation = self._fallback_difficulty(
                        assessment
                    )

                self.next_difficulty = recommendation

                next_question = self._select_main_question(
                    recommendation
                )

                self._activate_question(
                    next_question,
                    recommendation,
                )

                spoken = self._safe_spoken(
                    decision,
                    next_question["question"],
                )

        else:
            # An ambiguous LLM decision must not create
            # an unlimited interview turn.
            follow_up_text = decision.get(
                "follow_up_text"
            )

            if (
                isinstance(follow_up_text, str)
                and follow_up_text.strip().endswith("?")
                and self.current_follow_up_count
                < self.MAX_FOLLOW_UPS
            ):
                follow_up_required = True
                spoken = follow_up_text.strip()

            else:
                self.current_question_complete = True

                if (
                    answered_question_id
                    not in self.completed_main_question_ids
                ):
                    self.completed_main_question_ids.append(
                        answered_question_id
                    )

                if (
                    self.main_question_count
                    >= self.MAX_MAIN_QUESTIONS
                ):
                    self._complete_stage()

                    spoken = (
                        "Thank you. That completes the technical interview."
                    )

                else:
                    recommendation = (
                        self._fallback_difficulty(assessment)
                    )

                    self.next_difficulty = recommendation

                    next_question = self._select_main_question(
                        recommendation
                    )

                    self._activate_question(
                        next_question,
                        recommendation,
                    )

                    spoken = next_question["question"]

        self.conversation_history.append({
            "speaker": "candidate",
            "text": answer,
        })

        if follow_up_required:
            self.current_follow_up_count += 1

        self.turn_assessments.append({
            "question_id": answered_question_id,
            "answer": answer,
            "assessment": deepcopy(assessment),
        })

        self.conversation_history.append({
            "speaker": "interviewer",
            "text": spoken,
        })

        return spoken

    def _get_turn_decision(self, answer):
        context = self._build_context(answer)
        prompt = self._system_prompt()

        if hasattr(
            self.llm_provider,
            "generate_structured_response",
        ):
            raw = (
                self.llm_provider.generate_structured_response(
                    prompt,
                    context,
                )
            )
        else:
            raw = self.llm_provider.generate_response(
                prompt,
                conversation_context=context,
            )

        if isinstance(raw, dict):
            decision = raw
        else:
            try:
                decision = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return self._safe_decision("answer")

        if not isinstance(decision, dict):
            return self._safe_decision("answer")

        return decision

    def _system_prompt(self):
        return (
            "You are conducting one turn of a structured technical interview. "
            "Return ONLY JSON with keys: "
            "turn_type (answer|greeting|candidate_question), "
            "assessment object with technical_correctness, reasoning, "
            "relevance, summary; "
            "follow_up_required boolean; "
            "follow_up_text string or null; "
            "main_question_complete boolean; "
            "recommended_next_difficulty (easy|medium|hard|null); "
            "spoken_response string. "
            "Assess the overall answer, not one isolated mistake. "
            "Generate at most one contextual follow-up grounded in the "
            "current question, candidate answer, resume and interview memory. "
            "A follow-up may clarify, ask for reasoning, explore a technical "
            "detail or vary the scenario. Never reveal expected answers. "
            "Do not invent or select main questions. "
            "For greetings or candidate questions, set turn_type accordingly "
            "and do not complete the main question. "
            "Recommend difficulty only when the current main question is "
            "complete and another main question remains. "
            "Use Hard only for demonstrated strong scenario reasoning; "
            "strong Easy may move to Medium; weak Medium may move to Easy."
        )

    def _build_context(self, answer):
        return [
            {
                "speaker": "system",
                "text": self._system_prompt(),
            },
            {
                "speaker": "system",
                "text": "ROLE: "
                + json.dumps(
                    self.role_data,
                    ensure_ascii=False,
                ),
            },
            {
                "speaker": "system",
                "text": "RELEVANT RESUME: "
                + json.dumps(
                    self._safe_resume(),
                    ensure_ascii=False,
                ),
            },
            {
                "speaker": "system",
                "text": "CURRENT MAIN QUESTION: "
                + json.dumps(
                    self.current_question,
                    ensure_ascii=False,
                ),
            },
            {
                "speaker": "system",
                "text": "FOLLOW-UPS USED FOR THIS QUESTION: "
                + str(self.current_follow_up_count),
            },
            {
                "speaker": "system",
                "text": "INTERVIEW MEMORY: "
                + json.dumps(
                    self.turn_assessments[-8:],
                    ensure_ascii=False,
                ),
            },
            *self.conversation_history[-12:],
            {
                "speaker": "candidate",
                "text": answer,
            },
        ]

    def _safe_resume(self):
        """Expose only structured resume context relevant to follow-ups."""

        allowed_fields = (
            "skills",
            "projects",
            "work_experience",
            "education",
        )

        return {
            key: self.resume_data.get(key)
            for key in allowed_fields
            if key in self.resume_data
        }

    def _select_main_question(self, difficulty):
        try:
            question = self.question_selector(
                difficulty,
                list(self.used_main_question_ids),
            )

        except Exception as exc:
            raise TechnicalInterviewError(
                f"No unused {difficulty} main question is available."
            ) from exc

        if (
            not isinstance(question, dict)
            or not {
                "id",
                "question",
                "difficulty",
            }.issubset(question)
        ):
            raise TechnicalInterviewError(
                "Question bank returned an invalid main question."
            )

        question_id = str(question["id"])

        if question_id in self.used_main_question_ids:
            raise TechnicalInterviewError(
                "Question bank returned a repeated main question."
            )

        if question["difficulty"] != difficulty:
            raise TechnicalInterviewError(
                "Question bank returned a question at the wrong difficulty."
            )

        return {
            "id": question_id,
            "question": question["question"],
            "difficulty": difficulty,
        }

    def _activate_question(self, question, difficulty):
        question_id = str(question.get("id"))

        if question_id in self.used_main_question_ids:
            raise TechnicalInterviewError(
                "Repeated main question IDs are not allowed."
            )

        self.current_question = deepcopy(question)
        self.current_difficulty = difficulty
        self.current_follow_up_count = 0
        self.current_question_complete = False

        self.used_main_question_ids.append(question_id)

        self.main_questions.append(
            deepcopy(question)
        )

    def _fallback_difficulty(self, assessment):
        summary = " ".join(
            str(assessment.get(key, ""))
            for key in (
                "technical_correctness",
                "reasoning",
                "relevance",
                "summary",
            )
        ).lower()

        strong = any(
            word in summary
            for word in (
                "strong",
                "excellent",
                "correct",
                "comprehensive",
            )
        )

        scenario_depth = (
            "scenario" in summary
            or "trade-off" in summary
            or "edge case" in summary
        )

        if strong:
            if self.current_difficulty == "easy":
                return "medium"

            if (
                self.current_difficulty == "medium"
                and scenario_depth
            ):
                return "hard"

            return (
                "medium"
                if self.current_difficulty == "medium"
                else "hard"
            )

        if any(
            word in summary
            for word in (
                "weak",
                "incorrect",
                "poor",
                "irrelevant",
            )
        ):
            return "easy"

        return self.current_difficulty or "easy"

    @staticmethod
    def _safe_spoken(decision, fallback):
        spoken = decision.get("spoken_response")

        if isinstance(spoken, str) and spoken.strip():
            return spoken.strip()

        return fallback

    @staticmethod
    def _safe_decision(turn_type):
        return {
            "turn_type": turn_type,
            "assessment": {},
            "follow_up_required": False,
            "follow_up_text": None,
            "main_question_complete": True,
            "recommended_next_difficulty": None,
            "spoken_response": None,
        }

    def _complete_stage(self):
        if (
            self.current_question
            and str(self.current_question["id"])
            not in self.completed_main_question_ids
        ):
            self.completed_main_question_ids.append(
                str(self.current_question["id"])
            )

        if (
            len(self.completed_main_question_ids)
            != self.MAX_MAIN_QUESTIONS
        ):
            raise TechnicalInterviewError(
                "Stage 2 completion requires exactly three completed main questions."
            )

        self.stage_complete = True

    def export_state(self):
        return {
            "main_questions": deepcopy(
                self.main_questions
            ),
            "used_main_question_ids": list(
                self.used_main_question_ids
            ),
            "completed_main_question_ids": list(
                self.completed_main_question_ids
            ),
            "current_question": deepcopy(
                self.current_question
            ),
            "current_follow_up_count": (
                self.current_follow_up_count
            ),
            "current_difficulty": (
                self.current_difficulty
            ),
            "next_difficulty": self.next_difficulty,
            "current_question_complete": (
                self.current_question_complete
            ),
            "turn_assessments": deepcopy(
                self.turn_assessments
            ),
            "stage_complete": self.stage_complete,
        }