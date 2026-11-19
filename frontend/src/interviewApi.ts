
const API_BASE_URL = "http://127.0.0.1:8000";

export interface InterviewSession {
  livekit_url: string;
  room_name: string;
  participant_identity: string;
  token: string;
}

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return;

  let message = `Request failed (${response.status})`;

  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      message = body.detail;
    }
  } catch {
    // Keep the HTTP status message.
  }

  throw new Error(message);
}

export async function createInterview(): Promise<InterviewSession> {
  const response = await fetch(`${API_BASE_URL}/api/interviews`, {
    method: "POST",
  });

  await checkResponse(response);

  const session: unknown = await response.json();

  if (
    typeof session !== "object" ||
    session === null ||
    typeof (session as InterviewSession).livekit_url !== "string" ||
    typeof (session as InterviewSession).room_name !== "string" ||
    typeof (session as InterviewSession).participant_identity !== "string" ||
    typeof (session as InterviewSession).token !== "string"
  ) {
    throw new Error("The server returned an invalid interview session.");
  }

  return session as InterviewSession;
}

export async function dispatchInterviewer(
  roomName: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/interviews/${encodeURIComponent(roomName)}/dispatch`,
    { method: "POST" },
  );

  await checkResponse(response);
}

export async function deleteInterview(roomName: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/interviews/${encodeURIComponent(roomName)}`,
    { method: "DELETE" },
  );

  await checkResponse(response);
}
