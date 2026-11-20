
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import resume_models  # noqa: F401
from backend.app.database.resume_database import ResumeBase
from backend.app.database.resume_models import (
    CandidateResume,
    GuestCandidate,
    InterviewTranscriptMessage,
)
from backend.app.services.interview_session_service import (
    create_interview_session,
    get_interview_transcript,
    mark_interview_started,
)
from backend.app.services.interview_transcript_recorder import (
    InterviewTranscriptRecorder,
)


@pytest.fixture
def recorder_environment(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'transcript_recorder.db'}",
        connect_args={"check_same_thread": False},
    )
    ResumeBase.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    candidate_id = str(uuid.uuid4())
    resume_id = str(uuid.uuid4())

    with TestingSession() as db:
        candidate = GuestCandidate(
            id=candidate_id,
            token_hash="c" * 64,
        )
        db.add(candidate)
        db.flush()

        resume = CandidateResume(
            id=resume_id,
            candidate_id=candidate_id,
            storage_key=str(uuid.uuid4()),
            original_filename="candidate.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            raw_text="Candidate resume",
            structured_data={"name": "Candidate"},
        )
        db.add(resume)
        db.commit()

        interview = create_interview_session(
            db,
            candidate_id=candidate_id,
            room_name="interview-recorder-test",
            role_id="generative_ai_engineer",
            resume_id=resume_id,
        )

        interview_id = interview.id

        mark_interview_started(
            db,
            session_id=interview_id,
            candidate_id=candidate_id,
        )

    yield {
        "engine": engine,
        "session_factory": TestingSession,
        "candidate_id": candidate_id,
        "session_id": interview_id,
        "room_name": "interview-recorder-test",
    }

    engine.dispose()


def read_transcript(environment):
    with environment["session_factory"]() as db:
        return get_interview_transcript(
            db,
            session_id=environment["session_id"],
            candidate_id=environment["candidate_id"],
        )


def test_recorder_resolves_interview_by_room(recorder_environment):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    assert recorder.enabled is True
    assert recorder.session_id == recorder_environment["session_id"]
    assert recorder.candidate_id == recorder_environment["candidate_id"]

    recorder.close()


def test_interim_candidate_transcript_is_not_persisted(
    recorder_environment,
):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    recorder.record_candidate_transcript(
        "I am a computer science student",
        is_final=False,
    )

    assert read_transcript(recorder_environment) == []

    recorder.close()


def test_final_candidate_transcript_is_persisted(
    recorder_environment,
):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    recorder.record_candidate_transcript(
        "I am a computer science student.",
        is_final=True,
    )

    transcript = read_transcript(recorder_environment)

    assert len(transcript) == 1
    assert transcript[0].speaker == "candidate"
    assert transcript[0].message_text == (
        "I am a computer science student."
    )

    recorder.close()


def test_empty_final_candidate_transcript_is_ignored(
    recorder_environment,
):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    recorder.record_candidate_transcript("", is_final=True)
    recorder.record_candidate_transcript("   ", is_final=True)

    assert read_transcript(recorder_environment) == []

    recorder.close()


def test_assistant_conversation_item_is_persisted_as_interviewer(
    recorder_environment,
):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    event = SimpleNamespace(
        item=SimpleNamespace(
            role="assistant",
            text_content="Please introduce yourself.",
        )
    )

    recorder.record_conversation_item(event)

    transcript = read_transcript(recorder_environment)

    assert len(transcript) == 1
    assert transcript[0].speaker == "interviewer"
    assert transcript[0].message_text == "Please introduce yourself."

    recorder.close()


def test_candidate_conversation_item_is_not_duplicated(
    recorder_environment,
):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    event = SimpleNamespace(
        item=SimpleNamespace(
            role="user",
            text_content="My answer",
        )
    )

    recorder.record_conversation_item(event)

    assert read_transcript(recorder_environment) == []

    recorder.close()


def test_transcript_entries_keep_event_order(recorder_environment):
    recorder = InterviewTranscriptRecorder(
        room_name=recorder_environment["room_name"],
        session_factory=recorder_environment["session_factory"],
    )

    recorder.record_conversation_item(
        SimpleNamespace(
            item=SimpleNamespace(
                role="assistant",
                text_content="Tell me about yourself.",
            )
        )
    )

    recorder.record_candidate_transcript(
        "I am a computer science student.",
        is_final=True,
    )

    recorder.record_conversation_item(
        SimpleNamespace(
            item=SimpleNamespace(
                role="assistant",
                text_content="What project are you most proud of?",
            )
        )
    )

    transcript = read_transcript(recorder_environment)

    assert [message.sequence_number for message in transcript] == [1, 2, 3]
    assert [message.speaker for message in transcript] == [
        "interviewer",
        "candidate",
        "interviewer",
    ]

    recorder.close()


def test_unknown_room_disables_recorder_without_crashing(
    recorder_environment,
):
    recorder = InterviewTranscriptRecorder(
        room_name="interview-does-not-exist",
        session_factory=recorder_environment["session_factory"],
    )

    assert recorder.enabled is False

    # Calls are safely ignored when the room has no persistent session.
    recorder.record_candidate_transcript("Hello", is_final=True)

    assert read_transcript(recorder_environment) == []

    recorder.close()
