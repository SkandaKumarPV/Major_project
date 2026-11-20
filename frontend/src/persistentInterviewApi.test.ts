import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  clearGuestToken,
  createGuest,
  createPersistentInterview,
  deleteResume,
  dispatchPersistentInterview,
  endPersistentInterview,
  ensureGuest,
  generateEvaluationReport,
  getEvaluationReport,
  getInterviewSession,
  getInterviewTranscript,
  getResumeStatus,
  listInterviewSessions,
  replaceResume,
  uploadResume,
  verifyGuest,
} from "./persistentInterviewApi";

const TOKEN = "test-guest-token";

function jsonResponse(
  data: unknown,
  status = 200,
): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
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
  localStorage.setItem(
    "career_arena_guest_token",
    TOKEN,
  );
}

function getRequestOptions(
  fetchMock: ReturnType<typeof vi.fn>,
  callIndex = 0,
): RequestInit {
  return fetchMock.mock.calls[callIndex][1] as RequestInit;
}

function getRequestHeaders(
  fetchMock: ReturnType<typeof vi.fn>,
  callIndex = 0,
): Headers {
  const options = getRequestOptions(fetchMock, callIndex);
  return new Headers(options.headers);
}

const SAMPLE_EVALUATION_REPORT = {
  id: "report-123",
  interview_session_id: "session-123",
  resume_id: "resume-123",
  role_id: "generative_ai_engineer",
  completion_status: "completed",

  resume_score: 8.2,
  interview_score: 7.4,

  resume_report: {
    score: 8.2,

    strengths: [
      {
        claim: "The candidate has Python experience.",
        evidence: "Python, FastAPI",
      },
    ],

    missing_or_weak_skills: [
      "Deployment experience is not clearly evidenced.",
    ],

    experience_alignment: [
      {
        claim: "Relevant RAG project",
        evidence: "Built a RAG application using FastAPI.",
      },
    ],

    improvement_areas: [
      "Add more detail about deployment experience.",
    ],

    score_rationale: (
      "The resume contains relevant backend experience."
    ),
  },

  interview_report: {
    score: 7.4,

    technical_strengths: [
      "Explained the basic RAG architecture.",
    ],

    weak_or_incorrect_answers: [
      "Retrieval evaluation was incomplete.",
    ],

    missing_concepts: [
      "Precision and recall.",
    ],

    answer_by_answer_feedback: [
      {
        question: "Explain a RAG application.",
        assessment: "Partially correct.",
        feedback: "Explain the complete retrieval flow.",
        missing_concepts: [
          "Context construction",
        ],
        correctness: "partially_correct",
        evidence: "A RAG application retrieves relevant documents.",
      },
      {
        question: "What is vector search?",
        assessment: "Technically correct.",
        feedback: "You correctly described similarity search.",
        missing_concepts: [],
        correctness: "technically_correct",
        evidence: "Vector search compares embeddings.",
      },
      {
        question: "How do you evaluate retrieval?",
        assessment: "Incomplete.",
        feedback: "Explain retrieval evaluation metrics.",
        missing_concepts: [
          "Precision",
          "Recall",
        ],
        correctness: "insufficient_evidence",
        evidence: "I would evaluate retrieval quality.",
      },
    ],

    reasoning_and_justification: (
      "The candidate demonstrated a reasonable understanding "
      + "of retrieval and generation."
    ),

    recommendations: [
      "Study retrieval evaluation metrics.",
    ],

    score_rationale: (
      "The candidate demonstrated partial-to-good technical knowledge."
    ),
  },

  created_at: "2026-11-20T10:00:00Z",
};

beforeEach(() => {
  const values = new Map<string, string>();

  const mockStorage = {
    getItem: (key: string): string | null =>
      values.get(key) ?? null,

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
  vi.restoreAllMocks();
});


/* ============================================================
   GUEST IDENTITY
============================================================ */

describe("guest identity", () => {
  it("creates a guest and saves the access token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      guestResponse(),
    );

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

    const headers = getRequestHeaders(fetchMock);

    expect(headers.get("Authorization")).toBe(
      `Bearer ${TOKEN}`,
    );
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

    expect(result.access_token).toBe(TOKEN);
    expect(result.token_type).toBe("bearer");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a new guest when the existing token is invalid", async () => {
    setToken();

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: "Invalid token",
          },
          401,
        ),
      )
      .mockResolvedValueOnce(guestResponse());

    vi.stubGlobal("fetch", fetchMock);

    const result = await ensureGuest();

    expect(result.access_token).toBe(TOKEN);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("requires authentication for protected requests", async () => {
    const fetchMock = vi.fn();

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getResumeStatus(),
    ).rejects.toThrow(
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

    await expect(
      getResumeStatus(),
    ).resolves.toEqual(resume);

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/resumes/me",
    );
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
      {
        type: "application/pdf",
      },
    );

    await uploadResume(file);

    const [url] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    const options = getRequestOptions(fetchMock);
    const headers = getRequestHeaders(fetchMock);

    expect(url).toContain("/api/resumes");
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);

    expect(headers.get("Authorization")).toBe(
      `Bearer ${TOKEN}`,
    );

    // Browser must set the multipart boundary itself.
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
      {
        type: "application/pdf",
      },
    );

    await replaceResume(file);

    const [url] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    const options = getRequestOptions(fetchMock);

    expect(options.method).toBe("PUT");
    expect(url).toContain("/api/resumes/me");
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("deletes the current resume", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 204,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      deleteResume(),
    ).resolves.toBeUndefined();

    const options = getRequestOptions(fetchMock);

    expect(options.method).toBe("DELETE");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/resumes/me",
    );
  });
});


/* ============================================================
   PERSISTENT INTERVIEW API
============================================================ */

describe("persistent interview API", () => {
  const createdSession = {
    id: "session-123",
    room_name: "room-123",
    role_id: "generative_ai_engineer",
    resume_id: "resume-123",
    status: "created",

    current_stage: "not_started",
    current_main_question_id: null,

    used_main_question_ids: [],
    follow_up_count: 0,

    completed_question_ids: [],
    completed_stages: [],

    created_at: "2026-11-20T09:00:00Z",
    started_at: null,
    ended_at: null,
  };

  const createdSessionResponse = {
    ...createdSession,
    livekit_url: "wss://example.livekit.cloud",
    participant_identity: "candidate-123",
    token: "livekit-token",
  };

  it("creates a persistent session with role and resume IDs", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        createdSessionResponse,
        201,
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await createPersistentInterview({
      role_id: "generative_ai_engineer",
      resume_id: "resume-123",
    });

    const [url] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    const options = getRequestOptions(fetchMock);
    const headers = getRequestHeaders(fetchMock);

    expect(result.id).toBe("session-123");

    expect(url).toContain("/api/interview-sessions");
    expect(options.method).toBe("POST");

    expect(JSON.parse(options.body as string)).toEqual({
      role_id: "generative_ai_engineer",
      resume_id: "resume-123",
    });

    expect(headers.get("Authorization")).toBe(
      `Bearer ${TOKEN}`,
    );
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
    ).rejects.toThrow(
      "Role and resume are required.",
    );

    await expect(
      createPersistentInterview({
        role_id: "generative_ai_engineer",
        resume_id: " ",
      }),
    ).rejects.toThrow(
      "Role and resume are required.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists candidate interview sessions", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        createdSession,
      ]),
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
      jsonResponse(createdSession),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await getInterviewSession("session-123");

    expect(result.id).toBe("session-123");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions/session-123",
    );
  });

  it("encodes session IDs when retrieving a session", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(createdSession),
    );

    vi.stubGlobal("fetch", fetchMock);

    await getInterviewSession("session/with spaces");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "session%2Fwith%20spaces",
    );
  });

  it("dispatches a persistent interview by session ID", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        session_id: "session-123",
        room_name: "room-123",
        agent_name: "interviewer",
        dispatched: true,
        status: "in_progress",
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await dispatchPersistentInterview(
      "session-123",
    );

    const options = getRequestOptions(fetchMock);

    expect(result.dispatched).toBe(true);

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
        created_at: "2026-11-20T10:00:00Z",
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

  it("ends a persistent interview and handles HTTP 204", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 204,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      endPersistentInterview("session-123"),
    ).resolves.toBeUndefined();

    const options = getRequestOptions(fetchMock);

    expect(options.method).toBe("DELETE");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions/session-123",
    );
  });
});


/* ============================================================
   MILESTONE 2.6 — REPORT API
============================================================ */

describe("evaluation report API", () => {
  it("generates an evaluation report for a completed session", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await generateEvaluationReport(
      "session-123",
    );

    const [url] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];

    const options = getRequestOptions(fetchMock);
    const headers = getRequestHeaders(fetchMock);

    expect(url).toContain(
      "/api/interview-sessions/session-123/report/generate",
    );

    expect(options.method).toBe("POST");

    expect(headers.get("Authorization")).toBe(
      `Bearer ${TOKEN}`,
    );

    expect(result.id).toBe("report-123");
    expect(result.completion_status).toBe("completed");
  });

  it("keeps resume and interview scores separate", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    const report = await generateEvaluationReport(
      "session-123",
    );

    expect(report.resume_score).toBe(8.2);
    expect(report.interview_score).toBe(7.4);

    expect(report.resume_score).not.toBe(
      report.interview_score,
    );

    expect(report.resume_report.score).toBe(8.2);
    expect(report.interview_report.score).toBe(7.4);

    expect(
      "overall_score" in report,
    ).toBe(false);
  });

  it("returns evidence-backed resume strengths", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    const report = await generateEvaluationReport(
      "session-123",
    );

    expect(report.resume_report.strengths).toEqual([
      {
        claim: "The candidate has Python experience.",
        evidence: "Python, FastAPI",
      },
    ]);
  });

  it("returns answer-by-answer technical feedback", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    const report = await generateEvaluationReport(
      "session-123",
    );

    const feedback =
      report.interview_report.answer_by_answer_feedback;

    expect(feedback).toHaveLength(3);

    expect(feedback[0].correctness).toBe(
      "partially_correct",
    );

    expect(feedback[1].correctness).toBe(
      "technically_correct",
    );

    expect(feedback[2].correctness).toBe(
      "insufficient_evidence",
    );
  });

  it("rejects report generation with an empty session ID", async () => {
    setToken();

    const fetchMock = vi.fn();

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateEvaluationReport(""),
    ).rejects.toThrow(
      "Interview session ID is required.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retrieves an existing evaluation report", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await getEvaluationReport(
      "session-123",
    );

    expect(result.id).toBe("report-123");
    expect(result.interview_session_id).toBe("session-123");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/interview-sessions/session-123/report",
    );

    expect(getRequestOptions(fetchMock).method).toBeUndefined();
  });

  it("encodes the session ID in report URLs", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    await getEvaluationReport("session/with spaces");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "session%2Fwith%20spaces/report",
    );
  });

  it("rejects report retrieval with an empty session ID", async () => {
    setToken();

    const fetchMock = vi.fn();

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getEvaluationReport(" "),
    ).rejects.toThrow(
      "Interview session ID is required.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("propagates the backend incomplete-interview error", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          detail: (
            "A completed report requires all three technical questions."
          ),
        },
        409,
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateEvaluationReport("session-123"),
    ).rejects.toThrow(
      "A completed report requires all three technical questions.",
    );
  });

  it("requires candidate authentication for report retrieval", async () => {
    const fetchMock = vi.fn();

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getEvaluationReport("session-123"),
    ).rejects.toThrow(
      "Guest authentication is required.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requires candidate authentication for report generation", async () => {
    const fetchMock = vi.fn();

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateEvaluationReport("session-123"),
    ).rejects.toThrow(
      "Guest authentication is required.",
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not expose raw resume extraction fields in the report type", async () => {
    setToken();

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(SAMPLE_EVALUATION_REPORT),
    );

    vi.stubGlobal("fetch", fetchMock);

    const report = await getEvaluationReport("session-123");

    expect(report.resume_report).toBeDefined();
    expect(report.interview_report).toBeDefined();

    expect(
      "raw_text" in report,
    ).toBe(false);

    expect(
      "structured_data" in report,
    ).toBe(false);
  });
});