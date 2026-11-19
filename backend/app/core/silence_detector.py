
import asyncio
from collections.abc import Awaitable, Callable


class SilenceDetector:
    def __init__(
        self,
        timeout_seconds: float,
        on_finalize: Callable[[], Awaitable[None]],
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        self.timeout_seconds = timeout_seconds
        self.on_finalize = on_finalize

        self._timer_task: asyncio.Task | None = None
        self._finalized = False
        self._speech_active = False

    def speech_started(self):
        # A new speech segment starts a new answer cycle.
        self._finalized = False
        self._speech_active = True

        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        self._timer_task = None

    def speech_stopped(self):
        if not self._speech_active or self._finalized:
            return

        self._speech_active = False
        self._timer_task = asyncio.create_task(
            self._wait_for_silence()
        )

    def cancel(self):
        """Cancel the current timer without closing the detector."""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        self._timer_task = None
        self._speech_active = False

    async def _wait_for_silence(self):
        try:
            await asyncio.sleep(self.timeout_seconds)

            if not self._speech_active and not self._finalized:
                self._finalized = True
                await self.on_finalize()

        except asyncio.CancelledError:
            pass

    async def close(self):
        self.cancel()

        if self._timer_task:
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass

        self._timer_task = None
