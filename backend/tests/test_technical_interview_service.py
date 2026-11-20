import pytest

from backend.app.services.technical_interview_service import (
    TechnicalInterviewError,
    TechnicalInterviewService,
)


class FakeLLM:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.contexts = []

    def generate_structured_response(
        self,
        system_prompt,
        conversation_context,
    ):
        self.contexts.append(
            (system_prompt, conversation_context)
        )
        return self.decisions.pop(0)


class FakeBank:
    def __init__(self):
        self.questions = {
            "easy": [
                {
                    "id": i,
                    "question": "Easy main question?",
                    "difficulty": "easy",
                }
                for i in range(1, 11)
            ],
            "medium": [
                {
                    "id": i,
                    "question": "Medium main question?",
                    "difficulty": "medium",
                }
                for i in range(11, 21)
            ],
            "hard": [
                {
                    "id": i,
                    "question": "Hard main question?",
                    "difficulty": "hard",
                }
                for i in range(21, 31)
            ],
        }

        self.calls = []

    def select(self, difficulty, used):
        self.calls.append(
            (difficulty, list(used))
        )

        for question in self.questions[difficulty]:
            if str(question["id"]) not in used:
                return question

        raise ValueError("no unused questions")


def decision(
    *,
    follow=False,
    follow_text=None,
    complete=True,
    difficulty=None,
    turn_type="answer",
    spoken=None,
    assessment=None,
):
    return {
        "turn_type": turn_type,
        "assessment": assessment or {
            "technical_correctness": "strong",
            "reasoning": "strong",
            "relevance": "strong",
            "summary": "Strong and relevant answer",
        },
        "follow_up_required": follow,
        "follow_up_text": follow_text,
        "main_question_complete": complete,
        "recommended_next_difficulty": difficulty,
        "spoken_response": spoken,
    }


def make_service(
    decisions=None,
    state=None,
    history=None,
):
    llm = FakeLLM(decisions or [])
    bank = FakeBank()

    service = TechnicalInterviewService(
        llm_provider=llm,
        question_selector=bank.select,
        role_data={
            "role_name": "Generative AI Engineer",
            "technologies": ["Python", "LLMs"],
        },
        resume_data={
            "skills": ["Python"],
            "projects": [
                {"name": "Voice Agent"}
            ],
        },
        initial_state=state,
        conversation_history=history,
    )

    return service, llm, bank


def test_first_question_is_selected_from_easy():
    service, _, bank = make_service()

    assert service.start() == "Easy main question?"

    assert bank.calls == [
        ("easy", [])
    ]

    assert (
        service.export_state()["main_questions"][0]["difficulty"]
        == "easy"
    )


@pytest.mark.parametrize(
    "difficulty",
    ["easy", "medium", "hard"],
)
def test_question_selector_supports_all_difficulties(
    difficulty,
):
    service, _, bank = make_service()

    question = service._select_main_question(
        difficulty
    )

    assert question["difficulty"] == difficulty

    assert bank.calls == [
        (difficulty, [])
    ]


def test_recommendation_only_controls_next_main_question():
    service, _, bank = make_service([
        decision(
            follow=True,
            follow_text="Why did you choose that approach?",
            complete=False,
        ),
        decision(
            complete=True,
            difficulty="medium",
            spoken="Next technical question.",
        ),
    ])

    service.start()

    first_followup = service.process_answer(
        "I used retrieval augmented generation."
    )

    assert (
        first_followup
        == "Why did you choose that approach?"
    )

    assert service.main_question_count == 1

    assert (
        service.process_answer(
            "It reduced unsupported answers."
        )
        == "Next technical question."
    )

    assert bank.calls[-1][0] == "medium"

    assert service.current_question["id"] == "11"


def test_no_repeated_question_ids():
    service, _, _ = make_service()

    service.start()

    with pytest.raises(
        TechnicalInterviewError,
        match="Repeated",
    ):
        service._activate_question(
            {
                "id": "1",
                "question": "Repeat?",
                "difficulty": "easy",
            },
            "easy",
        )


def test_exactly_three_main_questions_complete_stage():
    service, _, _ = make_service([
        decision(
            complete=True,
            difficulty="medium",
        ),
        decision(
            complete=True,
            difficulty="hard",
        ),
        decision(
            complete=True,
        ),
    ])

    service.start()

    service.process_answer("Answer one")
    service.process_answer("Answer two")

    response = service.process_answer(
        "Answer three"
    )

    state = service.export_state()

    assert "complete" in response.lower()

    assert len(state["main_questions"]) == 3

    assert len(
        state["completed_main_question_ids"]
    ) == 3

    assert state["stage_complete"] is True


def test_maximum_two_followups_per_main_question():
    service, _, _ = make_service([
        decision(
            follow=True,
            follow_text="Follow-up one?",
            complete=False,
        ),
        decision(
            follow=True,
            follow_text="Follow-up two?",
            complete=False,
        ),
        decision(
            follow=True,
            follow_text="Follow-up three?",
            complete=False,
        ),
    ])

    service.start()

    assert (
        service.process_answer("Answer 1")
        == "Follow-up one?"
    )

    assert (
        service.process_answer("Answer 2")
        == "Follow-up two?"
    )

    service.process_answer("Answer 3")

    assert service.current_follow_up_count == 0

    assert service.main_question_count == 2


def test_followup_context_contains_main_question_and_answer():
    service, llm, _ = make_service([
        decision(
            follow=True,
            follow_text="How would you handle a larger corpus?",
            complete=False,
        )
    ])

    service.start()

    service.process_answer(
        "I would use vector search and chunking."
    )

    context = str(llm.contexts[0][1])

    assert "Easy main question?" in context
    assert "vector search and chunking" in context
    assert "Voice Agent" in context


def test_followups_are_not_selected_from_question_bank():
    service, _, bank = make_service([
        decision(
            follow=True,
            follow_text="Why use embeddings?",
            complete=False,
        )
    ])

    service.start()

    service.process_answer(
        "I used embeddings."
    )

    assert len(bank.calls) == 1

    assert (
        service.current_question["question"]
        == "Easy main question?"
    )


def test_invalid_difficulty_recommendation_uses_safe_fallback():
    service, _, bank = make_service([
        decision(
            complete=True,
            difficulty="expert",
            assessment={"summary": "unclear"},
        )
    ])

    service.start()

    service.process_answer("Answer")

    assert bank.calls[-1][0] in {
        "easy",
        "medium",
        "hard",
    }


def test_greetings_and_candidate_questions_do_not_consume_question_counts():
    service, _, _ = make_service([
        decision(
            turn_type="greeting",
            spoken="Hello. Let's continue.",
        ),
        decision(
            turn_type="candidate_question",
            spoken="We will discuss that later.",
        ),
    ])

    service.start()

    before = service.export_state()

    service.process_answer("Hello")

    service.process_answer(
        "Can I ask about the role?"
    )

    after = service.export_state()

    assert (
        after["main_questions"]
        == before["main_questions"]
    )

    assert (
        after["current_follow_up_count"]
        == before["current_follow_up_count"]
    )

    assert (
        after["completed_main_question_ids"]
        == before["completed_main_question_ids"]
    )


def test_state_is_restored_after_reconnect():
    service, _, _ = make_service()

    service.start()

    state = service.export_state()

    restored, _, _ = make_service(
        state=state,
        history=service.conversation_history,
    )

    assert (
        restored.start()
        == "Easy main question?"
    )

    assert restored.used_main_question_ids == ["1"]


def test_full_transcript_history_is_preserved():
    service, _, _ = make_service([
        decision(
            follow=True,
            follow_text="Explain why?",
            complete=False,
        )
    ])

    service.start()

    service.process_answer(
        "I chose Python."
    )

    history = service.conversation_history

    assert history[0] == {
        "speaker": "interviewer",
        "text": "Easy main question?",
    }

    assert history[1] == {
        "speaker": "candidate",
        "text": "I chose Python.",
    }

    assert history[2] == {
        "speaker": "interviewer",
        "text": "Explain why?",
    }


def test_invalid_persisted_counts_are_rejected():
    with pytest.raises(TechnicalInterviewError):
        make_service(
            state={
                "current_follow_up_count": 3
            }
        )


def test_hard_fallback_requires_evidence_of_scenario_depth():
    service, _, bank = make_service([
        decision(
            complete=True,
            difficulty="invalid",
            assessment={
                "summary": "strong answer"
            },
        )
    ])

    service.start()

    service.process_answer(
        "A strong but basic answer"
    )

    assert bank.calls[-1][0] == "medium"


def test_hard_fallback_requires_challenging_scenario_evidence():
    service, _, bank = make_service([
        decision(
            complete=True,
            difficulty="invalid",
            assessment={
                "summary": (
                    "strong scenario reasoning "
                    "with trade-off analysis"
                )
            },
        )
    ])

    service.start()

    service.process_answer(
        "I considered failure modes and trade-offs"
    )

    # Easy promotes only to Medium.
    assert bank.calls[-1][0] == "medium"