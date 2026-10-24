"""In-flight Completer progress ticks and hard inference timeout."""

from __future__ import annotations

import asyncio

import pytest

from mechaharness.inference_progress import (
    InferenceTimeoutError,
    await_while_running,
    inference_progress_tick_seconds,
    inference_timeout_seconds,
)


@pytest.mark.asyncio
async def test_await_while_running_ticks_only_while_pending() -> None:
    ticks: list[float] = []

    async def slow() -> str:
        await asyncio.sleep(0.35)
        return "ok"

    result = await await_while_running(
        slow(),
        timeout_seconds=2.0,
        tick_seconds=0.1,
        on_tick=ticks.append,
    )
    assert result == "ok"
    assert len(ticks) >= 2
    assert all(t > 0 for t in ticks)


@pytest.mark.asyncio
async def test_await_while_running_timeout_cancels_and_raises() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang() -> str:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "nope"

    with pytest.raises(InferenceTimeoutError, match="still running"):
        await await_while_running(
            hang(),
            timeout_seconds=0.2,
            tick_seconds=0.05,
            on_tick=lambda _e: None,
        )
    assert started.is_set()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_await_while_running_no_ticks_after_done() -> None:
    ticks: list[float] = []

    async def fast() -> int:
        return 7

    assert (
        await await_while_running(
            fast(),
            timeout_seconds=2.0,
            tick_seconds=0.05,
            on_tick=ticks.append,
        )
        == 7
    )
    assert ticks == []


def test_inference_timeout_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MECHA_INFERENCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("MECHA_HTTP_TIMEOUT_SECONDS", "90")
    assert inference_timeout_seconds() == 90.0
    monkeypatch.setenv("MECHA_INFERENCE_TIMEOUT_SECONDS", "240")
    assert inference_timeout_seconds() == 240.0
    monkeypatch.setenv("MECHA_INFERENCE_PROGRESS_TICK_SECONDS", "0.5")
    assert inference_progress_tick_seconds() == 1.0
