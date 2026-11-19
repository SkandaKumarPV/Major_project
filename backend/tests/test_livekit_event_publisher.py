
import json
import asyncio

import pytest

from backend.app.services.livekit_event_publisher import (
    LiveKitEventPublisher,
)


class FakeLocalParticipant:
    def __init__(self):
        self.messages = []

    async def publish_data(
        self,
        payload,
        *,
        reliable,
        topic,
    ):
        self.messages.append({
            "payload": payload,
            "reliable": reliable,
            "topic": topic,
        })


@pytest.mark.asyncio
async def test_publish_status_sends_reliable_event():
    participant = FakeLocalParticipant()
    publisher = LiveKitEventPublisher(participant)

    publisher.publish_status("AI_SPEAKING")

    await publisher.close()

    assert len(participant.messages) == 1

    message = participant.messages[0]
    decoded = json.loads(message["payload"].decode("utf-8"))

    assert decoded == {
        "type": "status",
        "status": "AI_SPEAKING",
    }

    assert message["reliable"] is True
    assert message["topic"] == "interview-events"


@pytest.mark.asyncio
async def test_publish_transcript_sends_text_and_final_flag():
    participant = FakeLocalParticipant()
    publisher = LiveKitEventPublisher(participant)

    publisher.publish_transcript(
        "I study computer science.",
        True,
    )

    await publisher.close()

    decoded = json.loads(
        participant.messages[0]["payload"].decode("utf-8")
    )

    assert decoded == {
        "type": "transcript",
        "text": "I study computer science.",
        "is_final": True,
    }


@pytest.mark.asyncio
async def test_publisher_can_send_multiple_events():
    participant = FakeLocalParticipant()
    publisher = LiveKitEventPublisher(participant)

    publisher.publish_status("AI_SPEAKING")
    publisher.publish_status("CANDIDATE_LISTENING")
    publisher.publish_transcript("Hello.", True)

    await publisher.close()

    assert len(participant.messages) == 3


@pytest.mark.asyncio
async def test_close_waits_for_pending_publications():
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowParticipant:
        async def publish_data(
            self,
            payload,
            *,
            reliable,
            topic,
        ):
            started.set()
            await release.wait()

    publisher = LiveKitEventPublisher(SlowParticipant())

    publisher.publish_status("AI_SPEAKING")

    await started.wait()

    closing = asyncio.create_task(publisher.close())

    await asyncio.sleep(0)

    assert not closing.done()

    release.set()
    await closing

    assert closing.done()


@pytest.mark.asyncio
async def test_publisher_does_not_send_after_close():
    participant = FakeLocalParticipant()
    publisher = LiveKitEventPublisher(participant)

    await publisher.close()

    publisher.publish_status("AI_SPEAKING")

    await asyncio.sleep(0)

    assert participant.messages == []
