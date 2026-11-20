import { useEffect, useRef, useState } from "react";
import {
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
} from "livekit-client";

import {
  microphoneShouldBeEnabled,
  parseInterviewEvent,
  type InterviewStatus,
} from "./interviewProtocol";

import {
  createPersistentInterview,
  dispatchPersistentInterview,
  endPersistentInterview,
  ensureGuest,
  generateEvaluationReport,
  getInterviewTranscript,
  getResumeStatus,
  listInterviewSessions,
  replaceResume,
  uploadResume,
  type EvaluationReport,
  type InterviewSession,
  type ResumeStatus,
  type TranscriptMessage,
} from "./persistentInterviewApi";

import "./App.css";
import "./PersistentInterview.css";

const TRANSCRIPTION_TOPIC = "lk.transcription";

const AVAILABLE_ROLES = [
  {
    id: "generative_ai_engineer",
    name: "Generative AI Engineer",
  },
];

type TranscriptSpeaker = "AI INTERVIEWER" | "CANDIDATE";

interface TranscriptLine {
  id: number;
  speaker: TranscriptSpeaker;
  text: string;
}

interface InterimTranscript {
  speaker: TranscriptSpeaker;
  text: string;
}

// =========================================================
// SMALL REPORT COMPONENTS
// =========================================================

function ReportStringList({
  items,
  emptyMessage = "No specific items recorded.",
}: {
  items: string[];
  emptyMessage?: string;
}) {
  if (!items || items.length === 0) {
    return <p className="report-empty">{emptyMessage}</p>;
  }

  return (
    <ul className="report-list">
      {items.map((item, index) => (
        <li key={`${index}-${item}`}>{item}</li>
      ))}
    </ul>
  );
}

function EvidenceList({
  items,
  emptyMessage = "No evidence-backed items recorded.",
}: {
  items: Array<{
    claim: string;
    evidence: string;
  }>;
  emptyMessage?: string;
}) {
  if (!items || items.length === 0) {
    return <p className="report-empty">{emptyMessage}</p>;
  }

  return (
    <div className="evidence-list">
      {items.map((item, index) => (
        <div className="evidence-item" key={`${index}-${item.claim}`}>
          <strong>{item.claim}</strong>
          <blockquote>{item.evidence}</blockquote>
        </div>
      ))}
    </div>
  );
}

function formatScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(1) : "—";
}

// =========================================================
// MAIN APPLICATION
// =========================================================

function App() {
  const roomRef = useRef<Room | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const audioContainerRef = useRef<HTMLDivElement | null>(null);
  const transcriptIdRef = useRef(0);
  const latestStatusRef = useRef<InterviewStatus | null>(null);

  const [guestReady, setGuestReady] = useState(false);
  const [loading, setLoading] = useState(true);

  const [resume, setResume] = useState<ResumeStatus | null>(null);
  const [resumeBusy, setResumeBusy] = useState(false);

  const [selectedRole, setSelectedRole] = useState(
    AVAILABLE_ROLES[0].id,
  );

  const [sessions, setSessions] = useState<InterviewSession[]>([]);
  const [historyTranscript, setHistoryTranscript] =
    useState<TranscriptMessage[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] =
    useState<string | null>(null);

  // Milestone 2.6 report state.
  const [evaluationReport, setEvaluationReport] =
    useState<EvaluationReport | null>(null);

  const [reportSessionId, setReportSessionId] =
    useState<string | null>(null);

  const [reportBusySessionId, setReportBusySessionId] =
    useState<string | null>(null);

  const [reportError, setReportError] = useState("");

  const [connected, setConnected] = useState(false);
  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);

  const [status, setStatus] =
    useState<InterviewStatus>("INITIALIZING");

  const [microphoneEnabled, setMicrophoneEnabled] = useState(false);
  const [audioNeedsGesture, setAudioNeedsGesture] = useState(false);

  const [transcripts, setTranscripts] = useState<TranscriptLine[]>([]);
  const [interimTranscript, setInterimTranscript] =
    useState<InterimTranscript | null>(null);

  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // =======================================================
  // APPLICATION INITIALIZATION
  // =======================================================

  async function refreshSessions() {
    const result = await listInterviewSessions();
    setSessions(result);
  }

  async function initializeApplication() {
    setLoading(true);
    setError("");

    try {
      await ensureGuest();
      setGuestReady(true);

      const resumeStatus = await getResumeStatus();
      setResume(resumeStatus);

      await refreshSessions();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to initialize the application.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void initializeApplication();

    return () => {
      const room = roomRef.current;
      roomRef.current = null;

      if (room) {
        room.unregisterTextStreamHandler(TRANSCRIPTION_TOPIC);
        void room.disconnect();
      }
    };
  }, []);

  // =======================================================
  // RESUME MANAGEMENT
  // =======================================================

  async function handleResumeUpload(file?: File) {
    if (!file || resumeBusy) return;

    const allowedExtensions = [".pdf", ".doc", ".docx"];
    const fileName = file.name.toLowerCase();

    if (
      !allowedExtensions.some((extension) =>
        fileName.endsWith(extension),
      )
    ) {
      setError("Please upload a PDF, DOC or DOCX resume.");
      return;
    }

    setResumeBusy(true);
    setError("");
    setNotice("");

    try {
      const result = resume?.uploaded
        ? await replaceResume(file)
        : await uploadResume(file);

      setResume(result);

      setNotice(
        resume?.uploaded
          ? "Resume replaced successfully."
          : "Resume uploaded successfully.",
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to upload the resume.",
      );
    } finally {
      setResumeBusy(false);
    }
  }

  // =======================================================
  // MICROPHONE CONTROL
  // =======================================================

  async function applyMicrophoneStatus(
    nextStatus: InterviewStatus,
  ) {
    const room = roomRef.current;
    if (!room) return;

    const enabled = microphoneShouldBeEnabled(nextStatus);

    try {
      await room.localParticipant.setMicrophoneEnabled(enabled);

      if (latestStatusRef.current === nextStatus) {
        setMicrophoneEnabled(enabled);
      }
    } catch (err) {
      setMicrophoneEnabled(false);

      setError(
        err instanceof Error
          ? `Microphone error: ${err.message}`
          : "Could not update microphone.",
      );
    }
  }

  // =======================================================
  // LIVEKIT EVENTS
  // =======================================================

  function handleInterviewEvent(
    payload: Uint8Array,
    topic?: string,
  ) {
    const event = parseInterviewEvent(payload, topic);
    if (!event) return;

    if (event.type === "status") {
      latestStatusRef.current = event.status;
      setStatus(event.status);

      void applyMicrophoneStatus(event.status);

      if (event.status === "ERROR") {
        setError("The interviewer reported an error.");
      }
    }
  }

  function registerTranscriptionHandler(room: Room) {
    room.registerTextStreamHandler(
      TRANSCRIPTION_TOPIC,
      async (reader, participantInfo) => {
        try {
          const text = (await reader.readAll()).trim();

          if (!text || roomRef.current !== room) return;

          const attributes = reader.info.attributes ?? {};

          const isTranscription =
            attributes["lk.transcribed_track_id"] !== undefined;

          if (!isTranscription) return;

          const isFinal =
            attributes["lk.transcription_final"] === "true";

          const speaker: TranscriptSpeaker =
            participantInfo.identity === room.localParticipant.identity
              ? "CANDIDATE"
              : "AI INTERVIEWER";

          if (isFinal) {
            setTranscripts((current) => [
              ...current,
              {
                id: ++transcriptIdRef.current,
                speaker,
                text,
              },
            ]);

            setInterimTranscript(null);
          } else {
            setInterimTranscript({ speaker, text });
          }
        } catch (err) {
          console.error(
            "Failed to read interview transcription:",
            err,
          );
        }
      },
    );
  }

  function attachAudioTrack(track: RemoteTrack) {
    if (track.kind !== Track.Kind.Audio) return;

    const element = track.attach();
    element.autoplay = true;
    element.setAttribute("playsinline", "true");

    audioContainerRef.current?.appendChild(element);
  }

  // =======================================================
  // START INTERVIEW
  // =======================================================

  async function startInterview() {
    if (starting || roomRef.current || !guestReady) return;

    if (!resume?.uploaded || !resume.resume_id) {
      setError("Upload your resume before starting an interview.");
      return;
    }

    if (!selectedRole) {
      setError("Select an interview role.");
      return;
    }

    setStarting(true);
    setError("");
    setNotice("");
    setReportError("");

    setTranscripts([]);
    setInterimTranscript(null);
    setHistoryTranscript([]);
    setSelectedHistoryId(null);

    setEvaluationReport(null);
    setReportSessionId(null);

    transcriptIdRef.current = 0;
    setMicrophoneEnabled(false);
    setStatus("INITIALIZING");
    latestStatusRef.current = null;

    let room: Room | null = null;
    let createdSessionId: string | null = null;

    try {
      const session = await createPersistentInterview({
        role_id: selectedRole,
        resume_id: resume.resume_id,
      });

      createdSessionId = session.id;
      sessionIdRef.current = session.id;

      room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });

      roomRef.current = room;

      room.on(
        RoomEvent.DataReceived,
        (payload, _participant, _kind, topic) => {
          handleInterviewEvent(payload, topic);
        },
      );

      room.on(RoomEvent.TrackSubscribed, (track) => {
        attachAudioTrack(track);
      });

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((element) => element.remove());
      });

      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        setAudioNeedsGesture(!room?.canPlaybackAudio);
      });

      room.on(RoomEvent.Disconnected, () => {
        setConnected(false);
        setMicrophoneEnabled(false);
        setInterimTranscript(null);
      });

      registerTranscriptionHandler(room);

      await room.connect(session.livekit_url, session.token);

      // Do not enable the candidate microphone automatically.
      await room.localParticipant.setMicrophoneEnabled(false);

      setMicrophoneEnabled(false);
      setConnected(true);

      try {
        await room.startAudio();
        setAudioNeedsGesture(!room.canPlaybackAudio);
      } catch {
        setAudioNeedsGesture(true);
      }

      // Dispatch the agent using the persistent session ID.
      const dispatchResult = await dispatchPersistentInterview(session.id);

      if (!dispatchResult.dispatched) {
        throw new Error("The interviewer could not be dispatched.");
      }

      await refreshSessions();
    } catch (err) {
      if (room) {
        await room.disconnect().catch(() => undefined);
      }

      roomRef.current = null;
      sessionIdRef.current = null;

      setConnected(false);
      setMicrophoneEnabled(false);
      setInterimTranscript(null);
      setAudioNeedsGesture(false);

      if (createdSessionId) {
        try {
          await endPersistentInterview(createdSessionId);
        } catch {
          // Preserve the original startup error.
        }
      }

      setError(
        err instanceof Error
          ? err.message
          : "Unable to start the interview.",
      );
    } finally {
      setStarting(false);
    }
  }

  // =======================================================
  // AUDIO PLAYBACK
  // =======================================================

  async function enableAudioPlayback() {
    const room = roomRef.current;
    if (!room) return;

    try {
      await room.startAudio();
      setAudioNeedsGesture(!room.canPlaybackAudio);
    } catch (err) {
      setError(
        err instanceof Error
          ? `Audio playback error: ${err.message}`
          : "Could not enable audio playback.",
      );
    }
  }

  // =======================================================
  // END INTERVIEW
  // =======================================================

  async function endInterview() {
    if (ending) return;

    setEnding(true);
    setError("");

    const room = roomRef.current;
    const sessionId = sessionIdRef.current;

    roomRef.current = null;
    sessionIdRef.current = null;

    latestStatusRef.current = "INTERVIEW_ENDED";

    if (room) {
      try {
        await room.localParticipant.setMicrophoneEnabled(false);
      } catch {
        // Continue with disconnect.
      }

      room.unregisterTextStreamHandler(TRANSCRIPTION_TOPIC);
      await room.disconnect();
    }

    setConnected(false);
    setMicrophoneEnabled(false);
    setStatus("INTERVIEW_ENDED");
    setAudioNeedsGesture(false);
    setInterimTranscript(null);

    audioContainerRef.current?.replaceChildren();

    if (sessionId) {
      try {
        await endPersistentInterview(sessionId);
        setNotice("Interview ended and session saved.");
        await refreshSessions();
      } catch (err) {
        setError(
          err instanceof Error
            ? `Disconnected, but session cleanup failed: ${err.message}`
            : "Disconnected, but session cleanup failed.",
        );
      }
    }

    setEnding(false);
  }

  // =======================================================
  // VIEW SAVED TRANSCRIPT
  // =======================================================

  async function viewSavedTranscript(sessionId: string) {
    setError("");
    setNotice("");
    setHistoryTranscript([]);
    setSelectedHistoryId(sessionId);

    try {
      const result = await getInterviewTranscript(sessionId);
      setHistoryTranscript(result);
    } catch (err) {
      setSelectedHistoryId(null);

      setError(
        err instanceof Error
          ? err.message
          : "Unable to retrieve the saved transcript.",
      );
    }
  }

  // =======================================================
  // MILESTONE 2.6 — LOAD OR GENERATE EVALUATION
  // =======================================================

  async function openEvaluationReport(session: InterviewSession) {
    if (reportBusySessionId) return;

    if (session.status !== "completed") {
      setReportError(
        "An evaluation report is available only after all three "
        + "main technical questions have been completed.",
      );
      return;
    }

    setReportBusySessionId(session.id);
    setReportError("");
    setError("");
    setNotice("");

    setSelectedHistoryId(session.id);
    setHistoryTranscript([]);
    setEvaluationReport(null);
    setReportSessionId(null);

    try {
      // The backend returns the existing report when one is already saved.
      // Otherwise it generates both evaluations and persists the result.
      const report = await generateEvaluationReport(session.id);

      setEvaluationReport(report);
      setReportSessionId(session.id);

      setNotice("Evaluation report loaded successfully.");
    } catch (err) {
      setReportError(
        err instanceof Error
          ? err.message
          : "Unable to load the evaluation report.",
      );
    } finally {
      setReportBusySessionId(null);
    }
  }

  // =======================================================
  // INTERVIEW STATUS LABELS
  // =======================================================

  const speakerLabel =
    status === "AI_SPEAKING"
      ? "AI SPEAKING"
      : status === "PROCESSING_ANSWER"
        ? "PROCESSING ANSWER"
        : status === "CANDIDATE_SPEAKING"
          ? "CANDIDATE SPEAKING"
          : status === "WAITING_FOR_SILENCE"
            ? "WAITING FOR ANSWER TO FINISH"
            : status === "CANDIDATE_LISTENING"
              ? "CANDIDATE LISTENING"
              : status === "INTERVIEW_ENDED"
                ? "INTERVIEW ENDED"
                : "WAITING";

  // Only display a report when it belongs to the selected history session.
  const visibleReport =
    reportSessionId === selectedHistoryId
      ? evaluationReport
      : null;

  // =======================================================
  // APPLICATION UI
  // =======================================================

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">CAREER ARENA</p>
          <h1>AI Interviewer</h1>
          <p className="subtitle">
            Your persistent AI interview workspace.
          </p>
        </div>

        <span className={`connection-pill ${connected ? "online" : ""}`}>
          <span className="connection-dot" />
          {connected ? "CONNECTED" : "DISCONNECTED"}
        </span>
      </header>

      {loading ? (
        <section className="interview-card">
          <p>Initializing your candidate workspace...</p>
        </section>
      ) : (
        <>
          {/* =================================================
              CANDIDATE SETUP
          ================================================= */}

          <section className="interview-card">
            <h2>Candidate setup</h2>

            <div className="session-details">
              <div className="detail-row">
                <span>Guest identity</span>
                <strong>
                  {guestReady ? "Ready" : "Not initialized"}
                </strong>
              </div>

              <div className="detail-row">
                <span>Resume</span>
                <strong className={resume?.uploaded ? "mic-on" : "mic-off"}>
                  {resume?.uploaded ? "UPLOADED" : "REQUIRED"}
                </strong>
              </div>

              {resume?.uploaded && (
                <div className="detail-row">
                  <span>Current file</span>
                  <strong>{resume.filename}</strong>
                </div>
              )}
            </div>

            <label className="field-label" htmlFor="resume-file">
              {resume?.uploaded ? "Replace resume" : "Upload resume"}
            </label>

            <input
              id="resume-file"
              type="file"
              accept=".pdf,.doc,.docx"
              disabled={resumeBusy || connected || starting}
              onChange={(event) => {
                const file = event.target.files?.[0];
                void handleResumeUpload(file);
                event.currentTarget.value = "";
              }}
            />

            {resumeBusy && <p>Processing resume...</p>}

            <label className="field-label" htmlFor="role-select">
              Interview role
            </label>

            <select
              id="role-select"
              value={selectedRole}
              onChange={(event) => setSelectedRole(event.target.value)}
              disabled={connected || starting}
            >
              {AVAILABLE_ROLES.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>

            <p className="subtitle">
              Your resume is mandatory for every interview.
            </p>
          </section>

          {/* =================================================
              LIVE INTERVIEW
          ================================================= */}

          <section className="interview-card">
            <div className="speaker-panel">
              <div
                className={`speaker-orb ${
                  status === "AI_SPEAKING" ? "active" : ""
                }`}
              >
                <span className="speaker-icon">AI</span>
              </div>

              <p className="speaker-label">{speakerLabel}</p>

              <p className="status-description">
                {status === "AI_SPEAKING"
                  ? "Please listen to the interviewer."
                  : status === "PROCESSING_ANSWER"
                    ? "Your answer is being processed."
                    : status === "CANDIDATE_LISTENING"
                      ? "You can start speaking."
                      : status === "WAITING_FOR_SILENCE"
                        ? "Your answer will be submitted after 10 seconds of silence."
                        : status === "CANDIDATE_SPEAKING"
                          ? "The interviewer is listening."
                          : "Start an interview to begin."}
              </p>
            </div>

            <div className="session-details">
              <div className="detail-row">
                <span>Connection</span>
                <strong>
                  {connected ? "LiveKit connected" : "Not connected"}
                </strong>
              </div>

              <div className="detail-row">
                <span>Microphone</span>
                <strong className={microphoneEnabled ? "mic-on" : "mic-off"}>
                  {microphoneEnabled ? "ENABLED" : "DISABLED"}
                </strong>
              </div>
            </div>

            {audioNeedsGesture && connected && (
              <button
                className="secondary-button"
                onClick={enableAudioPlayback}
              >
                Enable interviewer audio
              </button>
            )}

            <div className="controls">
              {!connected ? (
                <button
                  className="primary-button"
                  onClick={startInterview}
                  disabled={
                    starting ||
                    ending ||
                    !guestReady ||
                    !resume?.uploaded
                  }
                >
                  {starting ? "Starting interview..." : "Start Interview"}
                </button>
              ) : (
                <button
                  className="end-button"
                  onClick={endInterview}
                  disabled={ending}
                >
                  {ending ? "Ending..." : "End Interview"}
                </button>
              )}
            </div>

            {error && <p className="error-message">{error}</p>}
            {notice && <p className="success-message">{notice}</p>}
          </section>

          {/* =================================================
              LIVE TRANSCRIPT
          ================================================= */}

          <section className="transcript-card">
            <div className="transcript-heading">
              <div>
                <p className="eyebrow">LIVE CONVERSATION</p>
                <h2>Transcript</h2>
              </div>

              <span>{transcripts.length} final segments</span>
            </div>

            <div className="transcript-content" aria-live="polite">
              {transcripts.length === 0 && !interimTranscript && (
                <p className="empty-transcript">
                  The AI interviewer's and candidate's speech will appear here.
                </p>
              )}

              {transcripts.map((line) => (
                <div className="transcript-line" key={line.id}>
                  <strong>{line.speaker}</strong>
                  <p>{line.text}</p>
                </div>
              ))}

              {interimTranscript && (
                <div className="transcript-line interim">
                  <strong>{interimTranscript.speaker}</strong>
                  <p>{interimTranscript.text}</p>
                </div>
              )}
            </div>
          </section>

          {/* =================================================
              INTERVIEW HISTORY
          ================================================= */}

          <section className="transcript-card">
            <div className="transcript-heading">
              <div>
                <p className="eyebrow">PERSISTENT STORAGE</p>
                <h2>Interview history</h2>
              </div>

              <span>{sessions.length} sessions</span>
            </div>

            {sessions.length === 0 ? (
              <p className="empty-transcript">
                Your previous interview sessions will appear here.
              </p>
            ) : (
              <div className="history-list">
                {sessions.map((session) => (
                  <div className="history-item" key={session.id}>
                    <div>
                      <strong>
                        {AVAILABLE_ROLES.find(
                          (role) => role.id === session.role_id,
                        )?.name ?? session.role_id}
                      </strong>

                      <p>
                        {new Date(session.created_at).toLocaleString()}
                      </p>

                      <span className={`session-status ${session.status}`}>
                        {session.status.replaceAll("_", " ")}
                      </span>
                    </div>

                    <div className="history-actions">
                      <button
                        className="secondary-button"
                        onClick={() => void viewSavedTranscript(session.id)}
                        disabled={connected || starting}
                      >
                        View transcript
                      </button>

                      {session.status === "completed" && (
                        <button
                          className="report-button"
                          onClick={() => void openEvaluationReport(session)}
                          disabled={
                            reportBusySessionId !== null ||
                            connected ||
                            starting
                          }
                        >
                          {reportBusySessionId === session.id
                            ? "Loading report..."
                            : "Open evaluation"}
                        </button>
                      )}

                      {session.status === "interrupted" && (
                        <span className="report-unavailable">
                          No evaluation — interrupted
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Saved transcript */}
            {selectedHistoryId && (
              <div className="saved-transcript">
                <h3>Saved transcript</h3>

                {historyTranscript.length === 0 ? (
                  <p className="empty-transcript">
                    No saved transcript messages were found.
                  </p>
                ) : (
                  historyTranscript.map((message) => (
                    <div className="transcript-line" key={message.id}>
                      <strong>{message.speaker.toUpperCase()}</strong>
                      <p>{message.message_text}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </section>

          {/* =================================================
              MILESTONE 2.6 — EVALUATION REPORT
          ================================================= */}

          {reportError && (
            <section className="transcript-card">
              <h2>Evaluation report</h2>
              <p className="error-message">{reportError}</p>
            </section>
          )}

          {visibleReport && (
            <section className="transcript-card evaluation-card">
              <div className="transcript-heading">
                <div>
                  <p className="eyebrow">CAREER ARENA EVALUATION</p>
                  <h2>Interview evaluation report</h2>
                  <p className="subtitle">
                    Generated{" "}
                    {new Date(
                      visibleReport.created_at,
                    ).toLocaleString()}
                  </p>
                </div>

                <span className="completed-report-label">
                  COMPLETED
                </span>
              </div>

              {/* Separate scores */}
              <div className="evaluation-scores">
                <div className="evaluation-score-panel">
                  <span>Resume suitability</span>
                  <strong>
                    {formatScore(visibleReport.resume_score)}
                    <small>/ 10</small>
                  </strong>
                  <p>
                    Alignment between your resume evidence and the selected role.
                  </p>
                </div>

                <div className="evaluation-score-panel">
                  <span>Interview performance</span>
                  <strong>
                    {formatScore(visibleReport.interview_score)}
                    <small>/ 10</small>
                  </strong>
                  <p>
                    Technical performance based on your interview answers.
                  </p>
                </div>
              </div>

              {/* Resume evaluation */}
              <div className="report-section">
                <p className="eyebrow">PART 1</p>
                <h3>Resume suitability</h3>

                <p className="report-rationale">
                  {visibleReport.resume_report.score_rationale}
                </p>

                <h4>Strengths supported by resume evidence</h4>
                <EvidenceList
                  items={visibleReport.resume_report.strengths}
                  emptyMessage="No verified strengths were returned."
                />

                <h4>Experience and project alignment</h4>
                <EvidenceList
                  items={visibleReport.resume_report.experience_alignment}
                  emptyMessage="No evidence-backed alignment items were returned."
                />

                <h4>Missing or weakly evidenced skills</h4>
                <ReportStringList
                  items={
                    visibleReport.resume_report.missing_or_weak_skills
                  }
                />

                <h4>Resume improvement areas</h4>
                <ReportStringList
                  items={visibleReport.resume_report.improvement_areas}
                />
              </div>

              {/* Interview evaluation */}
              <div className="report-section">
                <p className="eyebrow">PART 2</p>
                <h3>Technical interview performance</h3>

                <p className="report-rationale">
                  {visibleReport.interview_report.score_rationale}
                </p>

                <h4>Technical strengths</h4>
                <ReportStringList
                  items={
                    visibleReport.interview_report.technical_strengths
                  }
                />

                <h4>Weak or incorrect answers</h4>
                <ReportStringList
                  items={
                    visibleReport.interview_report.weak_or_incorrect_answers
                  }
                />

                <h4>Missing technical concepts</h4>
                <ReportStringList
                  items={visibleReport.interview_report.missing_concepts}
                />

                {/* Answer-by-answer feedback */}
                <h4>Answer-by-answer feedback</h4>

                <div className="answer-feedback-list">
                  {visibleReport.interview_report.answer_by_answer_feedback
                    .map((answer, index) => (
                      <article
                        className="answer-feedback-item"
                        key={`${index}-${answer.question}`}
                      >
                        <div className="answer-feedback-heading">
                          <h5>
                            Question {index + 1}: {answer.question}
                          </h5>

                          <span className={`correctness ${answer.correctness}`}>
                            {answer.correctness.replaceAll("_", " ")}
                          </span>
                        </div>

                        <p className="answer-assessment">
                          {answer.assessment}
                        </p>

                        <p>{answer.feedback}</p>

                        {answer.evidence && (
                          <div className="answer-evidence">
                            <span>Evidence from your answer</span>
                            <blockquote>{answer.evidence}</blockquote>
                          </div>
                        )}

                        {answer.missing_concepts.length > 0 && (
                          <div className="answer-missing-concepts">
                            <strong>Concepts to improve</strong>
                            <ReportStringList
                              items={answer.missing_concepts}
                            />
                          </div>
                        )}
                      </article>
                    ))}
                </div>

                <h4>Technical justification</h4>
                <p className="report-rationale">
                  {visibleReport.interview_report.reasoning_and_justification}
                </p>

                <h4>Recommendations</h4>
                <ReportStringList
                  items={
                    visibleReport.interview_report.recommendations
                  }
                />
              </div>

              <p className="report-footer">
                Resume suitability and interview performance are evaluated
                separately. These scores are not combined.
              </p>
            </section>
          )}
        </>
      )}

      <div className="audio-container" ref={audioContainerRef} />
    </main>
  );
}

export default App;