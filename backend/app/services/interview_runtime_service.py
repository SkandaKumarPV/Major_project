
from uuid import uuid4

from sqlalchemy import func, text

from backend.app.database.database import SessionLocal
from backend.app.database.resume_database import ResumeSessionLocal
from backend.app.database.resume_models import (
    CandidateResume,
    InterviewSessionRecord,
    InterviewTranscriptMessage,
)

from backend.app.services.interview_session_service import (
    mark_interview_started,
    update_interview_progress,
)

from backend.app.services.resume_discussion_service import (
    ResumeDiscussionService,
    ResumeDiscussionStage,
)

from backend.app.services.technical_interview_service import (
    TechnicalInterviewService,
)

from backend.app.services.question_bank_service import (
    QuestionBankService,
)


STAGE_2_TRANSITION_MESSAGE = (
    "Thank you for sharing that. That completes the introduction "
    "and project discussion. We will now move on to the technical "
    "interview."
)


class InterviewRuntimeError(Exception):
    """Raised when a persistent interview cannot be initialized."""


class InterviewRuntimeService:
    """
    Backend-owned interview runtime.

    Stage 1:
        Introduction and resume/project discussion.

    Stage 2:
        Adaptive three-question technical interview.

    Responsibilities:
        - Load persistent interview state.
        - Route candidate turns to the active stage.
        - Persist transcript messages.
        - Persist structured interview progress.
        - Restore the latest interviewer prompt on reconnect.
        - Prevent duplicate transcript entries.
    """

    def __init__(self, room_name: str, llm_provider):
        self.room_name = room_name
        self.llm_provider = llm_provider

        self.session_id = None
        self.candidate_id = None

        self.discussion = None
        self.technical_interview = None

        self.resume_data = None
        self.role_data = None

        self._load_runtime()

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def _load_runtime(self):
        with ResumeSessionLocal() as resume_db:
            interview = (
                resume_db.query(InterviewSessionRecord)
                .filter(
                    InterviewSessionRecord.room_name == self.room_name
                )
                .one_or_none()
            )

            if interview is None:
                raise InterviewRuntimeError(
                    f"No interview record exists for room {self.room_name}."
                )

            if interview.status == "ended":
                raise InterviewRuntimeError(
                    "This interview has already ended."
                )

            if not interview.resume_id:
                raise InterviewRuntimeError(
                    "The interview has no selected resume."
                )

            resume = (
                resume_db.query(CandidateResume)
                .filter(
                    CandidateResume.id == interview.resume_id,
                    CandidateResume.candidate_id == interview.candidate_id,
                )
                .one_or_none()
            )

            if resume is None:
                raise InterviewRuntimeError(
                    "The selected resume could not be found."
                )

            resume_data = resume.structured_data

            if not isinstance(resume_data, dict):
                raise InterviewRuntimeError(
                    "The selected resume has no valid extracted data."
                )

            self.resume_data = resume_data
            self.role_data = self._load_role(interview.role_id)

            self.session_id = interview.id
            self.candidate_id = interview.candidate_id

            transcript = self._load_transcript(
                resume_db,
                interview.id,
                interview.candidate_id,
            )

            structured_memory = interview.structured_memory or {}

            stage_state = structured_memory.get(
                "resume_discussion",
                {},
            )

            technical_state = structured_memory.get(
                "technical_interview",
                {},
            )

            self.discussion = ResumeDiscussionService(
                llm_provider=self.llm_provider,
                resume_data=self.resume_data,
                role_data=self.role_data,
                conversation_history=transcript,
                initial_state=stage_state,
            )

            if (
                interview.current_stage
                == ResumeDiscussionStage.TECHNICAL_INTERVIEW.value
            ):
                self._create_technical_service(
                    initial_state=technical_state,
                    history=transcript,
                )

            mark_interview_started(
                resume_db,
                session_id=interview.id,
                candidate_id=interview.candidate_id,
            )

    # =========================================================
    # ROLE LOADING
    # =========================================================

    def _load_role(self, role_id) -> dict:
        """Resolve the selected role using its stored database ID."""

        if role_id is None:
            raise InterviewRuntimeError(
                "The interview session has no selected role."
            )

        with SessionLocal() as role_db:
            role = (
                role_db.execute(
                    text(
                        "SELECT id, role_name, role_details "
                        "FROM roles WHERE CAST(id AS TEXT) = :role_id"
                    ),
                    {"role_id": str(role_id)},
                )
                .mappings()
                .first()
            )

            if role is None:
                raise InterviewRuntimeError(
                    f"Selected role ID {role_id!r} was not found "
                    "in the role database."
                )

            technologies = (
                role_db.execute(
                    text(
                        "SELECT technology FROM role_technologies "
                        "WHERE role_id = :role_id ORDER BY id"
                    ),
                    {"role_id": role["id"]},
                )
                .scalars()
                .all()
            )

            return {
                "id": str(role["id"]),
                "role_name": role["role_name"],
                "role_details": role["role_details"],
                "technologies": list(technologies),
            }

    # =========================================================
    # TRANSCRIPT LOADING
    # =========================================================

    @staticmethod
    def _load_transcript(
        db,
        session_id,
        candidate_id,
    ) -> list:
        from backend.app.services.interview_session_service import (
            get_interview_transcript,
        )

        messages = get_interview_transcript(
            db,
            session_id=session_id,
            candidate_id=candidate_id,
        )

        history = []

        for message in messages:
            speaker = message.speaker

            if speaker in {"assistant", "interviewer"}:
                speaker = "interviewer"

            elif speaker == "candidate":
                speaker = "candidate"

            else:
                continue

            history.append({
                "speaker": speaker,
                "text": message.message_text,
            })

        return history

    @staticmethod
    def _normalize_history(history):
        """Normalize in-memory messages before transcript persistence."""

        normalized = []

        for item in history or []:
            if not isinstance(item, dict):
                continue

            speaker = item.get("speaker")
            message_text = item.get("text")

            if speaker in {"assistant", "interviewer"}:
                speaker = "interviewer"

            elif speaker == "candidate":
                speaker = "candidate"

            else:
                continue

            if not isinstance(message_text, str):
                continue

            message_text = message_text.strip()

            if not message_text:
                continue

            normalized.append({
                "speaker": speaker,
                "text": message_text,
            })

        return normalized

    # =========================================================
    # TRANSCRIPT PERSISTENCE
    # =========================================================

    def _persist_transcript_suffix(self, history):
        """
        Persist messages missing from the database transcript.

        The existing database transcript must match the beginning
        of the in-memory conversation history.

        Only the missing suffix is inserted.

        This supports the case where LiveKit has already persisted
        a candidate transcript before runtime answer processing.
        """

        normalized_history = self._normalize_history(history)

        if not normalized_history:
            return

        with ResumeSessionLocal() as db:
            interview = (
                db.query(InterviewSessionRecord)
                .filter(
                    InterviewSessionRecord.id == self.session_id,
                    InterviewSessionRecord.candidate_id == self.candidate_id,
                )
                .one_or_none()
            )

            if interview is None:
                raise InterviewRuntimeError(
                    "Interview session disappeared while saving transcript."
                )

            if interview.status == "ended":
                raise InterviewRuntimeError(
                    "Cannot save transcript to an ended interview."
                )

            existing_rows = (
                db.query(InterviewTranscriptMessage)
                .filter(
                    InterviewTranscriptMessage.interview_session_id
                    == self.session_id
                )
                .order_by(
                    InterviewTranscriptMessage.sequence_number.asc()
                )
                .all()
            )

            existing_history = []

            for row in existing_rows:
                speaker = row.speaker

                if speaker in {"assistant", "interviewer"}:
                    speaker = "interviewer"

                existing_history.append({
                    "speaker": speaker,
                    "text": row.message_text.strip(),
                })

            # Verify that the database transcript is a prefix
            # of the runtime's current conversation history.
            if len(existing_history) > len(normalized_history):
                raise InterviewRuntimeError(
                    "Persisted transcript contains more messages than "
                    "the runtime conversation history."
                )

            for index, existing in enumerate(existing_history):
                expected = normalized_history[index]

                if (
                    existing["speaker"] != expected["speaker"]
                    or existing["text"] != expected["text"]
                ):
                    raise InterviewRuntimeError(
                        "Persisted transcript and runtime conversation "
                        f"history diverged at message {index + 1}."
                    )

            missing_messages = normalized_history[
                len(existing_history):
            ]

            if not missing_messages:
                return

            current_max = (
                db.query(
                    func.max(
                        InterviewTranscriptMessage.sequence_number
                    )
                )
                .filter(
                    InterviewTranscriptMessage.interview_session_id
                    == self.session_id
                )
                .scalar()
            )

            next_sequence = (current_max or 0) + 1

            try:
                for offset, item in enumerate(missing_messages):
                    db.add(
                        InterviewTranscriptMessage(
                            id=str(uuid4()),
                            interview_session_id=self.session_id,
                            sequence_number=next_sequence + offset,
                            speaker=item["speaker"],
                            message_text=item["text"],
                        )
                    )

                db.commit()

            except Exception:
                db.rollback()
                raise

    # =========================================================
    # TECHNICAL INTERVIEW SERVICE
    # =========================================================

    def _create_technical_service(
        self,
        initial_state=None,
        history=None,
    ):
        """
        Build Stage 2.

        Main questions come from the role question bank.
        Follow-ups are generated by the LLM.
        """

        def select_question(difficulty, excluded_ids):
            with SessionLocal() as role_db:
                service = QuestionBankService(role_db)

                return service.select_random_unused_question(
                    self.role_data["role_name"],
                    difficulty,
                    excluded_ids=excluded_ids,
                )

        conversation_history = (
            history
            if history is not None
            else self.discussion.conversation_history
        )

        self.technical_interview = TechnicalInterviewService(
            llm_provider=self.llm_provider,
            question_selector=select_question,
            role_data=self.role_data,
            resume_data=self.resume_data,
            initial_state=initial_state or {},
            conversation_history=conversation_history,
        )

    def _ensure_technical_service(self):
        """Restore Stage 2 service if it has not been initialized."""

        if self.technical_interview is not None:
            return

        with ResumeSessionLocal() as db:
            record = (
                db.query(InterviewSessionRecord)
                .filter(
                    InterviewSessionRecord.id == self.session_id,
                    InterviewSessionRecord.candidate_id == self.candidate_id,
                )
                .one_or_none()
            )

            if record is None:
                raise InterviewRuntimeError(
                    "Interview session could not be restored."
                )

            state = (
                record.structured_memory or {}
            ).get("technical_interview", {})

        self._create_technical_service(
            initial_state=state,
            history=self.discussion.conversation_history,
        )

    # =========================================================
    # START / RECONNECT
    # =========================================================

    def start(self) -> str:
        """
        Start the interview or replay the latest committed prompt.

        Reconnect never generates a replacement question when an
        active question already exists.
        """

        if self.discussion.stage == ResumeDiscussionStage.NOT_STARTED:
            opening = self.discussion.start()

            self._persist_progress()

            return opening

        if (
            self.discussion.stage
            == ResumeDiscussionStage.TECHNICAL_INTERVIEW
        ):
            self._ensure_technical_service()

            state = self.technical_interview.export_state()

            # Stage 2 reconnect: replay the exact latest interviewer
            # message. This includes the Stage 1 transition message
            # combined with the first technical question.
            if state.get("current_question"):
                for item in reversed(
                    self.technical_interview.conversation_history
                ):
                    if item.get("speaker") == "interviewer":
                        return item.get("text", "")

            # No active question exists yet.
            prompt = self.technical_interview.start()

            self._persist_technical_progress()

            return prompt

        # Stage 1 reconnect.
        for item in reversed(
            self.discussion.conversation_history
        ):
            if item.get("speaker") == "interviewer":
                return item.get("text", "")

        raise InterviewRuntimeError(
            "Interview was already started, but no previous "
            "interviewer prompt exists."
        )

    # =========================================================
    # CANDIDATE ANSWER ROUTING
    # =========================================================

    def process_candidate_answer(
        self,
        candidate_answer: str,
    ) -> str:
        """Route one finalized candidate turn to the active stage."""

        if (
            not isinstance(candidate_answer, str)
            or not candidate_answer.strip()
        ):
            raise InterviewRuntimeError(
                "Candidate answer cannot be empty."
            )

        candidate_answer = candidate_answer.strip()

        # -----------------------------------------------------
        # STAGE 2
        # -----------------------------------------------------

        if (
            self.discussion.stage
            == ResumeDiscussionStage.TECHNICAL_INTERVIEW
        ):
            self._ensure_technical_service()

            response = self.technical_interview.process_answer(
                candidate_answer
            )

            self._persist_technical_progress()

            return response

        # -----------------------------------------------------
        # STAGE 1
        # -----------------------------------------------------

        result = self.discussion.process_answer(
            candidate_answer
        )

        # Stage 1 completed.
        if result is None:
            # Save Stage 1 state before initializing Stage 2.
            self._persist_progress()

            self._create_technical_service(
                initial_state={},
                history=self.discussion.conversation_history,
            )

            first_question = self.technical_interview.start()

            # The transition and first database-selected question
            # are delivered as one spoken interviewer message.
            combined = (
                f"{STAGE_2_TRANSITION_MESSAGE} "
                f"{first_question}"
            )

            history = self.technical_interview.conversation_history

            if (
                history
                and history[-1].get("speaker") == "interviewer"
            ):
                history[-1]["text"] = combined

            else:
                history.append({
                    "speaker": "interviewer",
                    "text": combined,
                })

            self._persist_technical_progress()

            return combined

        self._persist_progress()

        return result

    # =========================================================
    # STAGE 2 PROGRESS PERSISTENCE
    # =========================================================

    def _persist_technical_progress(self):
        """Persist Stage 2 transcript and structured progress."""

        if self.technical_interview is None:
            return

        state = self.technical_interview.export_state()

        # Persist the conversation before updating structured progress.
        self._persist_transcript_suffix(
            self.technical_interview.conversation_history
        )

        with ResumeSessionLocal() as db:
            interview = (
                db.query(InterviewSessionRecord)
                .filter(
                    InterviewSessionRecord.id == self.session_id,
                    InterviewSessionRecord.candidate_id == self.candidate_id,
                )
                .one_or_none()
            )

            if interview is None:
                raise InterviewRuntimeError(
                    "Interview session disappeared while saving Stage 2 progress."
                )

            memory = dict(interview.structured_memory or {})
            memory["technical_interview"] = state

            completed_stages = list(
                interview.completed_stages or []
            )

            if (
                state["stage_complete"]
                and "technical_interview" not in completed_stages
            ):
                completed_stages.append("technical_interview")

            current_question = state.get("current_question") or {}

            update_interview_progress(
                db,
                session_id=self.session_id,
                candidate_id=self.candidate_id,
                current_stage=(
                    "completed"
                    if state["stage_complete"]
                    else ResumeDiscussionStage.TECHNICAL_INTERVIEW.value
                ),
                current_main_question_id=(
                    str(current_question.get("id"))
                    if current_question
                    else None
                ),
                used_main_question_ids=(
                    state["used_main_question_ids"]
                ),
                follow_up_count=(
                    state["current_follow_up_count"]
                ),
                completed_question_ids=(
                    state["completed_main_question_ids"]
                ),
                completed_stages=completed_stages,
                structured_memory=memory,
            )

    # =========================================================
    # STAGE 1 PROGRESS PERSISTENCE
    # =========================================================

    def _persist_progress(self):
        """Persist Stage 1 transcript and structured progress."""

        state = self.discussion.export_state()

        self._persist_transcript_suffix(
            self.discussion.conversation_history
        )

        with ResumeSessionLocal() as db:
            interview = (
                db.query(InterviewSessionRecord)
                .filter(
                    InterviewSessionRecord.id == self.session_id,
                    InterviewSessionRecord.candidate_id == self.candidate_id,
                )
                .one_or_none()
            )

            if interview is None:
                raise InterviewRuntimeError(
                    "Interview session disappeared while saving progress."
                )

            memory = dict(interview.structured_memory or {})
            memory["resume_discussion"] = state

            completed_stages = list(
                interview.completed_stages or []
            )

            if (
                self.discussion.stage
                == ResumeDiscussionStage.TECHNICAL_INTERVIEW
                and "resume_discussion" not in completed_stages
            ):
                completed_stages.append("resume_discussion")

            update_interview_progress(
                db,
                session_id=self.session_id,
                candidate_id=self.candidate_id,
                current_stage=self.discussion.stage.value,
                follow_up_count=(
                    self.discussion.cross_question_count
                ),
                completed_stages=completed_stages,
                structured_memory=memory,
            )
