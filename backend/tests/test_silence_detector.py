
import asyncio

import pytest

from backend.app.core.silence_detector import SilenceDetector


@pytest.mark.asyncio
async def test_finalize_after_silence_timeout():
    finalized = asyncio.Event()

    async def on_finalize():
        finalized.set()

    detector = SilenceDetector(0.05, on_finalize)

    detector.speech_started()
    detector.speech_stopped()

    await asyncio.wait_for(finalized.wait(), timeout=0.2)

    await detector.close()


@pytest.mark.asyncio
async def test_new_speech_resets_silence_timer():
    finalized = asyncio.Event()

    async def on_finalize():
        finalized.set()

    detector = SilenceDetector(0.1, on_finalize)

    detector.speech_started()
    detector.speech_stopped()

    await asyncio.sleep(0.06)

    detector.speech_started()
    detector.speech_stopped()

    await asyncio.sleep(0.06)

    assert not finalized.is_set()

    await asyncio.wait_for(finalized.wait(), timeout=0.2)

    await detector.close()


@pytest.mark.asyncio
async def test_only_finalizes_once_per_speech_cycle():
    call_count = 0

    async def on_finalize():
        nonlocal call_count
        call_count += 1

    detector = SilenceDetector(0.05, on_finalize)

    detector.speech_started()
    detector.speech_stopped()

    await asyncio.sleep(0.1)

    assert call_count == 1

    detector.speech_stopped()
    await asyncio.sleep(0.1)

    assert call_count == 1

    await detector.close()


@pytest.mark.asyncio
async def test_speech_start_without_stop_does_not_finalize():
    finalized = asyncio.Event()

    async def on_finalize():
        finalized.set()

    detector = SilenceDetector(0.05, on_finalize)

    detector.speech_started()

    await asyncio.sleep(0.1)

    assert not finalized.is_set()

    await detector.close()


@pytest.mark.asyncio
async def test_detector_supports_multiple_answer_cycles():
    call_count = 0

    async def on_finalize():
        nonlocal call_count
        call_count += 1

    detector = SilenceDetector(0.05, on_finalize)

    # First answer
    detector.speech_started()
    detector.speech_stopped()

    await asyncio.sleep(0.1)

    assert call_count == 1

    # Second answer
    detector.speech_started()
    detector.speech_stopped()

    await asyncio.sleep(0.1)

    assert call_count == 2

    await detector.close()


@pytest.mark.asyncio
async def test_cancel_stops_pending_timer():
    finalized = asyncio.Event()

    async def on_finalize():
        finalized.set()

    detector = SilenceDetector(0.1, on_finalize)

    detector.speech_started()
    detector.speech_stopped()

    detector.cancel()

    await asyncio.sleep(0.15)

    assert not finalized.is_set()

    await detector.close()
