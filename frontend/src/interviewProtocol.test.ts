
import { describe, expect, it } from "vitest";

import {
  microphoneShouldBeEnabled,
  parseInterviewEvent,
} from "./interviewProtocol";

function encode(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value));
}

describe("parseInterviewEvent", () => {
  it("parses a valid status event", () => {
    const result = parseInterviewEvent(
      encode({
        type: "status",
        status: "AI_SPEAKING",
      }),
      "interview-events",
    );

    expect(result).toEqual({
      type: "status",
      status: "AI_SPEAKING",
    });
  });

  it("parses a valid transcript event", () => {
    const result = parseInterviewEvent(
      encode({
        type: "transcript",
        text: "I am studying computer science.",
        is_final: true,
      }),
      "interview-events",
    );

    expect(result).toEqual({
      type: "transcript",
      text: "I am studying computer science.",
      is_final: true,
    });
  });

  it("rejects messages from another topic", () => {
    expect(
      parseInterviewEvent(
        encode({
          type: "status",
          status: "AI_SPEAKING",
        }),
        "another-topic",
      ),
    ).toBeNull();
  });

  it("rejects invalid JSON", () => {
    const payload = new TextEncoder().encode("not-json");

    expect(
      parseInterviewEvent(payload, "interview-events"),
    ).toBeNull();
  });

  it("rejects unknown statuses", () => {
    expect(
      parseInterviewEvent(
        encode({
          type: "status",
          status: "UNKNOWN_STATUS",
        }),
        "interview-events",
      ),
    ).toBeNull();
  });

  it("rejects malformed transcript events", () => {
    expect(
      parseInterviewEvent(
        encode({
          type: "transcript",
          text: "Hello",
          is_final: "yes",
        }),
        "interview-events",
      ),
    ).toBeNull();
  });
});

describe("microphoneShouldBeEnabled", () => {
  it("enables the microphone while the candidate can speak", () => {
    expect(microphoneShouldBeEnabled("CANDIDATE_LISTENING")).toBe(true);
    expect(microphoneShouldBeEnabled("CANDIDATE_SPEAKING")).toBe(true);
    expect(microphoneShouldBeEnabled("WAITING_FOR_SILENCE")).toBe(true);
  });

  it("disables the microphone while the AI speaks or processes an answer", () => {
    expect(microphoneShouldBeEnabled("AI_SPEAKING")).toBe(false);
    expect(microphoneShouldBeEnabled("PROCESSING_ANSWER")).toBe(false);
    expect(microphoneShouldBeEnabled("INITIALIZING")).toBe(false);
    expect(microphoneShouldBeEnabled("INTERVIEW_ENDED")).toBe(false);
    expect(microphoneShouldBeEnabled("ERROR")).toBe(false);
  });
});
