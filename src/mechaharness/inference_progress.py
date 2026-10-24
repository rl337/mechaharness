"""Watch a running Completer awaitable: MCP progress ticks + hard timeout.

Ticks fire only while the awaitable is still pending (inference still
running). After ``timeout_seconds`` the awaitable is cancelled and
:class:`InferenceTimeoutError` is raised.

Env (not Settings):

- ``MECHA_INFERENCE_TIMEOUT_SECONDS`` — hard ceiling (falls back to
  ``MECHA_HTTP_TIMEOUT_SECONDS``, then ``180``)
- ``MECHA_INFERENCE_PROGRESS_TICK_SECONDS`` — tick interval while pending
  (default ``5``)
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

TickFn = Callable[[float], None]


class InferenceTimeoutError(TimeoutError):
    """Completer / inference awaitable exceeded the configured ceiling."""


def inference_timeout_seconds() -> float:
    """Hard ceiling for one Completer round (seconds)."""
    for key in ("MECHA_INFERENCE_TIMEOUT_SECONDS", "MECHA_HTTP_TIMEOUT_SECONDS"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            try:
                value = float(raw)
            except ValueError:
                continue
            if value > 0:
                return value
    return 180.0


def inference_progress_tick_seconds() -> float:
    """Seconds between in-flight progress ticks (minimum 1s)."""
    raw = (os.environ.get("MECHA_INFERENCE_PROGRESS_TICK_SECONDS") or "5").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 5.0
    return max(1.0, value)


async def await_while_running(
    awaitable: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
    tick_seconds: float | None = None,
    on_tick: TickFn | None = None,
) -> T:
    """Await *awaitable*, ticking only while it is still pending.

    If wall time exceeds *timeout_seconds*, cancel the task and raise
    :class:`InferenceTimeoutError`.
    """
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else inference_timeout_seconds()
    )
    tick = (
        float(tick_seconds)
        if tick_seconds is not None
        else inference_progress_tick_seconds()
    )
    if timeout <= 0:
        raise InferenceTimeoutError("inference timeout_seconds must be positive")
    if tick <= 0:
        raise InferenceTimeoutError("inference tick_seconds must be positive")

    task = asyncio.ensure_future(awaitable)
    start = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - start
            remaining = timeout - elapsed
            if remaining <= 0:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
                    raise InferenceTimeoutError(
                        f"inference still running after {timeout:.0f}s "
                        f"(MECHA_INFERENCE_TIMEOUT_SECONDS)"
                    )
                return await task

            wait = min(tick, remaining)
            done, _ = await asyncio.wait({task}, timeout=wait)
            if task in done:
                return await task

            # Only heartbeat when we can tell inference is still running.
            if not task.done() and on_tick is not None:
                on_tick(time.monotonic() - start)
    except InferenceTimeoutError:
        raise
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
        raise


__all__ = [
    "InferenceTimeoutError",
    "await_while_running",
    "inference_progress_tick_seconds",
    "inference_timeout_seconds",
]
