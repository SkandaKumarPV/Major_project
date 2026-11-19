
export const INTERVIEW_EVENTS_TOPIC = "interview-events";

export const INTERVIEW_STATUSES = [
  "INITIALIZING",
  "AI_SPEAKING",
  "CANDIDATE_LISTENING",
  "CANDIDATE_SPEAKING",
  "WAITING_FOR_SILENCE",
  "PROCESSING_ANSWER",
  "INTERVIEW_ENDED",
  "ERROR",
] as const;

export type InterviewStatus = (typeof INTERVIEW_STATUSES)[number];

export type InterviewEvent =
  | {
      type: "status";
      status: InterviewStatus;
    }
  | {
      type: "transcript";
      text: string;
      is_final: boolean;
    };

export function parseInterviewEvent(
  payload: Uint8Array,
  topic?: string,
): InterviewEvent | null {
  if (topic !== INTERVIEW_EVENTS_TOPIC) {
    return null;
  }

  try {
    const decoded = new TextDecoder().decode(payload);
    const parsed: unknown = JSON.parse(decoded);

    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }

    const event = parsed as Record<string, unknown>;

    if (
      event.type === "status" &&
      typeof event.status === "string" &&
      INTERVIEW_STATUSES.includes(event.status as InterviewStatus)
    ) {
      return {
        type: "status",
        status: event.status as InterviewStatus,
      };
    }

    if (
      event.type === "transcript" &&
      typeof event.text === "string" &&
      typeof event.is_final === "boolean"
    ) {
      return {
        type: "transcript",
        text: event.text,
        is_final: event.is_final,
      };
    }

    return null;
  } catch {
    return null;
  }
}

export function microphoneShouldBeEnabled(
  status: InterviewStatus,
): boolean {
  return (
    status === "CANDIDATE_LISTENING" ||
    status === "CANDIDATE_SPEAKING" ||
    status === "WAITING_FOR_SILENCE"
  );
}
