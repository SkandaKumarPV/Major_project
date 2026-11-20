
# CAREER ARENA — Project Development Rules

**Project:** CAREER ARENA: Gamified AI-Based Recruitment and Interview Simulation

**Current milestone:** Phase 2 — Milestone 2.7

**Purpose:** Define mandatory rules for planning, implementation, testing, integration and documentation.

---

# 1. General Development Rules

1. Understand the existing project before proposing or implementing changes.
2. Inspect existing source files before modifying them.
3. Preserve the original project objectives and approved architecture.
4. Do not introduce features that are outside the current approved milestone.
5. Prefer existing libraries, SDKs and services over unnecessary custom implementations.
6. Keep components modular, independent and replaceable.
7. Avoid unnecessary refactoring of working code.
8. Maintain consistency with the existing coding style and project structure.
9. Keep documentation synchronized with actual implementation.
10. Clearly distinguish implemented, tested, verified and pending functionality.

---

# 2. Approval Before Implementation

This is a mandatory rule.

- Do not write application code during brainstorming.
- Do not begin implementation before the user explicitly approves the proposed plan.
- First understand the requirement.
- Inspect the existing implementation.
- Explain the proposed approach and any architectural changes.
- Identify the files that would need modification.
- Wait for approval before starting implementation.

Do not interpret a request to discuss, analyze, review or plan a feature as permission to implement it.

For an already approved implementation task, work within the approved scope without requesting approval repeatedly for every ordinary implementation step.

---

# 3. Test-Driven Development (TDD)

Use a Test-Driven Development approach whenever application code must be changed.

The expected process is:

1. Understand the required behaviour.
2. Inspect existing tests and implementation.
3. Identify the missing or incorrect behaviour.
4. Write or update a test that demonstrates the expected behaviour.
5. Run the test and confirm the failure when practical.
6. Implement the smallest appropriate change.
7. Run the relevant test again.
8. Run related regression tests.
9. Run the broader test suite when appropriate.
10. Report the actual results.

Do not remove or weaken an existing test merely to make the suite pass.

Do not claim a test passed unless it was actually executed successfully.

If an external service, credential or environment dependency prevents execution, report that limitation explicitly.

---

# 4. Modular and Replaceable Architecture

Each functionality should remain independently maintainable and replaceable.

Examples include:

- Guest identity.
- Resume extraction.
- Resume storage.
- Role question bank.
- Interview session management.
- Resume discussion.
- Technical interview.
- Transcript recording.
- Evaluation.
- LiveKit integration.
- Speech-to-text.
- Text-to-speech.
- LLM provider.

Avoid combining unrelated responsibilities into a single large service.

Keep API routing, business logic, persistence and external-service integration separated.

Do not introduce unnecessary dependencies between independent modules.

---

# 5. Architecture Preservation

The approved architecture uses:

## Frontend

- React.
- TypeScript.
- Vite.
- LiveKit Client.

## Backend

- Python.
- FastAPI.
- SQLAlchemy.
- SQLite.

## Voice and AI

- LiveKit Agents.
- Deepgram STT.
- Silero VAD.
- Configurable LLM provider.
- Cartesia TTS.

Mandatory constraints:

1. Preserve the existing LiveKit voice architecture.
2. Do not replace LiveKit with another voice orchestration framework.
3. Preserve the existing speech-processing pipeline unless a verified defect requires a change.
4. Keep LLM provider configuration replaceable.
5. Keep backend interview state authoritative.
6. Keep database persistence independent of frontend state.
7. Do not hardcode API credentials.
8. Do not introduce a new framework without explaining the need and obtaining approval.

---

# 6. Backend Ownership of Interview Logic

The backend is the source of truth for interview progress.

The LLM must not independently control:

- Interview session creation.
- Interview session identity.
- Stage transitions.
- Main-question count.
- Follow-up count.
- Used main question IDs.
- Completed question IDs.
- Interview completion.
- Evaluation eligibility.

The backend validates LLM-generated decisions before applying them.

The frontend must not be trusted to enforce interview limits or candidate ownership.

---

# 7. Interview Behaviour Rules

The current approved interview design must be preserved.

## Stage 1 — Introduction and resume discussion

- The AI must initiate the interview with a spoken opening.
- The candidate must be asked to introduce themselves.
- Resume discussion must use the selected resume and role.
- A maximum of two contextual cross-questions is permitted.
- Reconnecting must not repeat the opening or restart the stage.

## Stage 2 — Technical interview

- Exactly three main technical questions are required.
- The first main question must be Easy.
- The next two main questions are selected adaptively.
- The next main question is selected dynamically after the previous question and its applicable follow-ups.
- Each main question allows at most two contextual follow-ups.
- Main questions must not repeat within a session.
- Main questions must come from the selected role's question bank.
- Follow-ups are dynamically generated, not prewritten question-bank entries.
- Candidate questions do not consume the main-question count.
- The backend enforces all question and follow-up limits.

## Stage 3 — Conclusion

- The AI concludes after the technical interview is completed.
- The backend records the completed state.
- Evaluation is generated only for eligible completed interviews.
- Incomplete or interrupted interviews must not receive completed evaluation reports.

---

# 8. Voice Interaction Rules

Preserve the existing half-duplex voice design.

## While AI speaks

- Candidate microphone is muted.
- AI audio is enabled.
- Candidate silence detection is inactive.

## While candidate speaks

- Candidate microphone is enabled.
- AI does not speak over the candidate.
- Deepgram processes candidate speech.
- Candidate transcript is captured.

## Silence handling

- The default silence timeout is 10 seconds.
- New candidate speech resets the timeout.
- The timeout is cancelled while the AI speaks.
- When the timeout expires, the candidate turn is finalized.
- The finalized answer is processed by the backend.

Do not change the turn-taking design or timeout behaviour without an identified defect and an approved reason.

---

# 9. Database Rules

The project uses two separate SQLite databases.

## Shared role question bank

`role_question_bank.db`

Stores:

- Roles.
- Role details.
- Role technologies.
- Main technical questions.
- Main-question difficulty.

Expected initial question distribution:

- 10 Easy.
- 10 Medium.
- 10 Hard.

The question bank must not contain:

- Answers.
- Answer explanations.
- Hints.
- Scoring rubrics.
- Prewritten follow-ups.
- Candidate-specific assessments.
- Interview transcripts.

## Candidate interview database

`interview_data.db`

Stores:

- Guest candidates.
- Candidate resumes.
- Interview sessions.
- Transcript messages.
- Evaluation reports.

Do not mix candidate-specific data into the shared role database.

Do not move shared role-question data into candidate-specific records without an approved architectural reason.

---

# 10. Candidate Privacy and Ownership

Candidate-specific records must always be accessed through backend ownership checks.

A candidate can access only their own:

- Resumes.
- Interview sessions.
- Transcripts.
- Evaluation reports.

Never assume that possession of a record ID is sufficient authorization.

The backend must validate candidate ownership for read, update and delete operations.

Private resume storage paths and internal storage keys must not be exposed through candidate-facing APIs.

Do not expose:

- Raw resume extraction.
- Internal prompts.
- Internal orchestration state.
- Private storage paths.
- API credentials.
- Other candidates' information.
- Internal question-selection details.

---

# 11. Transcript and Memory Rules

The complete transcript must be persisted independently of compact LLM context.

The transcript must preserve the chronological conversation, including:

- AI opening.
- Candidate introduction.
- Resume discussion.
- Cross-questions.
- Main technical questions.
- Follow-ups.
- Candidate answers.
- Candidate questions.
- Conclusion.

Structured memory may summarize previous context to control LLM context size.

However:

- A summary must not replace the complete transcript.
- A summary must not delete earlier transcript messages.
- Reconnects must not create duplicate transcript messages.
- Transcript ordering must be preserved.
- Evaluation must use the required complete interview evidence.

---

# 12. Evaluation Rules

Resume suitability and interview performance are independent evaluations.

## Resume evaluation

- Score is out of 10.
- Use structured resume evidence.
- Compare evidence with selected role requirements.
- Do not invent skills, projects or experience.
- Explain the score using evidence.

## Interview evaluation

- Score is out of 10.
- Use the complete ordered transcript and relevant stored assessments.
- Evaluate technical correctness and answer quality.
- Provide evidence-based feedback.
- Do not invent candidate answers or technical achievements.

## Score separation

- Do not average the two scores.
- Do not introduce an aggregate score.
- Do not expose internal evaluation prompts.
- Do not generate completed reports for incomplete interviews.

---

# 13. Dependencies and External Services

1. Prefer existing project dependencies.
2. Do not add a package when the existing stack already provides the required functionality.
3. Explain the purpose of any new dependency.
4. Avoid unnecessary package upgrades during integration verification.
5. Preserve compatible versions of LiveKit and related SDKs.
6. Keep provider credentials in environment variables.
7. Never include real secrets in source code, documentation or logs.
8. Distinguish a missing external credential from an application defect.

Any dependency removal must be supported by evidence that it is unused and safe to remove.

---

# 14. File Modification Rules

Before changing a file:

1. Read the complete relevant file.
2. Understand its callers and dependencies.
3. Inspect related tests.
4. Identify the exact defect or requirement.
5. Determine whether the change is within approved scope.

When code changes are requested:

- Prefer complete updated files over isolated fragments.
- Preserve unrelated functionality.
- Do not silently omit existing code.
- Explain important changes.
- Include relevant test results.

When documentation changes are requested:

- Preserve historical records.
- Do not claim unverified implementation.
- Use consistent terminology across project documents.
- Keep current status separate from planned work.

---

# 15. Logging and Error Handling

- Do not log API secrets or access tokens.
- Do not log unnecessary raw candidate resume content.
- Do not expose stack traces or internal paths to candidate-facing responses.
- Return clear API errors.
- Preserve useful diagnostic information in backend logs.
- Handle external-service failures without falsely marking an interview completed.
- Do not silently discard transcript messages or interview state.

---

# 16. Scope Control

Only implement functionality explicitly approved for the current milestone.

The following are not part of Milestone 2.7:

- Login and signup.
- Registered authentication.
- Account linking.
- Group Discussion.
- Multiplayer recruitment.
- Shared waiting rooms.
- Leaderboards.
- New assessment stages.
- Additional gamification features.
- Unapproved UI redesign.
- Replacement of the existing voice stack.

Do not begin these features as part of integration verification.

If an out-of-scope issue is discovered, document it and wait for approval rather than implementing it.

---

# 17. Milestone 2.7 Rules

Milestone 2.7 is a verification and stabilization milestone.

The objective is to verify the existing Phase 1 and Phase 2 implementation.

Permitted work:

- Source inspection.
- Database schema and content inspection.
- API integration verification.
- Workflow testing.
- Regression testing.
- Documentation updates.
- Fixing verified integration defects.

Not permitted:

- Adding unrelated features.
- Redesigning the architecture.
- Replacing existing technologies.
- Refactoring working code without a demonstrated need.
- Adding dependencies without justification.

For every discovered issue, record:

1. Affected file or module.
2. Expected behaviour.
3. Actual behaviour.
4. Evidence of the defect.
5. Whether it is in scope.
6. Minimal corrective action.
7. Test used to verify the correction.

If no defect is found, do not make an unnecessary code change.

---

# 18. Test Reporting Rules

Every verification report must distinguish:

- Tests actually executed.
- Tests passed.
- Tests failed.
- Tests skipped.
- Tests blocked by environment or credentials.
- Manual checks completed.
- Manual checks pending.

Do not report a previous test result as a newly executed result.

Do not describe a mocked integration test as proof of a live external-service integration.

Do not claim live voice acceptance unless the actual voice workflow has been tested.

---

# 19. Documentation Maintenance

Maintain the following root-level project documents:

- `README.md`
- `ARCHITECTURE.md`
- `PROJECT_CONTEXT.md`
- `PROJECT_RULES.md`
- `IMPLEMENTATION_STATUS.md`
- `LATEST_HANDOFF.md`
- `PROJECT_DEVELOPMENT_HISTORY.md`

The development history is append-only.

Do not delete or rewrite earlier milestone history when adding a new milestone entry.

Documentation must reflect the actual source code and executed verification results.

---

# 20. Final Rule

**Understand first. Plan second. Obtain approval before implementation. Test changes. Preserve working architecture. Report only verified results.**

For Milestone 2.7, stop after integration verification, confirmed defect fixes, regression testing and final documentation handoff.
