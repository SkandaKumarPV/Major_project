const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const GUEST_TOKEN_KEY = "career_arena_guest_token";

// =========================================================
// GUEST IDENTITY
// =========================================================

export interface GuestIdentity {
  access_token: string;
  token_type: "bearer";
}

export interface GuestStatus {
  authenticated: boolean;
}

// =========================================================
// RESUME
// =========================================================

export interface ResumeStatus {
  uploaded: boolean;
  resume_id: string | null;
  filename: string | null;
  status: string;
}

// =========================================================
// INTERVIEW SESSION
// =========================================================

export interface InterviewSession {
  id: string;
  room_name: string;
  role_id: string;
  resume_id: string;
  status: string;

  current_stage: string | null;
  current_main_question_id: string | null;

  used_main_question_ids: string[];
  follow_up_count: number;

  completed_question_ids: string[];
  completed_stages: string[];

  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}

export interface CreatedInterviewSession extends InterviewSession {
  livekit_url: string;
  participant_identity: string;
  token: string;
}

export interface DispatchInterviewResponse {
  session_id: string;
  room_name: string;
  agent_name: string;
  dispatched: boolean;
  status: string;
}

export interface CreateInterviewSessionInput {
  role_id: string;
  resume_id: string;
}

// =========================================================
// INTERVIEW TRANSCRIPT
// =========================================================

export interface TranscriptMessage {
  id: string;
  sequence_number: number;
  speaker: string;
  message_text: string;
  created_at: string;
}

// =========================================================
// MILESTONE 2.6 — RESUME EVALUATION TYPES
// =========================================================

export interface ResumeEvidenceItem {
  claim: string;
  evidence: string;
}

export interface ResumeEvaluation {
  score: number;

  strengths: ResumeEvidenceItem[];

  missing_or_weak_skills: string[];

  experience_alignment: ResumeEvidenceItem[];

  improvement_areas: string[];

  score_rationale: string;
}

// =========================================================
// MILESTONE 2.6 — INTERVIEW EVALUATION TYPES
// =========================================================

export type AnswerCorrectness =
  | "technically_correct"
  | "partially_correct"
  | "incorrect"
  | "insufficient_evidence";

export interface InterviewAnswerFeedback {
  question: string;
  assessment: string;
  feedback: string;
  missing_concepts: string[];
  correctness: AnswerCorrectness;
  evidence: string;
}

export interface InterviewEvaluation {
  score: number;

  technical_strengths: string[];

  weak_or_incorrect_answers: string[];

  missing_concepts: string[];

  answer_by_answer_feedback: InterviewAnswerFeedback[];

  reasoning_and_justification: string;

  recommendations: string[];

  score_rationale: string;
}

// =========================================================
// MILESTONE 2.6 — COMPLETE EVALUATION REPORT
// =========================================================

export interface EvaluationReport {
  id: string;

  interview_session_id: string;

  resume_id: string;

  role_id: string;

  completion_status: "completed";

  // Independent scores. No combined score.
  resume_score: number;

  interview_score: number;

  resume_report: ResumeEvaluation;

  interview_report: InterviewEvaluation;

  created_at: string;
}

// =========================================================
// GUEST TOKEN MANAGEMENT
// =========================================================

export function getGuestToken(): string | null {
  return localStorage.getItem(GUEST_TOKEN_KEY);
}

function saveGuestToken(token: string): void {
  localStorage.setItem(GUEST_TOKEN_KEY, token);
}

export function clearGuestToken(): void {
  localStorage.removeItem(GUEST_TOKEN_KEY);
}

// =========================================================
// HTTP RESPONSE HANDLING
// =========================================================

async function parseResponse<T>(
  response: Response,
): Promise<T> {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const body: unknown = await response.json();

      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        message = body.detail;
      }
    } catch {
      // Keep the original HTTP error.
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const headers = new Headers(options.headers);

  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (authenticated) {
    const token = getGuestToken();

    if (!token) {
      throw new Error("Guest authentication is required.");
    }

    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      headers,
    },
  );

  return parseResponse<T>(response);
}

// =========================================================
// GUEST IDENTITY
// =========================================================

export async function createGuest(): Promise<GuestIdentity> {
  const identity = await request<GuestIdentity>(
    "/api/guest",
    {
      method: "POST",
    },
    false,
  );

  if (!identity.access_token) {
    throw new Error(
      "The server returned an invalid guest identity.",
    );
  }

  saveGuestToken(identity.access_token);

  return identity;
}

export async function verifyGuest(): Promise<GuestStatus> {
  return request<GuestStatus>("/api/guest/me");
}

export async function ensureGuest(): Promise<GuestIdentity> {
  const existingToken = getGuestToken();

  if (existingToken) {
    try {
      await verifyGuest();

      return {
        access_token: existingToken,
        token_type: "bearer",
      };
    } catch {
      clearGuestToken();
    }
  }

  return createGuest();
}

// =========================================================
// RESUME MANAGEMENT
// =========================================================

export async function getResumeStatus(): Promise<ResumeStatus> {
  return request<ResumeStatus>("/api/resumes/me");
}

export async function uploadResume(
  file: File,
): Promise<ResumeStatus> {
  const formData = new FormData();

  formData.append("file", file);

  return request<ResumeStatus>(
    "/api/resumes",
    {
      method: "POST",
      body: formData,
    },
  );
}

export async function replaceResume(
  file: File,
): Promise<ResumeStatus> {
  const formData = new FormData();

  formData.append("file", file);

  return request<ResumeStatus>(
    "/api/resumes/me",
    {
      method: "PUT",
      body: formData,
    },
  );
}

export async function deleteResume(): Promise<void> {
  return request<void>(
    "/api/resumes/me",
    {
      method: "DELETE",
    },
  );
}

// =========================================================
// PERSISTENT INTERVIEW SESSIONS
// =========================================================

export async function createPersistentInterview(
  input: CreateInterviewSessionInput,
): Promise<CreatedInterviewSession> {
  if (!input.role_id.trim() || !input.resume_id.trim()) {
    throw new Error("Role and resume are required.");
  }

  return request<CreatedInterviewSession>(
    "/api/interview-sessions",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export async function listInterviewSessions(): Promise<
  InterviewSession[]
> {
  return request<InterviewSession[]>(
    "/api/interview-sessions",
  );
}

export async function getInterviewSession(
  sessionId: string,
): Promise<InterviewSession> {
  return request<InterviewSession>(
    `/api/interview-sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function dispatchPersistentInterview(
  sessionId: string,
): Promise<DispatchInterviewResponse> {
  return request<DispatchInterviewResponse>(
    `/api/interview-sessions/${encodeURIComponent(sessionId)}/dispatch`,
    {
      method: "POST",
    },
  );
}

export async function getInterviewTranscript(
  sessionId: string,
): Promise<TranscriptMessage[]> {
  return request<TranscriptMessage[]>(
    `/api/interview-sessions/${encodeURIComponent(sessionId)}/transcript`,
  );
}

export async function endPersistentInterview(
  sessionId: string,
): Promise<void> {
  return request<void>(
    `/api/interview-sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
    },
  );
}

// =========================================================
// MILESTONE 2.6 — GENERATE EVALUATION REPORT
// =========================================================

export async function generateEvaluationReport(
  sessionId: string,
): Promise<EvaluationReport> {
  if (!sessionId.trim()) {
    throw new Error("Interview session ID is required.");
  }

  return request<EvaluationReport>(
    `/api/interview-sessions/${encodeURIComponent(sessionId)}/report/generate`,
    {
      method: "POST",
    },
  );
}

// =========================================================
// MILESTONE 2.6 — RETRIEVE EVALUATION REPORT
// =========================================================

export async function getEvaluationReport(
  sessionId: string,
): Promise<EvaluationReport> {
  if (!sessionId.trim()) {
    throw new Error("Interview session ID is required.");
  }

  return request<EvaluationReport>(
    `/api/interview-sessions/${encodeURIComponent(sessionId)}/report`,
  );
}