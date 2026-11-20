
# CAREER ARENA — Project Context

**Project title:** CAREER ARENA: Gamified AI-Based Recruitment and Interview Simulation

**Project type:** Final-year Computer Science project

**Current development stage:** Phase 2 — Milestone 2.7 (Full Integration and Regression Verification)

**Current milestone objective:** Verify and stabilize the existing implementation. Do not introduce new product features.

---

# 1. Project Overview

CAREER ARENA is an AI-based recruitment and interview simulation platform designed to recreate the experience of participating in a real recruitment process.

The platform uses an AI interviewer to conduct a structured, role-specific interview with a candidate. It considers the candidate's resume, selected job role and previous answers to guide the interview.

The objective is to simulate an interview experience and provide evidence-based feedback after the interview. It is not intended to be a consultancy platform or a tool that teaches candidates how to pass interviews.

The current implementation focuses on a single-candidate AI interview workflow.

---

# 2. Current Product Scope

The active implementation includes:

1. Guest candidate identity.
2. Resume upload and extraction.
3. Role selection.
4. Persistent interview session creation.
5. AI-initiated interview.
6. Introduction and resume discussion.
7. Adaptive technical interview.
8. Real-time voice interaction.
9. Complete transcript persistence.
10. Separate resume and interview evaluation.
11. Candidate interview history and report access.

The current initial role is **Generative AI Engineer**.

The role question bank is shared across candidates. Candidate resumes, sessions, transcripts and reports are candidate-specific.

---

# 3. Candidate Workflow

The intended candidate workflow is:

```text
Candidate Opens Application
          |
          v
Guest Identity
          |
          v
Candidate Dashboard
          |
          v
Upload Resume
          |
          v
Resume Extraction and Processing
          |
          v
Select Job Role
          |
          v
Create Interview Session
          |
          v
Join LiveKit Room
          |
          v
AI Initiates Interview
          |
          v
Stage 1: Introduction and Resume Discussion
          |
          v
Stage 2: Technical Interview
          |
          v
Three Main Technical Questions
          |
          v
Stage 3: Conclusion
          |
          v
Persist Complete Transcript
          |
          v
Generate Two Independent Evaluations
          |
          v
Candidate Interview History
          |
          v
View Evaluation Report
```

A new interview must be created only through an explicit user action. Ordinary dashboard visits, page refreshes and greetings must not silently create or restart interviews.

---

# 4. Interview Design

The backend owns the authoritative interview state.

The LLM assists with conversation and contextual question generation, but it must not independently change question counts, bypass stages or override backend limits.

## 4.1 AI-initiated introduction

The AI interviewer must always initiate the interview with a spoken opening.

It then asks the candidate to introduce themselves.

The opening must not be repeated merely because the frontend reconnects or refreshes.

## 4.2 Stage 1 — Introduction and resume discussion

The interviewer uses the candidate's resume and selected job role to guide the discussion.

The stage covers relevant background, projects, experience and role-related information.

It permits a maximum of two contextual cross-questions.

After Stage 1 is completed, the backend transitions to the technical interview.

## 4.3 Stage 2 — Adaptive technical interview

The technical interview consists of exactly three main questions.

| Main question | Difficulty rule |
|---|---|
| Question 1 | Easy |
| Question 2 | Adaptive |
| Question 3 | Adaptive |

The main questions come from the selected role's shared question bank.

The next main question is selected dynamically after the previous question and its applicable follow-ups have been completed.

Each main question can have a maximum of two contextual follow-ups.

Follow-ups are generated dynamically based on the candidate's answer. They are not prewritten question-bank entries.

The backend enforces:

- Exactly three main questions for a completed technical interview.
- No repeated main question IDs within a session.
- No more than two follow-ups per main question.
- No premature difficulty transition.
- No counting greetings or ordinary candidate questions as main technical questions.
- No LLM-controlled modification of authoritative interview state.

## 4.4 Stage 3 — Conclusion

After the three main questions and applicable follow-ups are complete, the interviewer concludes the session.

The backend marks the interview completed and makes it eligible for evaluation.

An interrupted or incomplete interview must not receive a completed evaluation report.

---

# 5. Voice Interaction Requirements

The existing voice architecture must be preserved.

## Voice pipeline

```text
Candidate Speech
       |
       v
Deepgram STT
       |
       v
Backend Interview Runtime
       |
       v
Configurable LLM
       |
       v
Cartesia TTS
       |
       v
Candidate Hears AI
```

LiveKit provides real-time room communication and hosts the agent session.

Silero VAD is used for voice activity detection.

## Half-duplex behaviour

### While AI speaks

- AI audio is enabled.
- Candidate microphone is muted.
- Candidate silence detection is inactive.

### While candidate speaks

- Candidate microphone is enabled.
- AI does not speak over the candidate.
- Deepgram processes speech.
- Candidate transcript is captured.

### After candidate speech

- A 10-second silence timeout is used by default.
- New speech resets the timeout.
- When the timeout expires, the candidate turn is finalized.
- The backend processes the answer and generates the next response.

The silence timeout is configurable through `SILENCE_TIMEOUT_SECONDS`.

These requirements are existing project behaviour to preserve and verify, not a request to redesign the voice pipeline.

---

# 6. Resume Processing

Candidates upload PDF or DOCX resumes.

The backend validates and extracts resume content, then stores:

- Original resume file in private storage.
- Extracted text.
- Structured resume information.
- Candidate ownership association.
- File metadata.

Structured resume information is used to support role matching, resume discussion and evaluation.

Resume facts must not be invented. Evaluation claims must be grounded in available resume evidence.

The candidate-facing API must not expose raw extraction data, private storage keys or filesystem paths.

---

# 7. Role Question Bank

The role question bank is stored separately from candidate interview data.

Database:

`role_question_bank.db`

Initial role:

`Generative AI Engineer`

Expected question distribution:

| Difficulty | Questions |
|---|---:|
| Easy | 10 |
| Medium | 10 |
| Hard | 10 |
| Total | 30 |

The question bank stores role information, role technologies and main question text with difficulty.

It must not store:

- Answers.
- Answer explanations.
- Hints.
- Scoring rubrics.
- Prewritten follow-ups.
- Candidate-specific assessments.
- Interview transcripts.

The question bank is a shared source of main technical questions. Follow-up questions are generated dynamically during interviews.

The expected distribution must be verified against the actual database.

---

# 8. Candidate Identity and Data Ownership

The current candidate workflow uses guest identity.

Guest identity is created by the backend. The access token is hashed before being stored.

Candidate-specific data is associated with the guest candidate.

The interview database stores:

- Guest candidates.
- Candidate resumes.
- Interview sessions.
- Transcript messages.
- Evaluation reports.

Ownership must be checked by the backend for all candidate-specific operations.

A candidate must only be able to access their own:

- Resume records.
- Interview sessions.
- Transcript messages.
- Evaluation reports.

Knowing another candidate's session ID or resume ID must not grant access.

Registered authentication and account linking are not part of the current milestone.

---

# 9. Transcript and Interview State

The full transcript is persisted independently of compact interview memory.

The transcript includes the complete chronological conversation:

- AI opening.
- Candidate introduction.
- Resume discussion.
- Resume cross-questions.
- Main technical questions.
- Technical follow-ups.
- Candidate answers.
- Candidate questions.
- Interview conclusion.

Structured memory may summarize earlier conversation context for LLM requests. It must not replace or truncate the persisted transcript.

Persistent interview state includes information such as:

- Current stage.
- Current main question.
- Used main question IDs.
- Follow-up count.
- Completed question IDs.
- Completed stages.
- Structured memory.
- Session status and timestamps.

Reconnects must restore the existing interview state rather than silently start a new interview.

Transcript recording must not create duplicate committed messages after retries or reconnects.

---

# 10. Evaluation and Reports

Milestone 2.6 added two independent evaluations.

## 10.1 Resume suitability

The resume evaluation compares structured resume evidence with the selected role's requirements.

It produces:

- Resume score out of 10.
- Evidence-backed strengths.
- Experience and project alignment.
- Missing or weakly evidenced skills.
- Improvement areas.
- Score rationale.

## 10.2 Interview performance

The interview evaluation uses the complete ordered transcript, selected role requirements and stored technical turn assessments.

It produces:

- Interview score out of 10.
- Technical strengths.
- Weak or incorrect answers.
- Missing technical concepts.
- Answer-by-answer feedback.
- Technical justification.
- Recommendations.

## 10.3 Score separation

The two scores must remain independent.

There is no combined or aggregate score.

The report must not expose internal prompts, raw resume extraction, private storage paths or internal question-selection data.

Only completed interviews with three distinct completed main technical questions are eligible for completed evaluation.

---

# 11. Technology Stack

## Frontend

- React
- TypeScript
- Vite
- LiveKit Client
- Vitest

## Backend

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Pytest

## Voice and AI

- LiveKit Agents
- Deepgram STT
- Silero VAD
- Configurable LLM provider
- Cartesia TTS

The configured LLM provider and model are controlled through backend environment variables.

Do not hardcode secrets or assume a specific runtime LLM provider when configuration supports alternatives.

---

# 12. Database Separation

Two SQLite databases are used.

| Database | Purpose |
|---|---|
| `role_question_bank.db` | Shared roles, technologies and main technical questions |
| `interview_data.db` | Guest candidates, resumes, sessions, transcripts and reports |

The shared role database must not contain candidate-specific information.

The interview database must not become the source of shared role-question content.

The configured database URLs are:

- `DATABASE_URL`
- `INTERVIEW_DATABASE_URL`

---

# 13. Project Development Principles

All future approved implementation work must follow these principles:

1. Use Test-Driven Development where code changes are required.
2. Keep functionality modular and replaceable.
3. Preserve the approved architecture and technology choices.
4. Prefer existing libraries and public SDKs over unnecessary custom implementations.
5. Do not write implementation code during brainstorming or before the user approves a plan.
6. Inspect existing files before modifying them.
7. Make changes only within the approved milestone scope.
8. Avoid unnecessary refactoring of working components.
9. Update relevant documentation when implementation changes.
10. Report actual test results; do not claim unexecuted tests passed.
11. Keep credentials and candidate data private.
12. Do not add unapproved features.

When code is requested, provide complete updated files where practical rather than disconnected snippets.

---

# 14. Current Milestone — 2.7

## Objective

Complete full Phase 2 integration and regression verification.

This is a verification and documentation milestone, not a feature-development milestone.

## Required checks

### Candidate workflow
- Dashboard and resume upload.
- Resume extraction.
- Explicit interview creation.
- AI-initiated opening.
- Introduction and resume discussion.
- Three adaptive technical questions.
- Contextual follow-ups.
- Conclusion.
- Transcript persistence.
- Separate evaluations.
- Report and interview history.

### Database
- Actual schemas.
- Actual question counts and difficulty distribution.
- Question-bank content restrictions.
- Transcript ordering.
- Evaluation report associations.
- Candidate ownership.

### Reliability
- No duplicate interview creation.
- No repeated opening after reconnect.
- Persistent state restoration.
- Main-question and follow-up limits.
- No repeated main questions.
- Candidate questions do not consume question count.
- Complete transcript despite LLM context summarization.
- Incomplete interviews cannot generate completed reports.

### Voice regression
- LiveKit connection.
- Deepgram transcription.
- Configurable LLM.
- Cartesia speech generation.
- AI speaks first.
- Half-duplex microphone behaviour.
- 10-second silence handling.
- Repeated conversation turns.
- Session termination.

### Documentation
Update:

- `README.md`
- `ARCHITECTURE.md`
- `PROJECT_CONTEXT.md`
- `PROJECT_RULES.md`
- `IMPLEMENTATION_STATUS.md`
- `LATEST_HANDOFF.md`
- Append to `PROJECT_DEVELOPMENT_HISTORY.md` without deleting earlier history.

## Code-change policy

Do not implement new features during Milestone 2.7.

Only change application code when a specific defect is found and supported by source inspection or a failing test.

Do not redesign working systems or introduce new dependencies without a demonstrated need.

## Completion condition

Milestone 2.7 is complete only after the integration and regression checks have been executed and their results documented.

Live voice acceptance must be explicitly identified as pending if it cannot be performed in the verification environment.

---

# 15. Explicitly Out of Scope

Do not begin the following as part of Milestone 2.7:

- Login and signup.
- Registered authentication.
- Account linking.
- Group Discussion stage.
- Multiplayer recruitment.
- Shared candidate waiting rooms.
- Live candidate observation.
- Leaderboards.
- Additional assessment stages.
- Unapproved gamification features.
- New job-role catalogues.
- Unapproved UI redesign.
- Replacement of the existing voice architecture.

These may be considered in future milestones only after the current milestone is closed and the user approves the next scope.

---

# 16. Current Handoff

The project has an existing Phase 1 voice-interview foundation and Phase 2 persistent interview workflow.

Milestone 2.5 added adaptive three-question technical interviewing.

Milestone 2.6 added separate resume suitability and interview performance reports.

The supplied Milestone 2.6 documentation records 38 focused backend tests passing in its implementation environment, while full backend/frontend verification and live voice acceptance were pending there.

The project owner subsequently reported the following Windows results:

- Backend: 278 passed, 58 warnings.
- Frontend: 43 passed.
- Frontend production build: successful.

These are previously reported results and must not be represented as newly executed Milestone 2.7 results.

The next task is to inspect the existing implementation file by file, verify the full integration and correct only confirmed defects.

**Stop after Milestone 2.7 verification and final handoff.**
