
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createInterview,
  deleteInterview,
  dispatchInterviewer,
} from "./interviewApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("interviewApi", () => {
  it("creates an interview and returns the server session", async () => {
    const session = {
      livekit_url: "wss://example.livekit.cloud",
      room_name: "interview-test",
      participant_identity: "candidate-test",
      token: "test-token",
    };

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(session), { status: 201 }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(createInterview()).resolves.toEqual(session);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/interviews",
      { method: "POST" },
    );
  });

  it("rejects an invalid session response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ room_name: "interview-test" }), {
          status: 201,
        }),
      ),
    );

    await expect(createInterview()).rejects.toThrow(
      "invalid interview session",
    );
  });

  it("reports API error details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "LiveKit unavailable" }), {
          status: 502,
        }),
      ),
    );

    await expect(createInterview()).rejects.toThrow(
      "LiveKit unavailable",
    );
  });

  it("dispatches the interviewer after connection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          room_name: "interview-test",
          agent_name: "simple-ai-interviewer",
          dispatched: true,
        }),
        { status: 202 },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(dispatchInterviewer("interview-test")).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/interviews/interview-test/dispatch",
      { method: "POST" },
    );
  });

  it("deletes an interview", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteInterview("interview-test")).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/interviews/interview-test",
      { method: "DELETE" },
    );
  });
});
