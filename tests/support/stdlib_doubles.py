"""Shared pyiv 1.1 Memory*/Mock* bindings for unit tests.

Prefer ``stdlib_doubles_config(...)`` (override hooks that declare what
``configure()`` binds) when judge ``APIConnectionConfig`` must read the same
``Environment``. Use ``stdlib_doubles_overlay(...)`` with
``pyiv.override(base).with_(overlay)`` to swap only edge doubles on an
existing production Config; rebind ``APIConnectionConfig`` in the overlay
when judge env isolation matters (base ``configure()`` may have already
stamped a connection from OS env).

Composed services (``EventLog``, ``CheckpointStore``, …) take collaborators
via injection — do not call Config ``get_*`` from tests to pull them.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from pyiv import Config
from pyiv.files import Filesystem, MemoryFilesystem
from pyiv.log import LoggerFactory, MemoryLoggerFactory
from pyiv.process import Environment, MemoryEnvironment
from pyiv.time import Clock, DateTimeService, MockDateTimeService, SyntheticClock

from mechaharness.api_connection import APIConnectionConfig, SimpleHttpConnectionConfig
from mechaharness.di import MechaHarnessConfig
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy

_DEFAULT_FIXED = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def default_memory_environment(
    extra: Mapping[str, str] | None = None,
) -> MemoryEnvironment:
    """Judge-friendly MemoryEnvironment (base URL set unless overridden)."""
    data = {"MECHA_JUDGE_BASE_URL": "http://memory.invalid:9"}
    if extra:
        data.update(dict(extra))
    return MemoryEnvironment(data)


def stdlib_doubles_config(
    *,
    environment: Environment | None = None,
    datetime_service: DateTimeService | None = None,
    filesystem: Filesystem | None = None,
    logger_factory: LoggerFactory | None = None,
    clock: Clock | None = None,
    inference_class: type[InferenceStrategy] = MockInferenceStrategy,
    harness_class: type[AbstractHarness] = PassThroughHarness,
) -> MechaHarnessConfig:
    """Build a MechaHarnessConfig with Memory/Mock stdlib edges.

    Hooks return instances for ``configure()`` to ``register_instance``.
    Judge connection is built by the default injector factory from the same
    ``Environment`` binding.
    """
    env = environment if environment is not None else default_memory_environment()
    dts = (
        datetime_service
        if datetime_service is not None
        else MockDateTimeService(_DEFAULT_FIXED)
    )
    fs = filesystem if filesystem is not None else MemoryFilesystem()
    logs = logger_factory if logger_factory is not None else MemoryLoggerFactory()
    clk = clock if clock is not None else SyntheticClock(start_time=100.0)

    class DoublesConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return inference_class

        def get_harness_class(self) -> type[AbstractHarness]:
            return harness_class

        def get_environment(self) -> Environment:
            return env

        def get_datetime_service(self) -> DateTimeService:
            return dts

        def get_filesystem(self) -> Filesystem:
            return fs

        def get_logger_factory(self) -> LoggerFactory:
            return logs

        def get_clock(self) -> Clock:
            return clk

    return DoublesConfig()


def stdlib_doubles_overlay(
    *,
    environment: Environment | None = None,
    datetime_service: DateTimeService | None = None,
    filesystem: Filesystem | None = None,
    logger_factory: LoggerFactory | None = None,
    clock: Clock | None = None,
    rebind_judge_connection: bool = True,
) -> Config:
    """Overlay Config that replaces stdlib injectables (and optionally judge conn)."""
    env = environment
    dts = datetime_service
    fs = filesystem
    logs = logger_factory
    clk = clock
    rebind = rebind_judge_connection

    class Overlay(Config):
        def configure(self) -> None:
            if env is not None:
                self.register_instance(Environment, env)
                if rebind:
                    self.register_instance(
                        APIConnectionConfig,
                        SimpleHttpConnectionConfig.from_env(env=env),
                    )
            if dts is not None:
                self.register_instance(DateTimeService, dts)
            if fs is not None:
                self.register_instance(Filesystem, fs)
            if logs is not None:
                self.register_instance(LoggerFactory, logs)
            if clk is not None:
                self.register_instance(Clock, clk)

    return Overlay()


def fixed_utc(
    year: int = 2020,
    month: int = 1,
    day: int = 2,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    """UTC datetime helper for MockDateTimeService."""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def mock_datetime_service(
    year: int = 2020,
    month: int = 1,
    day: int = 2,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> MockDateTimeService:
    """``MockDateTimeService`` fixed at ``fixed_utc(...)``."""
    return MockDateTimeService(fixed_utc(year, month, day, hour, minute, second))


__all__ = [
    "default_memory_environment",
    "fixed_utc",
    "mock_datetime_service",
    "stdlib_doubles_config",
    "stdlib_doubles_overlay",
]
