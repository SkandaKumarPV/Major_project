import json
import uuid
from copy import deepcopy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import resume_models  # noqa: F401
from backend.app.database.resume_database import ResumeBase
from backend.app.database.resume_models import (
    CandidateResume,
    EvaluationReport,
    GuestCandidate,
    InterviewSessionRecord,
    InterviewTranscriptMessage,
)
from backend.app.services import evaluation_report_service
from backend.app.services.evaluation_report_service import (
    EvaluationError,
    generate_completed_report,
)


# =========================================================
# CONSTANTS
# =========================================================

ROLE_DETAILS = {
    "id": "role-001",
    "name": "Generative AI Engineer",
    "details": (
        "Develop and maintain generative AI applications, "
        "retrieval systems and backend services."
    ),
    "technologies": [
        "Python",
        "FastAPI",
        "LLMs",
        "Vector Databases",
    ],
}


RESUME_RESPONSE = {
    "score": 8.2,

    "strengths": [
        {
            "claim": "The candidate has Python experience.",
            "evidence": "Python, FastAPI",
        },
        {
            "claim": "The candidate has Kubernetes experience.",
            "evidence": "Kubernetes expert",
        },
    ],

    "missing_or_weak_skills": [
        "Kubernetes is not evidenced in the supplied resume.",
    ],

    "experience_alignment": [
        {
            "claim": "The candidate has worked on a RAG application.",
            "evidence": (
                "Built a RAG application using FastAPI "
                "and vector search."
            ),
        },
    ],

    "improvement_areas": [
        "Add more detail about deployment and monitoring experience.",
    ],

    "score_rationale": (
        "The resume provides evidence of Python, FastAPI "
        "and retrieval application development."
    ),
}


INTERVIEW_RESPONSE = {
    "score": 7.4,

    "technical_strengths": [
        "Explained the basic architecture of a RAG application.",
        "Correctly described the purpose of vector search.",
    ],

    "weak_or_incorrect_answers": [
        "The explanation of retrieval evaluation was incomplete.",
    ],

    "missing_concepts": [
        "Retrieval precision and recall.",
    ],

    "answer_by_answer_feedback": [
        {
            "question": "Explain a RAG application.",
            "assessment": "Partially correct.",
            "feedback": (
                "You explained retrieval and generation, "
                "but could describe the complete data flow."
            ),
            "missing_concepts": [
                "Context construction",
            ],
            "correctness": "partially_correct",
            "evidence": (
                "A RAG application retrieves relevant documents "
                "and sends them to an LLM."
            ),
        },
        {
            "question": "What is vector search?",
            "assessment": "Technically correct.",
            "feedback": (
                "You correctly described similarity-based retrieval."
            ),
            "missing_concepts": [],
            "correctness": "technically_correct",
            "evidence": (
                "Vector search compares embeddings to find "
                "semantically similar content."
            ),
        },
        {
            "question": "How would you evaluate retrieval quality?",
            "assessment": "Incomplete.",
            "feedback": (
                "Include precision, recall and the relevance "
                "of retrieved documents."
            ),
            "missing_concepts": [
                "Precision",
                "Recall",
            ],
            "correctness": "insufficient_evidence",
            "evidence": (
                "I would check whether the retrieved documents "
                "are relevant."
            ),
        },
    ],

    "reasoning_and_justification": (
        "The candidate demonstrated a reasonable understanding "
        "of retrieval and generation, but retrieval evaluation "
        "was not fully explained."
    ),

    "recommendations": [
        "Study retrieval evaluation metrics.",
        "Practice explaining RAG architecture end to end.",
    ],

    "score_rationale": (
        "The candidate demonstrated partial-to-good technical "
        "understanding across the interview."
    ),
}


def candidate_transcript():
    return [
        (
            "interviewer",
            "Please introduce yourself.",
        ),
        (
            "candidate",
            "I am a computer science student interested in AI.",
        ),
        (
            "interviewer",
            "Tell me about your RAG project.",
        ),
        (
            "candidate",
            "A RAG application retrieves relevant documents "
            "and sends them to an LLM.",
        ),
        (
            "interviewer",
            "What is vector search?",
        ),
        (
            "candidate",
            "Vector search compares embeddings to find "
            "semantically similar content.",
        ),
        (
            "interviewer",
            "How would you evaluate retrieval quality?",
        ),
        (
            "candidate",
            "I would check whether the retrieved documents "
            "are relevant.",
        ),
    ]


# =========================================================
# TEST DATABASE
# =========================================================

@pytest.fixture
def db_session(tmp_path):
    database_path = tmp_path / "evaluation_report_test.db"

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    ResumeBase.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    db = TestingSessionLocal()

    try:
        yield db

    finally:
        db.close()
        engine.dispose()


# =========================================================
# ROLE LOOKUP
# =========================================================

@pytest.fixture
def role_lookup(monkeypatch):
    """
    Isolate evaluation tests from role_question_bank.db.

    The real role lookup is tested separately through the role
    question-bank integration.
    """

    monkeypatch.setattr(
        evaluation_report_service,
        "_role_details",
        lambda role_id: deepcopy(ROLE_DETAILS),
    )


# =========================================================
# FAKE LLM PROVIDER
# =========================================================

class FakeLLMProvider:
    """
    Deterministic LLM provider for service unit tests.

    Responses are returned in order:
    1. Resume suitability evaluation.
    2. Interview performance evaluation.
    """

    def __init__(
        self,
        resume_response=None,
        interview_response=None,
    ):
        self.responses = [
            deepcopy(
                resume_response
                if resume_response is not None
                else RESUME_RESPONSE
            ),
            deepcopy(
                interview_response
                if interview_response is not None
                else INTERVIEW_RESPONSE
            ),
        ]

        self.calls = []

    def generate_structured_response(
        self,
        system_prompt,
        conversation_context=None,
    ):
        self.calls.append({
            "prompt": system_prompt,
            "context": deepcopy(conversation_context),
        })

        if not self.responses:
            raise AssertionError(
                "Unexpected additional LLM request."
            )

        return self.responses.pop(0)


# =========================================================
# FIXTURES — CANDIDATE, RESUME, SESSION AND TRANSCRIPT
# =========================================================

@pytest.fixture
def completed_interview(db_session):
    candidate_id = str(uuid.uuid4())
    resume_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    candidate = GuestCandidate(
        id=candidate_id,
        token_hash="a" * 64,
    )

    resume = CandidateResume(
        id=resume_id,
        candidate_id=candidate_id,
        storage_key=str(uuid.uuid4()),
        original_filename="candidate_resume.pdf",
        mime_type="application/pdf",
        size_bytes=2048,

        raw_text=(
            "RAW_RESUME_SECRET_MARKER "
            "Private Candidate Name "
            "private.candidate@example.com"
        ),

        structured_data={
            "name": "Private Candidate Name",
            "email": "private.candidate@example.com",
            "phone": "+91 9876543210",

            "skills": [
                "Python, FastAPI",
            ],

            "projects": [
                (
                    "Built a RAG application using FastAPI "
                    "and vector search."
                ),
            ],

            "work_experience": [
                {
                    "description": (
                        "Developed backend APIs using Python."
                    ),
                    "email": "private.candidate@example.com",
                },
            ],

            "education": [
                "B.Sc. Computer Science",
            ],

            "certifications": [],
        },
    )

    session = InterviewSessionRecord(
        id=session_id,
        room_name=f"evaluation-room-{uuid.uuid4()}",
        candidate_id=candidate_id,
        resume_id=resume_id,
        role_id="role-001",
        status="completed",
        current_stage="completed",
        current_main_question_id=None,
        used_main_question_ids=[
            "question-001",
            "question-002",
            "question-003",
        ],
        follow_up_count=0,
        completed_question_ids=[
            "question-001",
            "question-002",
            "question-003",
        ],
        completed_stages=[
            "introduction",
            "resume_discussion",
            "technical_interview",
        ],
        structured_memory={
            "technical_interview": {
                "stage_complete": True,
                "completed_main_question_ids": [
                    "question-001",
                    "question-002",
                    "question-003",
                ],
                "turn_assessments": [
                    {
                        "question_id": "question-001",
                        "assessment": "Partially correct",
                    },
                    {
                        "question_id": "question-002",
                        "assessment": "Correct",
                    },
                    {
                        "question_id": "question-003",
                        "assessment": "Incomplete",
                    },
                ],
            }
        },
    )

    db_session.add_all([
        candidate,
        resume,
        session,
    ])

    db_session.flush()

    for index, (speaker, message_text) in enumerate(
        candidate_transcript(),
        start=1,
    ):
        db_session.add(
            InterviewTranscriptMessage(
                id=str(uuid.uuid4()),
                interview_session_id=session_id,
                sequence_number=index,
                speaker=speaker,
                message_text=message_text,
            )
        )

    db_session.commit()

    return {
        "candidate": candidate,
        "resume": resume,
        "session": session,
    }


# =========================================================
# REPORT GENERATION
# =========================================================

def test_generates_separate_resume_and_interview_scores(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    assert report.resume_score == 8.2
    assert report.interview_score == 7.4

    assert report.resume_score != report.interview_score

    assert report.resume_report["score"] == 8.2
    assert report.interview_report["score"] == 7.4

    assert report.completion_status == "completed"

    # No combined or aggregate score should be created.
    assert "overall_score" not in report.resume_report
    assert "overall_score" not in report.interview_report


def test_report_is_linked_to_correct_candidate_session_resume_and_role(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]
    resume = completed_interview["resume"]

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=FakeLLMProvider(),
    )

    assert report.candidate_id == candidate.id
    assert report.interview_session_id == session.id
    assert report.resume_id == resume.id
    assert report.role_id == session.role_id


def test_report_is_persisted_in_interview_database(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    generated = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=FakeLLMProvider(),
    )

    db_session.expire_all()

    saved = db_session.query(EvaluationReport).filter(
        EvaluationReport.interview_session_id == session.id,
        EvaluationReport.candidate_id == candidate.id,
    ).one_or_none()

    assert saved is not None
    assert saved.id == generated.id

    assert saved.resume_score == 8.2
    assert saved.interview_score == 7.4

    assert saved.resume_report is not None
    assert saved.interview_report is not None


# =========================================================
# RESUME EVIDENCE VALIDATION
# =========================================================

def test_unsupported_positive_resume_claim_is_discarded(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    strengths = report.resume_report["strengths"]

    assert any(
        item["claim"] == "The candidate has Python experience."
        for item in strengths
    )

    assert not any(
        item["claim"] == "The candidate has Kubernetes experience."
        for item in strengths
    )


def test_resume_evidence_must_match_structured_resume_data(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    for item in report.resume_report["strengths"]:
        assert item["evidence"] == "Python, FastAPI"

    for item in report.resume_report["experience_alignment"]:
        assert item["evidence"] == (
            "Built a RAG application using FastAPI "
            "and vector search."
        )


# =========================================================
# PRIVATE DATA PROTECTION
# =========================================================

def test_raw_resume_and_contact_data_are_not_sent_to_llm(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    resume_context_text = provider.calls[0]["context"][0]["text"]

    assert "RAW_RESUME_SECRET_MARKER" not in resume_context_text
    assert "Private Candidate Name" not in resume_context_text
    assert "private.candidate@example.com" not in resume_context_text
    assert "+91 9876543210" not in resume_context_text

    assert "Python, FastAPI" in resume_context_text
    assert "RAG application" in resume_context_text


def test_raw_resume_text_is_not_saved_in_candidate_report(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=FakeLLMProvider(),
    )

    serialized_report = json.dumps({
        "resume": report.resume_report,
        "interview": report.interview_report,
    })

    assert "RAW_RESUME_SECRET_MARKER" not in serialized_report
    assert "private.candidate@example.com" not in serialized_report


# =========================================================
# ROLE AND TRANSCRIPT CONTEXT
# =========================================================

def test_evaluator_receives_selected_role_details(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    resume_context = json.loads(
        provider.calls[0]["context"][0]["text"]
    )

    interview_context = json.loads(
        provider.calls[1]["context"][0]["text"]
    )

    assert resume_context["role"]["name"] == (
        "Generative AI Engineer"
    )

    assert interview_context["role"]["id"] == "role-001"

    assert "Python" in interview_context["role"]["technologies"]
    assert "FastAPI" in interview_context["role"]["technologies"]


def test_interview_evaluator_receives_ordered_full_transcript(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    interview_context = json.loads(
        provider.calls[1]["context"][0]["text"]
    )

    transcript = interview_context["ordered_transcript"]

    assert len(transcript) == 8

    assert transcript[0]["speaker"] == "interviewer"
    assert transcript[1]["speaker"] == "candidate"

    assert transcript[1]["text"] == (
        "I am a computer science student interested in AI."
    )

    assert transcript[-1]["text"] == (
        "I would check whether the retrieved documents "
        "are relevant."
    )


def test_interview_evaluator_receives_turn_assessments(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    interview_context = json.loads(
        provider.calls[1]["context"][0]["text"]
    )

    assessments = interview_context[
        "technical_turn_assessments"
    ]

    assert len(assessments) == 3
    assert assessments[0]["question_id"] == "question-001"


# =========================================================
# ANSWER-BY-ANSWER FEEDBACK
# =========================================================

def test_answer_feedback_is_tied_to_candidate_transcript_evidence(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=FakeLLMProvider(),
    )

    feedback = report.interview_report[
        "answer_by_answer_feedback"
    ]

    assert len(feedback) == 3

    candidate_messages = {
        message_text
        for speaker, message_text in candidate_transcript()
        if speaker == "candidate"
    }

    for item in feedback:
        assert item["evidence"] in candidate_messages


def test_unsupported_interview_feedback_is_discarded(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    invalid_interview_response = deepcopy(INTERVIEW_RESPONSE)

    invalid_interview_response["answer_by_answer_feedback"][0][
        "evidence"
    ] = "This statement never appeared in the transcript."

    provider = FakeLLMProvider(
        interview_response=invalid_interview_response,
    )

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            llm_provider=provider,
        )

    assert db_session.query(EvaluationReport).count() == 0


def test_technical_correctness_categories_are_preserved(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=FakeLLMProvider(),
    )

    feedback = report.interview_report[
        "answer_by_answer_feedback"
    ]

    assert feedback[0]["correctness"] == "partially_correct"
    assert feedback[1]["correctness"] == "technically_correct"
    assert feedback[2]["correctness"] == "insufficient_evidence"


# =========================================================
# SCORE VALIDATION
# =========================================================

@pytest.mark.parametrize(
    "invalid_score",
    [
        -0.1,
        10.1,
        True,
        "8.5",
        None,
    ],
)
def test_invalid_resume_score_is_rejected(
    db_session,
    completed_interview,
    role_lookup,
    invalid_score,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    invalid_resume_response = deepcopy(RESUME_RESPONSE)
    invalid_resume_response["score"] = invalid_score

    provider = FakeLLMProvider(
        resume_response=invalid_resume_response,
    )

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            llm_provider=provider,
        )

    assert db_session.query(EvaluationReport).count() == 0


@pytest.mark.parametrize(
    "invalid_score",
    [
        -1,
        10.5,
        False,
        "7.4",
        None,
    ],
)
def test_invalid_interview_score_is_rejected(
    db_session,
    completed_interview,
    role_lookup,
    invalid_score,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    invalid_interview_response = deepcopy(INTERVIEW_RESPONSE)
    invalid_interview_response["score"] = invalid_score

    provider = FakeLLMProvider(
        interview_response=invalid_interview_response,
    )

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            llm_provider=provider,
        )

    assert db_session.query(EvaluationReport).count() == 0


# =========================================================
# INCOMPLETE INTERVIEW PROTECTION
# =========================================================

def test_incomplete_interview_does_not_generate_report(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    session.current_stage = "main_questions"

    db_session.commit()

    provider = FakeLLMProvider()

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            llm_provider=provider,
        )

    assert provider.calls == []
    assert db_session.query(EvaluationReport).count() == 0


@pytest.mark.parametrize(
    "completed_ids",
    [
        [],
        ["question-001"],
        ["question-001", "question-002"],
        [
            "question-001",
            "question-002",
            "question-002",
        ],
        [
            "question-001",
            "question-002",
            "question-003",
            "question-004",
        ],
    ],
)
def test_report_requires_exactly_three_distinct_main_questions(
    db_session,
    completed_interview,
    role_lookup,
    completed_ids,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    session.structured_memory = {
        "technical_interview": {
            "stage_complete": True,
            "completed_main_question_ids": completed_ids,
        }
    }

    db_session.commit()

    provider = FakeLLMProvider()

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            llm_provider=provider,
        )

    assert provider.calls == []
    assert db_session.query(EvaluationReport).count() == 0


def test_interrupted_session_cannot_receive_report(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    session.status = "interrupted"

    db_session.commit()

    provider = FakeLLMProvider()

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=candidate.id,
            llm_provider=provider,
        )

    assert provider.calls == []
    assert db_session.query(EvaluationReport).count() == 0


# =========================================================
# CANDIDATE OWNERSHIP
# =========================================================

def test_candidate_cannot_generate_another_candidates_report(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]

    provider = FakeLLMProvider()

    with pytest.raises(EvaluationError):
        generate_completed_report(
            db_session,
            session_id=session.id,
            candidate_id=str(uuid.uuid4()),
            llm_provider=provider,
        )

    assert provider.calls == []
    assert db_session.query(EvaluationReport).count() == 0


# =========================================================
# REPORT RETRIEVAL / IDEMPOTENCY
# =========================================================

def test_report_is_not_generated_twice(
    db_session,
    completed_interview,
    role_lookup,
):
    session = completed_interview["session"]
    candidate = completed_interview["candidate"]

    provider = FakeLLMProvider()

    first_report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=provider,
    )

    first_report_id = first_report.id

    second_provider = FakeLLMProvider()

    second_report = generate_completed_report(
        db_session,
        session_id=session.id,
        candidate_id=candidate.id,
        llm_provider=second_provider,
    )

    assert second_report.id == first_report_id

    # Existing report is returned without another LLM call.
    assert second_provider.calls == []

    assert db_session.query(EvaluationReport).filter_by(
        interview_session_id=session.id
    ).count() == 1