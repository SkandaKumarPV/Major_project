# Phase 2 — Existing Project Audit and Implementation Plan

**Milestone:** 2.0 — Existing Project Audit and Phase 2 Implementation Plan  
**Prepared:** 18 November 2026  
**Audit status:** Evidence-limited; current source repository was not mounted in the audit workspace  
**Implementation status:** No application source code changed; no dependencies installed; no database or migrations created

---

## 1. Executive summary

The available project history describes a Phase 1 application with a React + TypeScript dashboard, a FastAPI backend, a LiveKit Agents worker, Deepgram STT, a configurable HTTP-based LLM provider, Cartesia TTS, half-duplex turn-taking, and a custom 10-second silence timer. The backend was divided into core, service, agent, and API modules. The user reports that the complete Phase 1 interview workflow is now working.

The architecture described in the supplied Phase 1 records is a reasonable base for Phase 2. The strongest reuse opportunity is to keep the existing LiveKit voice path intact and add a separate persisted interview-domain layer around it: shared SQLite databases, a guest identity/ownership service, private resume storage and extraction, a role question-bank repository, an authoritative interview state machine, and reporting/evaluation services.

**Important audit limitation:** the actual Windows project folder (`C:\Users\kumar\Documents\Sem 7\Mp_v2\livekit-voice-agent`) was not available in the current execution workspace. The mounted files consisted of pasted prompts, code excerpts, command output, and test logs; a search for a mounted `livekit-voice-agent` directory found no repository. Consequently, this document distinguishes:

- **Recorded:** explicitly present in supplied code excerpts, command output, or test logs.
- **Reported:** stated by the project owner or described in prior project context, but not independently inspected from current source files.
- **Proposed:** a design recommendation for approval, not an existing implementation.
- **Unverified:** cannot be confirmed without the current source tree or runtime environment.

This is a useful planning baseline, but it is **not a completed source-level audit**. In particular, the current source files, final dependency lock, frontend implementation, environment variable names, and current docs need inspection from the actual project before Milestone 2.1 begins.

## 2. Workspace and repository inventory

### 2.1 What was available for inspection

The audit workspace contained the Phase 2 master context and historical Phase 1 text/log snapshots. It did not contain the project directory, its `.venv`, `node_modules`, `.env`, or the current source tree. No source code in the user's Windows workspace was opened or modified.

### 2.2 Structure recorded in project history

The following root-level files were present in an early `tree /F` snapshot, before the Phase 1 restructuring:

```text
livekit-voice-agent/
├── agent.py
├── graph.py
├── interview_workflow.png
├── pyproject.toml
└── uv.lock
```

The same history records that the Phase 1 backend structure was subsequently created and expanded:

```text
livekit-voice-agent/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── agent/
│   │   └── services/
│   └── tests/
└── frontend/
    └── src/
```

The module inventory below is reported by the Phase 1 implementation context. It is not a substitute for a fresh `tree /F` of the current folder.

| Area | Reported modules / files | Audit assessment |
|---|---|---|
| Backend configuration | `backend/app/core/config.py` | Existing environment-backed settings are reported; exact names/defaults need source inspection. |
| Conversation state | `backend/app/core/conversation_state.py` | Existing Phase 1 conversation state and completed-answer count are reported. |
| Silence detection | `backend/app/core/silence_detector.py` | Existing resettable 10-second silence detector is reported and covered by tests. |
| Agent worker | `backend/app/agent/worker.py` | LiveKit Agents worker, VAD prewarm, manual turn detection, and session creation are reported/tested. |
| Agent session controller | `backend/app/agent/livekit_session_controller.py` | Reported to coordinate speech events, silence timer, transcript events and state changes. |
| LLM provider | `backend/app/services/llm_provider.py` | HTTP `requests` adapter to a configurable chat-completions endpoint is reported. |
| LiveKit LLM adapter | `backend/app/services/livekit_llm.py` | Bridges the configured provider to the LiveKit Agents LLM interface. |
| STT | `backend/app/services/deepgram_service.py` | Deepgram STT factory/service is reported and unit-tested. |
| TTS | `backend/app/services/cartesia_service.py` | Cartesia TTS factory/service is reported and unit-tested. |
| LiveKit room/API service | `backend/app/services/livekit_service.py` | Room creation, candidate token generation, explicit agent dispatch and room deletion are reported and tested. |
| LiveKit event publisher | `backend/app/services/livekit_event_publisher.py` | Reliable JSON data-channel events on topic `interview-events` are reported. |
| HTTP API | `backend/app/api/app.py` | FastAPI health/create/dispatch/delete routes are reported. |
| Backend tests | `backend/tests/test_*.py` | Tests cover the areas listed in Section 8; latest supplied run in the attached history is 72 passed. |
| Frontend protocol | `frontend/src/interviewProtocol.ts` | Status/transcript event parsing and validation are reported; 8 tests passed in a supplied test result. |
| Frontend API | `frontend/src/interviewApi.ts` | API calls for interview create/dispatch/end are reported; current exact tests/results need confirmation. |
| Frontend dashboard | `frontend/src/App.tsx`, `App.css`, `index.css` | Dashboard implementation is reported, but current JSX and interaction logic could not be inspected. |

### 2.3 Legacy repository files requiring disposition

An early root snapshot showed `agent.py` and `graph.py`. An earlier `agent.py` excerpt imported LangChain, a LangChain LiveKit plugin, Cartesia, Deepgram, noise cancellation, Silero, Bey, and `create_workflow` from `graph.py`. The early `pyproject.toml` excerpt also listed LangChain/Chroma/OpenAI-related packages and a `pypdf` dependency.

That snapshot predates the later Phase 1 refactor described in the project history. It is not known whether these files or dependencies remain in the current project, whether they are active, or whether they are obsolete leftovers. Do not remove them based on this report. The current import graph and final `pyproject.toml`/`uv.lock` need to be inspected before deciding whether any legacy files or packages can be safely retired.

## 3. Current Phase 1 architecture and data flow

The following is the Phase 1 data flow reconstructed from project context, endpoint contracts, module names, and test names. It is **reported architecture**, not independently traced from the current source code.

```text
React + TypeScript dashboard
  ├─ POST /api/interviews
  │    └─ FastAPI -> LiveKitService
  │         ├─ creates interview-{UUID} room
  │         └─ returns LiveKit URL, room, participant identity and token
  ├─ connects candidate to LiveKit room
  ├─ POST /api/interviews/{room_name}/dispatch
  │    └─ LiveKitService explicitly dispatches configured agent
  └─ subscribes to LiveKit data topic: interview-events

LiveKit room
  ├─ candidate audio track
  ├─ agent worker receives dispatch
  │    └─ AgentSession
  │         ├─ Silero VAD
  │         ├─ Deepgram STT
  │         ├─ LiveKitLLM -> configurable LLMProvider (HTTP)
  │         └─ Cartesia TTS
  └─ agent/controller publishes status and transcript events

Agent/session controller
  ├─ opens with configured interviewer message
  ├─ manages AI-speaking / candidate-listening phases
  ├─ collects transcript updates
  ├─ resets silence timer when more candidate speech arrives
  ├─ finalizes candidate turn after configured silence
  ├─ submits the finalized candidate answer once to the LLM
  └─ repeats until interview ends

FastAPI DELETE /api/interviews/{room_name}
  └─ LiveKitService deletes room; service closes at API shutdown
```

The reported API contract is:

| Endpoint | Reported behaviour | Response contract recorded in project history |
|---|---|---|
| `GET /health` | Health check | `{"status":"ok"}` |
| `POST /api/interviews` | Create LiveKit room and candidate token | `201`: `{livekit_url, room_name, participant_identity, token}` |
| `POST /api/interviews/{room_name}/dispatch` | Explicitly dispatch interviewer | `202`: `{room_name, agent_name, dispatched}` |
| `DELETE /api/interviews/{room_name}` | End interview by deleting LiveKit room | `204` |

CORS is reported to allow `localhost:5173` and `127.0.0.1:5173`. The exact route implementation, error model, authorization semantics, and shutdown hooks require current-source verification.

## 4. LiveKit Agents and voice pipeline audit

### 4.1 Agent/session lifecycle

**Reported:** the worker builds an `AgentSession`, starts a configured interviewer agent, uses manual turn detection, and is dispatched explicitly after the candidate has joined. The test inventory includes worker prewarm, session construction, worker options, entrypoint startup without duplicate connect, and interviewer instructions.

**Recorded API investigation:** supplied console output from the installed LiveKit Agents package shows `Agent.on_enter()` and `Agent.on_user_turn_completed(...)` hooks, and that `AgentSession.start(...)` is used. Historical investigation of the library also examined session event emissions and session state. This indicates the implementation was adapted to the installed LiveKit API rather than simply retaining the original LangGraph agent.

**Unverified:** current `worker.py` control flow, whether room/participant disconnection reliably ends the session, cleanup of per-session tasks, reconnect behaviour, and whether API termination also cancels the running agent task.

**Phase 2 implication:** keep the worker focused on voice transport/orchestration. Pass a server-issued interview/session identifier into the agent context and route every transcript/turn/completion event to the persisted interview service. Never let the LLM independently decide whether the interview is complete or exceed backend-enforced limits.

### 4.2 Deepgram STT

**Reported configuration:** `livekit.plugins.deepgram.STT` using `model="nova-3"`, `language="en-IN"`, `interim_results=True`, and `punctuate=True`.

**Test evidence:** test names cover API-key requirement, plugin construction, interim transcript enablement, and punctuation enablement.

**Phase 2 implication:** retain interim transcripts for live display if useful, but persist finalized transcript segments/turns as the authoritative record. Store speaker, order, timestamps if available, and final/interim status separately; do not append duplicate interim revisions as separate final turns.

### 4.3 LLM integration and provider abstraction

**Reported:** `LiveKitLLM` adapts the LiveKit Agents LLM protocol to `LLMProvider`. `LLMProvider` uses an HTTP `requests.post` call to a configurable base URL ending in `/chat/completions`, with provider, model, API key, and base URL configured through backend settings. The project history records that `requests` was used instead of the OpenAI SDK after a Python 3.14 `jiter` DLL/import issue, and that a real NVIDIA-compatible endpoint was successfully tested.

**Test evidence:** provider configuration checks, successful response mapping, empty-response handling, LiveKit adapter model selection, latest user message selection, missing-user-context rejection, empty-provider-response rejection, and unsupported tool-call handling.

**Phase 2 implication:** preserve the provider abstraction. Extend the service with task-specific methods or a small application-layer interface for resume extraction, dynamic follow-ups, difficulty recommendations, and evaluation. Keep prompts and provider credentials on the backend. Use structured output validation and deterministic backend validation for every LLM recommendation. Do not couple question selection or session limits to an LLM tool call.

### 4.4 Cartesia TTS

**Reported configuration:** `livekit.plugins.cartesia.TTS` using model `sonic-3` and language `en`.

**Test evidence:** tests cover missing API-key rejection, Cartesia TTS object construction, and plugin usage.

**Phase 2 implication:** retain this TTS integration for spoken interview prompts and follow-ups. Persist the text of every interviewer question/response independently of TTS completion, and define a single session event sequence so that retries or reconnects do not create duplicate spoken questions.

### 4.5 Half-duplex microphone/audio behaviour

**Reported:** the candidate microphone is disabled while the AI is speaking; candidate microphone publishing is enabled while listening; the interviewer does not interrupt candidate speech. Worker tests include `allow_interruptions=False` and manual turn detection. Controller tests check that AI speaking cancels a candidate silence timer and that speaking status is reported.

**Unverified:** the precise frontend API call used to enable/disable local microphone publishing, the treatment of microphone permissions/track reconnect, and whether the backend also rejects or ignores unexpected candidate audio while AI is speaking.

**Phase 2 risk:** the half-duplex rule is important to the existing workflow and should not be rewritten as part of persistence work. Add integration/regression tests for the actual audio-publishing state across AI speaking, candidate listening, candidate speaking, processing, errors and end-of-interview. Ensure the UI's microphone icon reflects the actual LiveKit publication state, not merely a desired state value.

### 4.6 Silence detection and end-of-turn handling

**Reported:** a separate configurable silence detector owns the 10-second answer-completion rule. New speech resets the timer; expiry finalizes one answer; duplicate finalization is prevented. Deepgram endpointing is not intended to finalize a full candidate turn on its own.

**Test evidence:** test inventory covers timeout finalization, timer reset on new speech, only one finalization per speech cycle, no finalization when speech has not stopped, multiple answer cycles, cancellation, and controller-level turn commit after silence.

**Phase 2 implication:** preserve this rule without substituting LiveKit/Deepgram endpointing. When an interview is persisted, finalization must be an idempotent state transition: a turn ID or unique event key should prevent duplicate transcript commits and duplicate LLM evaluations after reconnects or task retries.

### 4.7 Transcript handling

**Reported:** the controller receives transcript text plus a final/interim flag; the event publisher sends JSON over LiveKit's reliable data channel on topic `interview-events`; the React protocol parser handles speaker status and transcript events. The frontend displays transcript content.

**Unverified:** exact transcript data structures, timestamps, speaker identifiers, ordering guarantees, and whether final transcript events currently remain only in frontend memory.

**Phase 2 implication:** database transcript persistence must be server-side and independent of the browser's event stream. The UI's event stream should be a projection of server events, not the only transcript record. Persist the full chronological transcript, including the introduction/resume discussion, main questions, follow-ups, candidate answers, and conclusion. Keep interim display updates distinct from committed transcript turns.

### 4.8 Session start, end and state reset

**Reported:** API creates a LiveKit room; the candidate joins; the frontend explicitly dispatches the interviewer; the worker starts the agent session and opening message; DELETE removes the room. A `LiveKitService` in-memory dispatched-room set prevents duplicate dispatch within the process.

**Reported state:** `conversation_state.py` holds conversation states including `INITIALIZING`, `AI_SPEAKING`, `WAITING_FOR_CANDIDATE`, `CANDIDATE_SPEAKING`, `WAITING_FOR_SILENCE`, `PROCESSING_ANSWER`, `INTERVIEW_ENDED`, and `ERROR`. Completed-answer count is tracked. Tests cover valid transitions and preventing transitions/completions after the interview has ended.

**Unverified:** whether state is instantiated once per agent session, whether it resets for a second interview in the same browser tab, and what happens to state if FastAPI or the worker restarts.

**Phase 2 risk:** current in-memory conversation state and dispatch deduplication cannot be the source of truth for persistent interview progress. Keep a small in-memory runtime cache if needed for the live agent, but load and validate the authoritative stage, question IDs, turn counts and completion status from the interview database. A new session must receive fresh state; a resumed/incomplete session must restore from persisted state rather than reset silently.

## 5. Existing persistence, resume, database and API capabilities

### 5.1 Database

No database engine, schema, migration, ORM/repository, or persistent session record is evidenced by the supplied Phase 1 source history. The Phase 1 design originally called for in-memory session state. Treat SQLite databases as **new Phase 2 functionality**, subject to confirming the current repository does not already contain an unreported persistence layer.

### 5.2 Resume upload and file handling

No current resume upload endpoint, file validation layer, private file store, PDF/DOCX extraction module, resume metadata table, or resume processing status is evidenced in the Phase 1 module inventory. An early root `pyproject.toml` snapshot included `pypdf>=6.0.0`, but that does not prove it remains in the final lock or is currently used. DOCX parsing support is not evidenced.

### 5.3 Identity and ownership

No authentication or user identity model is evidenced in Phase 1. Phase 2 therefore needs a guest identity generated and controlled by the backend, a server-side association between that identity and resumes/sessions/reports, and ownership checks on every read/write endpoint. Do not trust a frontend-supplied `user_id`, `room_name`, or file path as proof of ownership.

### 5.4 Existing API

The reported Phase 1 API provides only health, create interview, dispatch, and end interview. Resume, role/question-bank, transcript-history, report, and guest-identity endpoints are new. Do not expose question-bank contents, internal selection logic, prompts, evaluation instructions, or private filesystem paths to the frontend.

## 6. Phase 2 requirement-to-code mapping

The table maps every major Phase 2 requirement group to the best-known reuse point and the proposed location for missing functionality. Paths marked **reported** need verification against the actual workspace before implementation.

| Phase 2 requirement | Existing code / capability | Missing work and proposed module boundary |
|---|---|---|
| Preserve existing voice interview | Reported `agent/worker.py`, `livekit_session_controller.py`, Deepgram, Cartesia, `LiveKitLLM`, LiveKit service | Freeze current interfaces; add regression tests before touching voice code. Persist session identifiers/events through an adapter rather than rewriting voice orchestration. |
| Generative AI Engineer role | No role catalogue evidenced | `domain/roles.py` plus shared role/question-bank repository; initially seed exactly one role. |
| Exactly 30 scenario-based main questions: 10 Easy, 10 Medium, 10 Hard | No question bank evidenced | `role_question_bank.db`; deterministic seed/validation test asserting counts, difficulty distribution, unique IDs, and no answers/rubrics/follow-ups/extra metadata. |
| Question bank contains no answers, answer keys, hints, rubrics, scoring criteria, or prewritten follow-ups | No question bank evidenced | Keep only role identity/details/technologies and minimum question identifiers, difficulty and question text. Enforce this in schema and seed-data tests. |
| Shared role-question database | No DB evidenced | Repository boundary for `role_question_bank.db`; read-only question selection interface for the interview domain. |
| Shared interview database | No DB evidenced | Repository boundary for `interview_data.db`; tables for guest/user identity, resumes, extracted information, sessions, transcript records, and reports. |
| Guest identity and future account linking | No identity/ownership service evidenced | `services/identity_service.py` and identity repository; guest IDs generated server-side; future account linking without changing interview/resume ownership model. |
| Server-side ownership and privacy | Phase 1 API room routes are reported; ownership cannot be confirmed | API dependencies/policies that resolve guest owner from a server-issued capability or authenticated identity; authorize every resume/session/transcript/report operation. |
| Resume upload, replace and remove | No resume endpoints evidenced | `api/resumes.py`, `services/resume_storage.py`, `services/resume_extractor.py`; validate extension, MIME/signature, size and ownership; write to private non-static storage. |
| PDF and DOCX extraction | Early dependency snapshot includes `pypdf`; no DOCX parser evidenced | Use an existing supported PDF library only after lock inspection; inspect/approve a DOCX parser such as `python-docx` if absent. Keep extraction behind a replaceable service. |
| Extract candidate name/contact, education, skills, projects, experience, certifications | No structured resume extraction evidenced | `services/resume_extractor.py` normalizes extracted text into validated fields, retaining source text/snippets for traceability and representing missing data as absent. |
| Never invent resume facts; retain raw text traceability | No resume pipeline evidenced | Persist extracted raw text and provenance; all structured fields need source evidence; evaluation prompts must treat resume text as untrusted candidate data. |
| Intro and resume discussion | Phase 1 opening statement and conversation path are reported; Phase 2 resume-aware flow is new | Interview domain stage controller: fixed intro coverage (background, reason for applying, role interest, relevant projects), followed by at most two contextual resume cross-questions. |
| Resume mismatch/project cross-question rules | No resume-aware interview behaviour evidenced | Backend-controlled interview planner using extracted evidence; only raise a mismatch where supported by specific resume evidence; otherwise ask about a resume project or an unexplored project. |
| Three adaptive main technical questions | Existing Phase 1 answer counter only; no adaptive bank selection evidenced | `services/question_selection.py` and persisted interview state; first question randomly Easy, later difficulty selected using validated overall performance. |
| Never repeat main questions in one session | No question-ID tracking evidenced | Persist selected question IDs in session state; atomic selection excluding already selected IDs. |
| Up to two dynamic follow-ups per main question | Existing LLM conversation capability, but no validated follow-up counter evidenced | `services/followup_generator.py`; categories clarification/reasoning/deeper exploration/scenario variation; backend hard cap of two per main question. |
| LLM may recommend next action, backend enforces limits | Existing configurable LLM service | Add typed recommendation schemas and validators; LLM output is advisory. Server decides whether a question/follow-up/transition is allowed. |
| Full chronological transcript | Frontend transcript event rendering is reported; durable storage not evidenced | Transcript repository and idempotent append API/service; retain both candidate and AI messages with sequence and event type. |
| Compact structured interview memory | No Phase 2 memory module evidenced | `services/interview_memory.py`; build from persisted transcript and structured state, while retaining full transcript separately. |
| Incomplete interviews persist without final score | No persistent session status evidenced | Session status lifecycle (`created`, `in_progress`, `incomplete`, `completed`, `failed/abandoned` as approved); final evaluation rows only when completion criteria are met. |
| Separate resume suitability and interview performance scores, each /10 | No report/evaluation module evidenced | `services/evaluation_service.py` with distinct report types and validated numeric scores; use evidence-only explanations. |
| Strengths, weaknesses, missing concepts, answer feedback, actionable suggestions | No evaluation report evidenced | Persist structured report sections with transcript/resume evidence references; technical scoring strictness and rubric policy need an approved design without adding rubrics to the question-bank DB. |
| No personality/intelligence/confidence inference from voice | No Phase 2 scoring logic evidenced | Evaluation policy explicitly excludes personality/psychological inferences and accent scoring. Evaluate answer content only. |
| Candidate sees only allowed data | Phase 1 dashboard has status/transcript controls, but full current UI unverified | Minimal extensions to existing dashboard for resume upload status/replace/remove, role-appropriate summary, asked questions, report and history. No question bank, future questions, selection logic, internal state or prompts. |
| Start New Interview only via explicit UI action | Phase 1 Start Interview button is reported | API creates a new persisted session only from explicit start action; greetings or ordinary candidate utterances cannot reset state. |
| Local Windows execution; no new infrastructure | Phase 1 runs locally, according to owner; FastAPI/LiveKit already present | Prefer SQLite and local private file storage; no database server, Redis, microservices or workflow engine. Confirm Python 3.14 package compatibility before selecting parser/ORM dependencies. |
| Maintain project documentation and development history | Required docs are listed in Phase 2 context; current files not visible | Inspect docs; create/update `PROJECT_CONTEXT.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_STATUS.md`, `LATEST_HANDOFF.md`, and append-only `PROJECT_DEVELOPMENT_HISTORY.md` as needed. |

## 7. Proposed database integration

### 7.1 Recommendation: two local SQLite files

**Proposed:** use Python's built-in `sqlite3` module initially, unless current project inspection reveals a suitable database layer already in use. This respects the local-first requirement and avoids introducing a database server or unnecessary ORM dependency.

```text
backend/data/
├── role_question_bank.db   # shared, seed-managed role/question data
└── interview_data.db       # guest/user-specific interview data

backend/private_storage/
└── resumes/                # originals; never served as static frontend content
```

The exact storage root should be configurable and excluded from source control. Do not commit candidate files, the databases containing user data, or `.env` credentials.

### 7.2 `role_question_bank.db`

Keep this database deliberately minimal:

- role identifier/name/details/technologies;
- question identifier;
- role association;
- difficulty (`Easy`, `Medium`, `Hard`);
- scenario question text.

Seed exactly 30 unique Generative AI Engineer scenario questions: 10 at each difficulty. Do not store answers, answer keys, explanations, hints, rubrics, scoring criteria, prewritten follow-ups, tags, or generated assessments. Add a deterministic seed validator that fails if counts/distribution/uniqueness are wrong or prohibited columns are added.

### 7.3 `interview_data.db`

Proposed minimum entity groups:

- `identities`: opaque server-generated guest identity; optional future registered-user association; timestamps and status.
- `resumes`: owning identity, original filename for display, storage key (not public path), detected type, size/hash, processing status, extracted raw text and structured extraction metadata.
- `interview_sessions`: owner identity, role, resume reference, lifecycle status, current stage, selected main question IDs, current main-question index, follow-up count, start/end timestamps, completion marker.
- `transcript_entries`: session, sequence number, speaker, message type, text, final/interim marker, optional source timestamps, idempotency/event key.
- `resume_reports`: session/resume association, score out of 10, evidence, strengths, gaps, recommendations, model/provider version metadata where appropriate.
- `interview_reports`: session association, score out of 10, evidence-linked answer feedback, strengths, weaknesses, missing concepts, actionable recommendations.

This is a conceptual boundary, not a final schema. The next milestone should inspect current patterns and write tests before implementing schema details.

### 7.4 Cross-database relationship consideration

SQLite does not provide ordinary cross-file foreign keys. Store the role question identifiers selected for a session as stable opaque IDs in `interview_data.db`; validate them through the question-bank repository. Avoid making interview persistence depend on a live cross-database join. If atomic consistency across the two files becomes a requirement, revisit the split only with an explicit architecture decision; do not silently consolidate the two mandated databases.

### 7.5 Migrations, durability and concurrency

Use versioned SQL migration files or a small migration runner compatible with the existing stack. Each migration must be repeatable/trackable and have rollback or recovery guidance. Configure transactions around state-changing operations; evaluate SQLite WAL mode and busy timeout after checking the actual process topology. Do not assume in-memory locks are sufficient if FastAPI and the LiveKit worker are separate processes. Make transcript appends and question selection idempotent/transactional.

### 7.6 Guest ownership and file security

A guest identity must be generated server-side. Because login is deferred, the design still needs a durable ownership capability for returning to that guest's data. Prefer a high-entropy, signed or otherwise unguessable guest credential/capability; store only a verifier/hash server-side where practical. Do not trust a client-supplied identity string by itself. Keep original resumes under a private directory, store opaque storage keys in the DB, validate file content and size, and never expose absolute local paths. A later account system should link the guest identity to an account through a server-controlled operation.

## 8. Existing test status and verification

### 8.1 Backend tests

The supplied historical test logs include these suites:

- `test_api.py`
- `test_cartesia_service.py`
- `test_config.py`
- `test_conversation_state.py`
- `test_deepgram_service.py`
- `test_interview_orchestrator.py` (an earlier design/test name in the history)
- `test_livekit_llm.py`
- `test_livekit_service.py`
- `test_livekit_session_controller.py`
- `test_llm_provider.py`
- `test_silence_detector.py`
- `test_worker.py`

A supplied earlier test run ended with **55 passed, 57 warnings**. Another captured run first ended with **1 failed, 71 passed, 57 warnings**, then a rerun ended with **72 passed, 57 warnings in 4.25s**. The earlier failure was in `test_livekit_llm.py`; the accompanying traceback showed a `ChatMessage.content` validation error because a string was supplied where the installed LiveKit type expected a list. The subsequent captured full run passed all 72 tests.

Warnings in the captured output came from the installed LiveKit Agents package using `asyncio.iscoroutinefunction`, which was deprecated and is scheduled for removal in Python 3.16. This is a dependency warning, not evidence of an application test failure.

Project history outside the currently mounted logs also reports a later **77 passed, 57 warnings** checkpoint. Because the current source and its newest raw test output were not mounted, that newer total could not be independently checked or reconciled against the 72-test log. Record the exact current baseline only after rerunning tests in the actual workspace.

### 8.2 Frontend tests and manual workflow

A supplied frontend protocol-test result recorded **8 passed** for event parsing, status handling, malformed/unknown messages and microphone-state mapping. The project history also reports frontend API tests, React/Vite, `livekit-client`, and a successful manual end-to-end workflow according to the project owner. The final frontend API test count, current `npm test` result, current build result, and exact current package versions are not present in the mounted raw logs.

### 8.3 Baseline commands to run in the actual Windows workspace

Do not run these in this audit container because the project files and Windows virtual environment are absent. Run from the project's root PowerShell terminal after making the current repository available:

```powershell
# Backend baseline
.\.venv\Scripts\Activate.ps1
python --version
python -m pytest .\backend\tests -v

# Frontend baseline
node --version
npm --version
Set-Location .\frontend
npm test
npm run build
```

The test script name should be confirmed from the current `frontend/package.json` before running; if no `test` script exists, inspect the scripts rather than changing them during this audit. Also inspect `pyproject.toml`, `uv.lock`, `frontend/package.json`, and any requirements files to record the actual installed/locked dependency set.

## 9. Runtime versions, dependencies, setup and environment

### 9.1 Versions found in supplied project history

| Component | Version / detail | Confidence |
|---|---|---|
| Windows | Windows PowerShell; user project path under `C:\Users\...` | Recorded in console transcripts |
| Python | 3.14.10 in the later `.venv` logs | Recorded in test output |
| pytest | 9.2.0 | Recorded in test output |
| Node.js | v26.12.1 | Reported in prior project context; current `node --version` not available here |
| npm | 11.20.0 | Reported in prior project context; current `npm --version` not available here |
| LiveKit Agents | 1.2.8 in later project context | Reported; current lockfile unavailable |
| LiveKit plugins | Cartesia, Deepgram, Silero, turn detector at 1.2.8 in later project context | Reported; current lockfile unavailable |
| `livekit-client` | 2.24.1 | Reported; current package lock unavailable |
| React | 19.3.1 | Reported; current package lock unavailable |
| Vite | 8.3.8 | Reported; current package lock unavailable |
| TypeScript | 7.0.2 | Reported; current package lock unavailable |
| Vitest | 5.1.0 | Reported; current package lock unavailable |

An early `pyproject.toml` excerpt required Python `>=3.12` and included LangChain/Chroma/OpenAI integrations, LiveKit Agents extras, noise cancellation, and `pypdf`. Those values must not be assumed to describe the final Phase 1 dependency lock.

### 9.2 Environment variables

The project context reports backend configuration for:

- LiveKit URL, API key and API secret;
- configured LiveKit agent name (`simple-ai-interviewer` in the recorded implementation);
- Deepgram API key;
- Cartesia API key;
- LLM provider, model, API key and base URL;
- silence timeout (reported default: 10 seconds);
- opening interviewer message.

The precise environment variable names, `.env`/`.env.local` loading order, required-vs-optional flags, and frontend variables cannot be confirmed without `config.py`, `.env.example` and startup files. Do not copy or expose live secrets in audit documentation. Phase 2 will likely add private storage/data-directory settings; their names and defaults should be decided in the relevant milestone.

### 9.3 Setup and run commands

Historical setup uses a Windows Python virtual environment and `python -m pytest`. The backend and frontend startup commands are not fully preserved in the available records. Do not invent exact commands; inspect the current README, `pyproject.toml`, app entrypoints, Vite scripts and any worker launch configuration in the actual repository, then document the verified commands.

## 10. Minimal React dashboard changes

Do not redesign the dashboard. Preserve the existing interview screen, voice states, transcript, Start Interview and End Interview behaviour.

Recommended additions, only when their related backend capability is ready:

1. **Before interview:** show the role title and a short role-appropriate summary; add resume upload, filename, processing status, replace and remove controls.
2. **During interview:** keep the existing voice/status/transcript experience. Display the questions that have actually been asked, not the future question bank, difficulty, selection logic, hidden state or prompts. Do not add a new dashboard information architecture.
3. **After interview:** show separate resume suitability and interview performance reports, only when a completed interview has produced them.
4. **History:** add a small list of the candidate's own prior sessions and completion status, subject to ownership authorization.

The incomplete-interview state must not show final completed scores. Candidate-visible API DTOs should be explicit allow-lists; do not serialize ORM/database records directly.

## 11. Proposed minimal module boundaries and milestone order

These are recommendations for approval. Actual paths should follow the current project's naming conventions after source inspection. Keep the existing voice pipeline intact.

| Proposed order | Scope | Minimal module boundary | Exit criteria |
|---|---|---|---|
| **2.1 — Persistence and identity foundation** | Create the two SQLite databases, schema/versioning, repository interfaces, guest identity and session ownership | `app/db/`, `app/repositories/`, `app/services/identity_service.py`; focused DB config | Migration/schema tests; ownership tests; no regression to Phase 1 voice/API tests; no resume parsing or adaptive interview logic yet. |
| **2.2 — Role and question bank** | Define Generative AI Engineer role; seed exactly 30 main questions | `role_question_bank.db`, `repositories/question_bank_repository.py`, seed/validation module | Tests prove exactly 10 Easy/10 Medium/10 Hard, unique IDs, role association and prohibited content absent. |
| **2.3 — Resume storage and extraction** | Upload/replace/remove, private file storage, PDF/DOCX extraction, normalized resume data | `api/resumes.py`, `services/resume_storage.py`, `services/resume_extractor.py`, resume repository | File validation, ownership, private-path, extraction, malformed/oversized file and evidence-traceability tests. |
| **2.4 — Persistent interview state and adaptive orchestration** | Intro/resume discussion, 3 main questions, adaptive difficulty, max 2 follow-ups, no repeats, full transcript and incomplete-session recovery | `domain/interview_state.py`, `services/interview_orchestrator.py`, `services/question_selection.py`, `services/followup_generator.py`, transcript repository | State-transition and hard-limit tests; persistence/restart tests; question non-repeat; no automatic reset; Phase 1 voice regression passes. |
| **2.5 — Evaluation and reporting** | Separate resume and interview evaluations, evidence-linked strengths/gaps/feedback, completion gating | `services/evaluation_service.py`, report schemas/repository | Numeric range and evidence validation; separate scores; incomplete sessions have no final score; no voice/accent/personality inference. |
| **2.6 — Minimal dashboard and API integration** | Resume controls, role summary, asked-question view, own history and reports | Extend existing `interviewApi.ts`, `App.tsx`, protocol/types and tests; add focused API routers | Candidate sees only authorized/allowed data; existing UI retained; end-to-end flows work locally. |
| **2.7 — Integration, recovery and regression** | Full local integration, restart recovery, failure handling, docs and handoff | Integration tests and documentation | Backend + frontend test/build success; manual end-to-end test; Phase 1 voice regression; current docs accurately reflect implementation. |

This order intentionally establishes durable identity and storage before resume uploads or persisted interviews. It also seeds and validates the question bank before building adaptive selection around it. If current source inspection reveals an existing compatible persistence layer, adjust the plan to reuse it instead of introducing duplicate infrastructure.

## 12. Proposed test plan

### 12.1 Protect Phase 1 before Phase 2 changes

- Run all current backend tests and record the raw output and exact count.
- Run all current frontend tests and production build.
- Verify API health, create, join, explicit dispatch, opening speech, candidate speech, 10-second silence, LLM response, Cartesia response, half-duplex audio, repeated turns and end.
- Save this as the baseline against which every Phase 2 milestone is compared.

### 12.2 Database and identity tests

- Fresh database initialization and repeatable migration/version handling.
- Foreign-key/integrity checks within each database.
- Guest identity creation, persistence and future user-link association.
- Cross-owner read/write rejection for resumes, sessions, transcripts and reports.
- Transaction rollback, duplicate event/idempotency protection and concurrent write behaviour.
- Safe data-directory configuration and no private storage path in API responses.

### 12.3 Question-bank tests

- Exactly one initial role and exactly 30 main questions.
- Exactly 10 Easy, 10 Medium and 10 Hard.
- Every question scenario-based and has a stable unique identifier.
- No answer/rubric/hint/explanation/follow-up/extra metadata fields.
- Question selection never repeats an ID within a session; first question always Easy; later difficulty is within permitted evidence-based bounds.

### 12.4 Resume tests

- Valid PDF and DOCX extraction.
- Invalid extension, spoofed MIME/signature, corrupt file, empty file and over-limit file.
- Replace/remove operations restricted to owner.
- Original file remains in private storage; frontend receives no physical path.
- Missing fields remain missing; extracted facts can be traced to raw text/source excerpts.
- Prompt-injection content inside resumes is treated as data, not instructions.

### 12.5 Interview workflow tests

- Introduction is always the first stage and covers required introductory areas.
- Resume cross-questions are evidence-based and capped at two.
- Main question 1 is Easy; maximum three main questions total; no repeats.
- Maximum two contextual follow-ups per main question; follow-ups are not stored in the question bank.
- Difficulty recommendations are validated by backend rules; Hard is not chosen without demonstrated performance.
- Greetings or ordinary candidate messages never reset/start a session; only explicit Start New Interview does.
- Session state and selected IDs survive backend/worker restart or are recovered as incomplete.
- Interrupted/incomplete interviews persist transcript but have no final completed score.
- Full transcript is retained; compact memory is only a derived context representation.

### 12.6 Evaluation and privacy tests

- Resume suitability and interview performance are independently scored from 0 to 10.
- Report claims cite resume/transcript evidence; no unsupported inference.
- Technical feedback identifies strengths, weaknesses, missing concepts and actionable improvements.
- No score derived from accent, personality, intelligence, confidence or other psychological inference from voice.
- Candidate APIs cannot retrieve another identity's data, question bank, hidden difficulty/selection state, prompts, evaluation instructions, secrets or local paths.

### 12.7 End-to-end regression

Run a complete interview from the React dashboard through LiveKit, STT, provider LLM, Cartesia and back to the dashboard; verify transcript persistence and reports; repeat with a deliberately interrupted interview; restart backend/worker and confirm state is not silently reset. Continue running the Phase 1 tests after every milestone that touches shared interfaces.

## 13. Risks, migration concerns and dependency considerations

1. **Source audit incomplete:** most significant risk. The current source tree, actual imports, current database state (if any), exact UI and docs were not accessible. Proposed paths are provisional.
2. **Phase 1 state is in-memory:** it may be fine for the original single live session, but cannot by itself satisfy persistence, resume/recovery, server restarts or multi-session history.
3. **FastAPI and LiveKit worker process boundary:** if they run as separate processes, their in-memory state and locks are not shared. Persisted state and idempotent event handling must coordinate both.
4. **Room name is not user ownership:** room IDs are transport identifiers, not an authorization mechanism. All Phase 2 data endpoints require owner checks independent of client-provided room names.
5. **Guest identity without login:** durable guest ownership must be designed deliberately. A client-chosen identity alone is not secure, and browser-local storage loss may otherwise orphan records.
6. **Transcript duplication/order:** interim STT events and reconnect/retry paths can create duplicate records. Use sequence/order and idempotency keys; distinguish interim display from final persisted content.
7. **Agent and API termination consistency:** deleting a LiveKit room may disconnect a participant, but the exact worker task cancellation, final transcript flush and incomplete-session marking must be tested.
8. **Two SQLite databases:** the mandated split prevents ordinary cross-database foreign keys/atomic transactions. Use stable IDs and repository validation; document consistency guarantees.
9. **Concurrent access:** if API and worker processes write to the same SQLite interview database, use transactions, busy timeout and an explicitly tested journal mode. Avoid relying on process-local locks.
10. **Question-bank purity:** it must not become a hidden rubric store. Do not add scoring metadata or prewritten follow-ups to the question records.
11. **LLM nondeterminism and injection:** resume text and candidate answers are untrusted input. Validate all structured outputs; enforce all limits in code; do not let a prompt or model output override policy.
12. **Evaluation validity:** two scores need separate definitions and evidence requirements. Do not invent candidate facts or use voice characteristics as a proxy for technical capability.
13. **File security and privacy:** validate actual content, size and ownership; store outside static web roots; never expose absolute paths. Plan retention/deletion behaviour before collecting real resumes.
14. **Dependency compatibility:** Python 3.14.10 was used in captured test logs. PDF/DOCX parsers and database dependencies must be checked against the actual `uv.lock`/Python version before addition. The old pyproject snapshot included `pypdf`; final usage is unknown. Avoid a new ORM or migration library unless its benefit is justified and approved.
15. **LiveKit version-specific API:** early logs show LiveKit Agents API adaptation and a past LLM adapter test failure caused by message-content shape. Keep using the installed/locked SDK signatures and preserve adapter contract tests.
16. **Legacy LangGraph/LangChain artifacts:** early repository files and dependencies may remain from the selected upstream repository. Inspect import references before removal; do not remove packages/files in this audit milestone.
17. **Documentation drift:** early README/project files may describe the upstream agent rather than the current Phase 1 architecture. Compare docs against source and verified commands before updating them.
18. **Frontend build/runtime:** historical Node/npm/dependency versions are reported but not directly verifiable here. Confirm the actual lockfile before changing React/Vite/TypeScript versions.

## 14. Documentation audit

The Phase 2 master context requires these documents to be maintained:

- `PROJECT_CONTEXT.md`
- `PROJECT_RULES.md`
- `ARCHITECTURE.md`
- `IMPLEMENTATION_STATUS.md`
- `LATEST_HANDOFF.md`
- `PROJECT_DEVELOPMENT_HISTORY.md` (append-only)

Earlier Phase 1 instructions also named `README.md`. No current documentation file was available in the mounted workspace, so its existence and accuracy cannot be assessed. The only verifiable project documentation content is the set of Phase 1/Phase 2 prompts and pasted console outputs. The README, architecture and handoff should be reviewed after the repository is supplied. Keep the development history cumulative; do not overwrite it when adding a milestone entry.

## 15. Approval gates and next action

Before Milestone 2.1, the current repository needs to be made available for a true source-level pass. The most reliable input is a ZIP of the current `livekit-voice-agent` folder, excluding `.venv`, `node_modules`, `.git`, runtime databases, private resumes and `.env` files. Include safe templates such as `.env.example`, `pyproject.toml`, `uv.lock`, frontend package/lock files, tests and documentation. Alternatively, mount the repository in the workspace.

Once it is available, the audit should be reconciled against the actual files by:

1. capturing the full current `tree /F`;
2. reading backend/frontend entrypoints, configuration, worker/controller/services, tests, manifests and docs;
3. checking environment variable names without exposing secret values;
4. running the baseline backend tests and frontend tests/build in the project's own environment;
5. correcting this report's provisional module, version, and risk statements.

**No Milestone 2.1 work is authorized by this report.** No application source code was changed, no dependencies were installed, no databases or migrations were created, and no interview workflow was modified. Await review and approval of the plan after the source-level audit is complete.
