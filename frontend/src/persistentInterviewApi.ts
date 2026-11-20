
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const GUEST_TOKEN_KEY = "career_arena_guest_token";

export interface GuestIdentity {
  access_token: string;
  token_type: "bearer";
}

export interface GuestStatus {
  authenticated: boolean;
}

export interface ResumeStatus {
  uploaded: boolean;
  resume_id: string | null;
  filename: string | null;
  status: string;
}

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

export interface TranscriptMessage {
  id: string;
  sequence_number: number;
  speaker: string;
  message_text: string;
  created_at: string;
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

export function getGuestToken(): string | null {
  return localStorage.getItem(GUEST_TOKEN_KEY);
}

function saveGuestToken(token: string): void {
  localStorage.setItem(GUEST_TOKEN_KEY, token);
}

export function clearGuestToken(): void {
  localStorage.removeItem(GUEST_TOKEN_KEY);
}

async function parseResponse<T>(response: Response): Promise<T> {
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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  return parseResponse<T>(response);
}

/* ---------------- Guest identity ---------------- */

export async function createGuest(): Promise<GuestIdentity> {
  const identity = await request<GuestIdentity>(
    "/api/guest",
    { method: "POST" },
    false,
  );

  if (!identity.access_token) {
    throw new Error("The server returned an invalid guest identity.");
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

/* ---------------- Resume management ---------------- */

export async function getResumeStatus(): Promise<ResumeStatus> {
  return request<ResumeStatus>("/api/resumes/me");
}

export async function uploadResume(file: File): Promise<ResumeStatus> {
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

export async function replaceResume(file: File): Promise<ResumeStatus> {
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
    { method: "DELETE" },
  );
}

/* ---------------- Persistent interview sessions ---------------- */

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

export async function listInterviewSessions(): Promise<InterviewSession[]> {
  return request<InterviewSession[]>("/api/interview-sessions");
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
    { method: "POST" },
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
    { method: "DELETE" },
  );
}
