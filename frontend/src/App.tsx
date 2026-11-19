
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
  createInterview,
  dispatchInterviewer,
  deleteInterview,
} from "./interviewApi";

import "./App.css";

const TRANSCRIPTION_TOPIC = "lk.transcription";

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

function App() {
  const roomRef = useRef<Room | null>(null);
  const roomNameRef = useRef<string | null>(null);
  const audioContainerRef = useRef<HTMLDivElement | null>(null);
  const transcriptIdRef = useRef(0);
  const latestStatusRef = useRef<InterviewStatus | null>(null);

  const [connected, setConnected] = useState(false);
  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [status, setStatus] = useState<InterviewStatus>("INITIALIZING");
  const [microphoneEnabled, setMicrophoneEnabled] = useState(false);
  const [audioNeedsGesture, setAudioNeedsGesture] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptLine[]>([]);
  const [interimTranscript, setInterimTranscript] =
    useState<InterimTranscript | null>(null);
  const [error, setError] = useState("");

  async function applyMicrophoneStatus(nextStatus: InterviewStatus) {
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

  function handleInterviewEvent(payload: Uint8Array, topic?: string) {
    const event = parseInterviewEvent(payload, topic);
    if (!event) return;

    // Custom data events continue to control interview status.
    // Transcripts are received separately through LiveKit text streams.
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

          if (!text || roomRef.current !== room) {
            return;
          }

          const attributes = reader.info.attributes ?? {};

          // Ignore ordinary text messages. We only want speech transcripts.
          const isTranscription =
            attributes["lk.transcribed_track_id"] !== undefined;

          if (!isTranscription) {
            return;
          }

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
            setInterimTranscript({
              speaker,
              text,
            });
          }
        } catch (err) {
          console.error("Failed to read interview transcription:", err);
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

  async function startInterview() {
    if (starting || roomRef.current) return;

    setStarting(true);
    setError("");
    setTranscripts([]);
    setInterimTranscript(null);
    transcriptIdRef.current = 0;
    setMicrophoneEnabled(false);
    setStatus("INITIALIZING");
    latestStatusRef.current = null;

    let room: Room | null = null;
    let createdRoomName: string | null = null;

    try {
      const session = await createInterview();
      createdRoomName = session.room_name;
      roomNameRef.current = session.room_name;

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

      // Register the transcription handler before joining the room.
      registerTranscriptionHandler(room);

      await room.connect(session.livekit_url, session.token);

      // Always start with the candidate microphone disabled.
      await room.localParticipant.setMicrophoneEnabled(false);
      setMicrophoneEnabled(false);
      setConnected(true);

      try {
        await room.startAudio();
        setAudioNeedsGesture(!room.canPlaybackAudio);
      } catch {
        setAudioNeedsGesture(true);
      }

      // Dispatch only after the candidate has joined the room.
      await dispatchInterviewer(session.room_name);
    } catch (err) {
      if (room) {
        await room.disconnect().catch(() => undefined);
      }

      roomRef.current = null;
      roomNameRef.current = null;
      setConnected(false);
      setMicrophoneEnabled(false);
      setInterimTranscript(null);

      if (createdRoomName) {
        try {
          await deleteInterview(createdRoomName);
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

  async function endInterview() {
    if (ending) return;

    setEnding(true);
    setError("");

    const room = roomRef.current;
    const roomName = roomNameRef.current;

    roomRef.current = null;
    roomNameRef.current = null;
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

    if (roomName) {
      try {
        await deleteInterview(roomName);
      } catch (err) {
        setError(
          err instanceof Error
            ? `Disconnected, but room cleanup failed: ${err.message}`
            : "Disconnected, but room cleanup failed.",
        );
      }
    }

    setEnding(false);
  }

  useEffect(() => {
    return () => {
      const room = roomRef.current;
      roomRef.current = null;

      if (room) {
        room.unregisterTextStreamHandler(TRANSCRIPTION_TOPIC);
        void room.disconnect();
      }
    };
  }, []);

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

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">LIVE INTERVIEW SESSION</p>
          <h1>AI Interviewer</h1>
          <p className="subtitle">
            A simple voice-based interview experience.
          </p>
        </div>

        <span className={`connection-pill ${connected ? "online" : ""}`}>
          <span className="connection-dot" />
          {connected ? "CONNECTED" : "DISCONNECTED"}
        </span>
      </header>

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
            <span>Interviewer</span>
            <strong>{speakerLabel}</strong>
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
              disabled={starting || ending}
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
      </section>

      <section className="transcript-card">
        <div className="transcript-heading">
          <div>
            <p className="eyebrow">CONVERSATION</p>
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
              <strong>
                {line.speaker}
              </strong>
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

      <div className="audio-container" ref={audioContainerRef} />
    </main>
  );
}

export default App;
