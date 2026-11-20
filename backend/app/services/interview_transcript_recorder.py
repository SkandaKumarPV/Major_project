
import logging

from sqlalchemy.orm import sessionmaker

from backend.app.database.resume_database import ResumeSessionLocal
from backend.app.database.resume_models import InterviewSessionRecord
from backend.app.services.interview_session_service import (
    append_transcript_message,
)

logger = logging.getLogger("ai-interviewer-transcript-recorder")


class InterviewTranscriptRecorder:
    """
    Persists final candidate transcripts and committed interviewer messages.

    The LiveKit room name is used to resolve the persistent interview record.
    Each write uses its own SQLAlchemy session.
    """

    def __init__(
        self,
        room_name: str,
        session_factory: sessionmaker = ResumeSessionLocal,
    ):
        self.room_name = room_name
        self.session_factory = session_factory
        self.session_id = None
        self.candidate_id = None
        self.enabled = False

        self._resolve_interview()

    def _resolve_interview(self):
        try:
            with self.session_factory() as db:
                interview = (
                    db.query(InterviewSessionRecord)
                    .filter(
                        InterviewSessionRecord.room_name == self.room_name
                    )
                    .one_or_none()
                )

                if interview is None:
                    logger.warning(
                        "No persistent interview found for room %s. "
                        "Transcript persistence is disabled for this room.",
                        self.room_name,
                    )
                    return

                if interview.status == "ended":
                    logger.warning(
                        "Interview for room %s has already ended.",
                        self.room_name,
                    )
                    return

                self.session_id = interview.id
                self.candidate_id = interview.candidate_id
                self.enabled = True

        except Exception:
            logger.exception(
                "Could not resolve persistent interview for room %s",
                self.room_name,
            )

    def _save(self, speaker: str, text: str):
        if not self.enabled:
            return

        if not isinstance(text, str) or not text.strip():
            return

        try:
            with self.session_factory() as db:
                append_transcript_message(
                    db,
                    session_id=self.session_id,
                    candidate_id=self.candidate_id,
                    speaker=speaker,
                    message_text=text,
                )

        except Exception:
            # A persistence failure must not crash the LiveKit voice pipeline.
            logger.exception(
                "Failed to persist %s transcript for session %s",
                speaker,
                self.session_id,
            )

    def record_candidate_transcript(
        self,
        text: str,
        is_final: bool,
    ):
        """Persist only final candidate STT transcripts."""

        if not is_final:
            return

        self._save("candidate", text)

    def record_conversation_item(self, event):
        """
        Persist committed assistant messages.

        Candidate conversation items are deliberately ignored here because
        final candidate STT is persisted through record_candidate_transcript.
        """

        item = getattr(event, "item", None)

        if item is None:
            return

        role = str(getattr(item, "role", "")).lower()

        if role not in {"assistant", "agent"}:
            return

        text = getattr(item, "text_content", None)

        if not isinstance(text, str) or not text.strip():
            text = getattr(item, "raw_text_content", None)

        if isinstance(text, str) and text.strip():
            self._save("interviewer", text)

    def close(self):
        """No persistent database connection is held by this recorder."""
        self.enabled = False
