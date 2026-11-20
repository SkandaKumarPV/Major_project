import json

import pytest

from backend.app.services.resume_discussion_service import (
    ResumeDiscussionService,
    ResumeDiscussionStage,
)


class FakeLLM:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.prompts = []

    def generate_response(self, candidate_answer, **kwargs):
        self.prompts.append({
            "answer": candidate_answer,
            **kwargs,
        })
        if self.responses:
            return self.responses.pop(0)
        return json.dumps({
            "decision": "project_question",
            "question": "Could you explain a challenge in this project?",
            "selected_project": "AI Interview Simulator",
            "candidate_claim_quote": None,
            "resume_evidence_quote": None,
        })


def llm_response(
    question,
    *,
    decision="project_question",
    project="AI Interview Simulator",
    candidate_quote=None,
    resume_quote=None,
):
    return json.dumps({
        "decision": decision,
        "question": question,
        "selected_project": project,
        "candidate_claim_quote": candidate_quote,
        "resume_evidence_quote": resume_quote,
    })


@pytest.fixture
def resume():
    return {
        "projects": [
            {
                "name": "AI Interview Simulator",
                "description": "A real-time voice interview platform",
                "technologies": ["Python", "FastAPI", "LiveKit"],
            },
            {
                "name": "Flood Prediction",
                "description": "Flood forecasting using XGBoost",
                "technologies": ["Python", "XGBoost"],
            },
        ],
        "skills": ["Python", "FastAPI", "Machine Learning"],
        "work_experience": [],
        "education": [],
        "certifications": [],
    }


@pytest.fixture
def role():
    return {
        "id": "1",
        "role_name": "Generative AI Engineer",
        "role_details": "Build and integrate AI-powered applications.",
        "technologies": ["Python", "LLMs", "FastAPI"],
    }


def make_service(resume, role, responses=None, state=None, history=None):
    return ResumeDiscussionService(
        llm_provider=FakeLLM(responses),
        resume_data=resume,
        role_data=role,
        initial_state=state,
        conversation_history=history,
    )


def test_ai_always_initiates_with_introduction(resume, role):
    service = make_service(resume, role)
    opening = service.start()
    assert opening
    assert service.stage == ResumeDiscussionStage.INTRODUCTION
    assert "introduce yourself" in opening.lower()


def test_opening_covers_required_introduction_areas(resume, role):
    opening = make_service(resume, role).start().lower()
    assert "background" in opening
    assert "interests" in opening
    assert "project" in opening


@pytest.mark.parametrize(
    "role_data, expected",
    [
        ({"role_name": "Backend Developer"}, "Backend Developer"),
        ({"title": "Data Engineer"}, "Data Engineer"),
        ({"name": "ML Engineer"}, "ML Engineer"),
        ({}, "the selected role"),
    ],
)
def test_opening_uses_selected_role(resume, role_data, expected):
    opening = make_service(resume, role_data).start()
    assert expected in opening


def test_role_context_is_dynamic(resume):
    llm = FakeLLM([
        llm_response(
            "How did you design your data pipeline?",
            project="Flood Prediction",
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data={
            "title": "Data Engineer",
            "role_details": "Build data pipelines.",
            "technologies": ["Python", "SQL", "Spark"],
        },
    )
    service.start()
    service.process_answer("I have worked with Python.")
    prompt = llm.prompts[0]["conversation_context"][0]["text"]
    assert "Data Engineer" in prompt
    assert "Spark" in prompt


def test_project_question_uses_selected_resume_project(resume, role):
    llm = FakeLLM([
        llm_response(
            "How did you use LiveKit in your AI Interview Simulator?",
            project="AI Interview Simulator",
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer(
        "I built an AI Interview Simulator using Python and LiveKit."
    )
    assert "LiveKit" in result
    assert service.cross_question_count == 1
    assert service.current_project == "AI Interview Simulator"
    assert "AI Interview Simulator" in service.discussed_projects


def test_unverified_claim_does_not_create_mismatch(resume, role):
    llm = FakeLLM([
        llm_response(
            "Could you explain the architecture of your AI Interview Simulator?",
            project="AI Interview Simulator",
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer(
        "I have experience building AI applications."
    )
    assert "contradict" not in result.lower()
    assert service.cross_question_count == 1


def test_valid_verbatim_evidence_allows_clarification(resume, role):
    candidate_quote = "I used Java for the entire project."
    resume_quote = "Python"
    llm = FakeLLM([
        llm_response(
            "You mentioned Java, but the resume lists Python for this project. "
            "Could you clarify which language you used?",
            decision="clarification",
            project="AI Interview Simulator",
            candidate_quote=candidate_quote,
            resume_quote=resume_quote,
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer(
        f"My project was the AI Interview Simulator. {candidate_quote}"
    )
    assert "clarify" in result.lower()
    assert service.cross_question_count == 1


def test_invalid_candidate_quote_rejects_mismatch(resume, role):
    llm = FakeLLM([
        llm_response(
            "You claimed to use Java. Could you clarify?",
            decision="clarification",
            project="AI Interview Simulator",
            candidate_quote="I used Java",
            resume_quote="Python",
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer("I built an AI project.")
    assert "Could you walk me through" in result
    assert "claimed to use Java" not in result


def test_invalid_resume_quote_rejects_mismatch(resume, role):
    llm = FakeLLM([
        llm_response(
            "Your resume says Java. Could you clarify?",
            decision="clarification",
            project="AI Interview Simulator",
            candidate_quote="I used Java.",
            resume_quote="Resume says Java",
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer("I used Java.")
    assert "Your resume says Java" not in result
    assert result.endswith("?")


def test_missing_resume_information_is_not_a_contradiction(resume, role):
    llm = FakeLLM([
        llm_response(
            "Could you explain your contribution to the AI Interview Simulator?",
            project="AI Interview Simulator",
        )
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer(
        "I also worked on a cloud deployment."
    )
    assert "Could you explain" in result
    assert "contradict" not in result.lower()


def test_malformed_llm_output_fails_closed(resume, role):
    llm = FakeLLM(["This is not JSON and might be an accusation."])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    result = service.process_answer("I worked on a project.")
    assert "Could you walk me through" in result
    assert "accusation" not in result


def test_second_cross_question_adds_depth(resume, role):
    llm = FakeLLM([
        llm_response(
            "How did you use LiveKit in this project?",
            project="AI Interview Simulator",
        ),
        llm_response(
            "What challenges did you face managing real-time audio?",
            project="AI Interview Simulator",
        ),
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    first = service.process_answer(
        "I built an AI Interview Simulator using Python and LiveKit."
    )
    second = service.process_answer(
        "I used LiveKit for real-time audio streaming."
    )
    assert first != second
    assert service.cross_question_count == 2
    assert service.current_project == "AI Interview Simulator"
    assert (
        service.stage == ResumeDiscussionStage.RESUME_DISCUSSION
    )

def test_second_question_receives_first_project_context(resume, role):
    llm = FakeLLM([
        llm_response(
            "How did you use LiveKit?",
            project="AI Interview Simulator",
        ),
        llm_response(
            "How did you handle audio interruptions?",
            project="AI Interview Simulator",
        ),
    ])

    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )

    service.start()
    service.process_answer("I built an AI Interview Simulator.")
    service.process_answer("I used LiveKit.")

    second_prompt = llm.prompts[1]["conversation_context"][0]["text"]

    assert "AI Interview Simulator" in second_prompt
    assert "previously discussed projects" in second_prompt.lower()
    assert "current project" in second_prompt.lower()
    assert service.cross_question_count == 2

def test_maximum_two_cross_questions(resume, role):
    llm = FakeLLM([
        llm_response("First question?"),
        llm_response("Second question?"),
        llm_response("Third question?"),
    ])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    service.process_answer("My introduction.")
    service.process_answer("My first project answer.")
    result = service.process_answer("My second project answer.")
    assert result is None
    assert service.cross_question_count == 2
    assert service.stage == ResumeDiscussionStage.TECHNICAL_INTERVIEW
    assert len(llm.prompts) == 2


def test_transition_occurs_after_candidate_answers_second_question(
    resume, role
):
    service = make_service(
        resume,
        role,
        [
            llm_response("First question?"),
            llm_response("Second question?"),
        ],
    )
    service.start()
    service.process_answer("Introduction.")
    second_question = service.process_answer("Answer one.")
    assert second_question == "Second question?"
    assert service.stage == ResumeDiscussionStage.RESUME_DISCUSSION
    assert service.process_answer("Answer two.") is None
    assert service.stage == ResumeDiscussionStage.TECHNICAL_INTERVIEW


def test_candidate_answer_is_required(resume, role):
    service = make_service(resume, role)
    service.start()
    with pytest.raises(ValueError):
        service.process_answer("  ")


def test_service_cannot_start_twice(resume, role):
    service = make_service(resume, role)
    service.start()
    with pytest.raises(RuntimeError):
        service.start()


def test_llm_failure_does_not_duplicate_candidate_turn(resume, role):
    class FailingLLM:
        def generate_response(self, *args, **kwargs):
            raise RuntimeError("LLM unavailable")

    service = ResumeDiscussionService(
        llm_provider=FailingLLM(),
        resume_data=resume,
        role_data=role,
    )
    service.start()
    before = len(service.conversation_history)
    with pytest.raises(RuntimeError):
        service.process_answer("Candidate answer.")
    assert len(service.conversation_history) == before
    assert service.cross_question_count == 0


def test_stage_one_does_not_use_question_bank(resume, role):
    llm = FakeLLM([llm_response("Tell me about your project?")])
    service = ResumeDiscussionService(
        llm_provider=llm,
        resume_data=resume,
        role_data=role,
    )
    service.start()
    service.process_answer("I built an AI Interview Simulator.")
    assert "question_bank" not in str(llm.prompts).lower()


def test_export_state_contains_persistent_progress(resume, role):
    service = make_service(
        resume,
        role,
        [llm_response("Tell me about your project?")],
    )
    service.start()
    service.process_answer("I built an AI Interview Simulator.")
    state = service.export_state()
    assert state["stage"] == ResumeDiscussionStage.RESUME_DISCUSSION.value
    assert state["cross_question_count"] == 1
    assert state["current_project"] == "AI Interview Simulator"
    assert "AI Interview Simulator" in state["discussed_projects"]


def test_initial_state_restores_discussion(resume, role):
    state = {
        "stage": "resume_discussion",
        "cross_question_count": 1,
        "discussed_projects": ["AI Interview Simulator"],
        "current_project": "AI Interview Simulator",
    }
    history = [
        {"speaker": "interviewer", "text": "Opening"},
        {"speaker": "candidate", "text": "Introduction"},
        {"speaker": "interviewer", "text": "First question?"},
    ]
    service = ResumeDiscussionService(
        llm_provider=FakeLLM([llm_response("Second question?")]),
        resume_data=resume,
        role_data=role,
        initial_state=state,
        conversation_history=history,
    )
    assert service.stage == ResumeDiscussionStage.RESUME_DISCUSSION
    assert service.cross_question_count == 1
    result = service.process_answer("My answer.")
    assert result == "Second question?"
    assert service.cross_question_count == 2