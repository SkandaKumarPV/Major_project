
from types import SimpleNamespace

import pytest

from backend.app.agent import worker


def test_prewarm_loads_vad(monkeypatch):
    expected_vad = object()

    fake_silero = SimpleNamespace(
        VAD=SimpleNamespace(
            load=lambda: expected_vad
        )
    )

    monkeypatch.setattr(worker, "silero", fake_silero)

    proc = SimpleNamespace(userdata={})

    worker.prewarm(proc)

    assert proc.userdata["vad"] is expected_vad


def test_build_agent_session_uses_manual_turn_detection(monkeypatch):
    expected_stt = object()
    expected_tts = object()
    expected_provider = object()
    expected_llm = object()
    expected_vad = object()

    settings = SimpleNamespace()

    monkeypatch.setattr(
        worker,
        "DeepgramService",
        lambda settings: SimpleNamespace(stt=expected_stt),
    )

    monkeypatch.setattr(
        worker,
        "CartesiaService",
        lambda settings: SimpleNamespace(tts=expected_tts),
    )

    monkeypatch.setattr(
        worker,
        "LLMProvider",
        lambda settings: expected_provider,
    )

    monkeypatch.setattr(
        worker,
        "LiveKitLLM",
        lambda provider: expected_llm,
    )

    captured = {}

    class FakeAgentSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        worker,
        "AgentSession",
        FakeAgentSession,
    )

    worker.build_agent_session(settings, expected_vad)

    assert captured["turn_detection"] == "manual"
    assert captured["stt"] is expected_stt
    assert captured["vad"] is expected_vad
    assert captured["llm"] is expected_llm
    assert captured["tts"] is expected_tts
    assert captured["allow_interruptions"] is False


def test_build_worker_options_uses_livekit_credentials():
    settings = SimpleNamespace(
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="test-api-key",
        livekit_api_secret="test-api-secret",
        agent_name="simple-ai-interviewer",
    )

    options = worker.build_worker_options(settings)

    assert options.entrypoint_fnc is worker.entrypoint
    assert options.prewarm_fnc is worker.prewarm
    assert options.ws_url == settings.livekit_url
    assert options.api_key == settings.livekit_api_key
    assert options.api_secret == settings.livekit_api_secret
    assert options.agent_name == settings.agent_name


@pytest.mark.asyncio
async def test_entrypoint_connects_before_creating_publisher(monkeypatch):
    settings = SimpleNamespace(
        silence_timeout_seconds=10,
        opening_message="Hello! Welcome to your interview.",
    )

    monkeypatch.setattr(
        worker.Settings,
        "from_environment",
        staticmethod(lambda: settings),
    )

    fake_vad = object()
    local_participant = object()

    class FakeRoom:
        def __init__(self):
            self.connected = False

        @property
        def local_participant(self):
            if not self.connected:
                raise RuntimeError(
                    "cannot access local participant before connecting"
                )

            return local_participant

    class FakeSpeechHandle:
        def __init__(self):
            self.playout_completed = False

        async def wait_for_playout(self):
            self.playout_completed = True

    class FakeSession:
        def __init__(self):
            self.started = False
            self.start_arguments = None
            self.spoken_text = None
            self.speech_handle = FakeSpeechHandle()

        async def start(self, **kwargs):
            self.start_arguments = kwargs

            # Simulate AgentSession connecting to LiveKit.
            kwargs["room"].connected = True
            self.started = True

        def say(self, text, *, allow_interruptions):
            self.spoken_text = text

            assert allow_interruptions is False

            return self.speech_handle

    fake_session = FakeSession()

    monkeypatch.setattr(
        worker,
        "build_agent_session",
        lambda settings, vad: fake_session,
    )

    publisher_instances = []

    class FakePublisher:
        def __init__(self, participant):
            self.participant = participant
            publisher_instances.append(self)

        def publish_status(self, status):
            pass

        def publish_transcript(self, text, is_final):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(
        worker,
        "LiveKitEventPublisher",
        FakePublisher,
    )

    controller_arguments = {}

    class FakeController:
        def __init__(self, **kwargs):
            controller_arguments.update(kwargs)

        async def close(self):
            pass

    monkeypatch.setattr(
        worker,
        "LiveKitSessionController",
        FakeController,
    )

    class FakeContext:
        def __init__(self):
            self.room = FakeRoom()

            self.proc = SimpleNamespace(
                userdata={"vad": fake_vad}
            )

            self.connect_calls = 0
            self.shutdown_callbacks = []

        async def connect(self):
            self.connect_calls += 1

        def add_shutdown_callback(self, callback):
            self.shutdown_callbacks.append(callback)

    ctx = FakeContext()

    await worker.entrypoint(ctx)

    # No separate ctx.connect() call is required.
    assert ctx.connect_calls == 0

    # AgentSession.start() must connect the room.
    assert fake_session.started is True
    assert fake_session.start_arguments["room"] is ctx.room
    assert fake_session.start_arguments["agent"] is not None

    # Publisher must be created after the room connects.
    assert len(publisher_instances) == 1
    assert publisher_instances[0].participant is local_participant

    # Verify controller configuration.
    assert controller_arguments["session"] is fake_session

    assert controller_arguments["silence_timeout_seconds"] == 10

    assert controller_arguments["on_status"] == (
        publisher_instances[0].publish_status
    )

    assert controller_arguments["on_transcript"] == (
        publisher_instances[0].publish_transcript
    )

    # Verify the opening introduction is spoken.
    assert fake_session.spoken_text == settings.opening_message
    assert fake_session.speech_handle.playout_completed is True

    # Both resources must register shutdown callbacks.
    assert len(ctx.shutdown_callbacks) == 2


def test_create_interviewer_agent_has_instructions():
    agent = worker.create_interviewer_agent()

    assert agent is not None
