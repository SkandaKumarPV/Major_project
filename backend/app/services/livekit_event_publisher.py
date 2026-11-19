
import asyncio
import json
import logging


logger = logging.getLogger("ai-interviewer-events")


class LiveKitEventPublisher:
    """Publishes interview status and transcript events to room participants."""

    TOPIC = "interview-events"

    def __init__(self, local_participant):
        self.local_participant = local_participant
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    def publish_status(self, status: str):
        self._schedule({
            "type": "status",
            "status": status,
        })

    def publish_transcript(self, text: str, is_final: bool):
        self._schedule({
            "type": "transcript",
            "text": text,
            "is_final": is_final,
        })

    def _schedule(self, message: dict):
        if self._closed:
            return

        task = asyncio.create_task(self._publish(message))
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)

    async def _publish(self, message: dict):
        payload = json.dumps(message).encode("utf-8")

        await self.local_participant.publish_data(
            payload,
            reliable=True,
            topic=self.TOPIC,
        )

    def _on_task_done(self, task: asyncio.Task):
        self._tasks.discard(task)

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Failed to publish interview event")

    async def close(self):
        self._closed = True

        pending_tasks = list(self._tasks)

        if pending_tasks:
            await asyncio.gather(
                *pending_tasks,
                return_exceptions=True,
            )
