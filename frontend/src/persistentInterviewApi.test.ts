
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearGuestToken,
  createGuest,
  createPersistentInterview,
  deleteResume,
  dispatchPersistentInterview,
  ensureGuest,
  getInterviewSession,
  getInterviewTranscript,
  getResumeStatus,
  listInterviewSessions,
  replaceResume,
  uploadResume,
  verifyGuest,
} from "./persistentInterviewApi";

const TOKEN = "test-guest-token";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function guestResponse(): Response {
  return jsonResponse(
    {
      access_token: TOKEN,
      token_type: "bearer",
    },
    201,
  );
}

function setToken(): void {
  localStorage.setItem("career_arena_guest_token", TOKEN);
}

beforeEach(() => {
  const values = new Map<string, string>();

  const mockStorage = {
    getItem: (key: string): string | null => values.get(key) ?? null,

    setItem: (key: string, value: string): void => {
      values.set(key, String(value));
    },

    removeItem: (key: string): void => {
      values.delete(key);
    },

    clear: (): void => {
      values.clear();
    },

    key: (index: number): string | null =>
      Array.from(values.keys())[index] ?? null,

    get length(): number {
      return values.size;
    },
  };

  vi.stubGlobal("localStorage", mockStorage);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/* ============================================================
   GUEST IDENTITY
   ============================================================ */

describe("guest identity", () => {
  it("creates a guest and saves the access token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(guestResponse());
    vi.stubGlobal("fetch", fetchMock);

    const result = await createGuest();

    expect(result.access_token).toBe(TOKEN);

    expect(
      localStorage.getItem("career_arena_guest_token"),
    ).toBe(TOKEN);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/guest"),
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("verifies an existing guest using bearer authentication", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        authenticated: true,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(verifyGuest()).resolves.toEqual({
      authenticated: true,
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(options.headers);

    expect(headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("reuses an existing valid guest token", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        authenticated: true,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await ensureGuest();

    expect(result?.access_token).toBe(TOKEN);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a new guest when the existing token is invalid", async () => {
    setToken();

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: "Invalid token" },
          401,
        ),
      )
      .mockResolvedValueOnce(guestResponse());

    vi.stubGlobal("fetch", fetchMock);

    const result = await ensureGuest();

    expect(result?.access_token).toBe(TOKEN);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("requires authentication for protected requests", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(getResumeStatus()).rejects.toThrow(
      "Guest authentication is required.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("clears the guest token", () => {
    setToken();

    clearGuestToken();

    expect(
      localStorage.getItem("career_arena_guest_token"),
    ).toBeNull();
  });
});

/* ============================================================
   RESUME API
   ============================================================ */

describe("resume API", () => {
  it("retrieves the current resume status", async () => {
    setToken();

    const resume = {
      uploaded: true,
      resume_id: "resume-123",
      filename: "candidate.docx",
      status: "uploaded",
    };

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(resume),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(getResumeStatus()).resolves.toEqual(resume);

    expect(fetchMock.mock.calls[0][0]).toContain("/api/resumes/me");
  });

  it("uploads a resume using multipart form data", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          uploaded: true,
          resume_id: "resume-123",
          filename: "candidate.pdf",
          status: "uploaded",
        },
        201,
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    const file = new File(
      ["resume contents"],
      "candidate.pdf",
      { type: "application/pdf" },
    );

    await uploadResume(file);

    const [url, options] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    const headers = new Headers(options.headers);

    expect(url).toContain("/api/resumes");
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);
    expect(headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);

    // The browser must set the multipart boundary itself.
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("replaces a resume using PUT", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        uploaded: true,
        resume_id: "resume-123",
        filename: "replacement.pdf",
        status: "uploaded",
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    const file = new File(
      ["replacement resume"],
      "replacement.pdf",
      { type: "application/pdf" },
    );

    await replaceResume(file);

    const [url, options] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    expect(options.method).toBe("PUT");
    expect(url).toContain("/api/resumes/me");
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("deletes the current resume", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteResume()).resolves.toBeUndefined();

    const options = fetchMock.mock.calls[0][1] as RequestInit;

    expect(options.method).toBe("DELETE");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/resumes/me");
  });
});

/* ============================================================
   PERSISTENT INTERVIEW API
   ============================================================ */

describe("persistent interview API", () => {
  const createdSession = {
    session: {
      id: "session-123",
      room_name: "room-123",
      candidate_id: "candidate-123",
      resume_id: "resume-123",
      role_id: "generative_ai_engineer",
      status: "created",
      current_stage: "not_started",
      created_at: "2026-11-20T09:00:00Z",
      started_at: null,
      ended_at: null,
    },
    livekit_url: "wss://example.livekit.cloud",
    participant_identity: "candidate-123",
    token: "livekit-token",
  };

  it("creates a persistent session with role and resume IDs", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(createdSession, 201),
    );

    vi.stubGlobal("fetch", fetchMock);

    await createPersistentInterview({
      role_id: "generative_ai_engineer",
      resume_id: "resume-123",
    });

    const [url, options] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    const headers = new Headers(options.headers);

    expect(url).toContain("/api/interview-sessions");
    expect(options.method).toBe("POST");

    expect(JSON.parse(options.body as string)).toEqual({
      role_id: "generative_ai_engineer",
      resume_id: "resume-123",
    });

    expect(headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("rejects session creation without a role or resume", async () => {
    setToken();

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createPersistentInterview({
        role_id: "",
        resume_id: "resume-123",
      }),
    ).rejects.toThrow("Role and resume are required.");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists candidate interview sessions", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([createdSession.session]),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await listInterviewSessions();

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("session-123");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions",
    );
  });

  it("retrieves one interview session", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(createdSession.session),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await getInterviewSession("session-123");

    expect(result.id).toBe("session-123");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions/session-123",
    );
  });

  it("dispatches a persistent interview by session ID", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        dispatched: true,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await dispatchPersistentInterview("session-123");

    const options = fetchMock.mock.calls[0][1] as RequestInit;

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions/session-123/dispatch",
    );

    expect(options.method).toBe("POST");
  });

  it("retrieves the persisted transcript", async () => {
    setToken();

    const transcript = [
    {
        id: "message-1",
        sequence_number: 1,
        speaker: "interviewer",
        message_text: "Welcome to the interview.",
        created_at: "2026-11-20T10:00:00",
    },
    ];

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(transcript),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await getInterviewTranscript("session-123");

    expect(result).toEqual(transcript);
    expect(result).toHaveLength(1);

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions/session-123/transcript",
    );
  });
});
