"""pyiv 1.1 use-case doubles wired through MechaHarness edges."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pyiv import override
from pyiv.files import Filesystem, MemoryFilesystem
from pyiv.log import LoggerFactory, MemoryLoggerFactory
from pyiv.process import Environment, MemoryEnvironment
from pyiv.time import Clock, DateTimeService, MockDateTimeService, SyntheticClock

from mechaharness.api_connection import APIConnectionConfig, SimpleHttpConnectionConfig
from mechaharness.checkpoint_store import CheckpointStore, EventLogCheckpointStore
from mechaharness.core.events import (
    LOGGER_NAME,
    Event,
    InMemoryEventLog,
    LoggingEventLog,
    RunStart,
    event_type_key,
)
from mechaharness.decision_log import DecisionLog, DecisionRecord
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.external_effect import EffectRecord, EffectState
from mechaharness.graph import ExecutionGraph, GraphNode, GraphStore, NodeStatus
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
from tests.support.stdlib_doubles import (
    default_memory_environment,
    fixed_utc,
    stdlib_doubles_config,
    stdlib_doubles_overlay,
)


class _ProdBase(MechaHarnessConfig):
    def get_inference_class(self):  # type: ignore[no-untyped-def]
        return MockInferenceStrategy

    def get_harness_class(self):  # type: ignore[no-untyped-def]
        return PassThroughHarness


def test_config_registers_stdlib_doubles() -> None:
    env = default_memory_environment({"MECHA_JUDGE_BASE_URL": "http://mem:9"})
    inj = get_injector(
        stdlib_doubles_config(
            environment=env,
            datetime_service=MockDateTimeService(fixed_utc(2020, 1, 2)),
        )
    )
    assert inj.inject(Environment).get("MECHA_JUDGE_BASE_URL") == "http://mem:9"
    assert inj.inject(DateTimeService).now_utc_iso().startswith("2020-01-02")
    assert inj.inject(APIConnectionConfig).endpoint_url().startswith("http://mem:9")


def test_override_swaps_only_edge_doubles() -> None:
    env = MemoryEnvironment(
        {
            "MECHA_JUDGE_BASE_URL": "http://overlay:9",
            "MECHA_JUDGE_MODEL": "laya",
        }
    )
    dts = MockDateTimeService(fixed_utc(2021, 2, 3))
    fs = MemoryFilesystem()
    logs = MemoryLoggerFactory()
    clock = SyntheticClock(start_time=50.0)
    inj = get_injector(
        override(_ProdBase).with_(
            stdlib_doubles_overlay(
                environment=env,
                datetime_service=dts,
                filesystem=fs,
                logger_factory=logs,
                clock=clock,
                rebind_judge_connection=True,
            )
        )
    )
    assert inj.inject(Environment) is env
    assert inj.inject(DateTimeService) is dts
    assert inj.inject(Filesystem) is fs
    assert inj.inject(LoggerFactory) is logs
    assert inj.inject(Clock) is clock
    assert inj.inject(APIConnectionConfig).endpoint_url() == "http://overlay:9/v1/systemone"
    assert inj.inject(APIConnectionConfig).model_id() == "laya"
    store = inj.inject(CheckpointStore)
    assert isinstance(store, EventLogCheckpointStore)


def test_from_env_empty_memory_environment_missing_base() -> None:
    conn = SimpleHttpConnectionConfig.from_env(env=MemoryEnvironment())
    with pytest.raises(ValueError, match="MECHA_JUDGE_BASE_URL"):
        conn.endpoint_url()


def test_from_env_legacy_only_when_judge_keys_absent() -> None:
    env = MemoryEnvironment(
        {
            "MECHA_DECIDE_BASE_URL": "http://legacy:8009",
            "MECHA_DECIDE_MODEL": "kev",
        }
    )
    conn = SimpleHttpConnectionConfig.from_env(env=env)
    assert conn.endpoint_url() == "http://legacy:8009/v1/systemone"
    assert conn.model_id() == "kev"

    preferred = MemoryEnvironment(
        {
            "MECHA_JUDGE_BASE_URL": "http://judge:1",
            "MECHA_JUDGE_MODEL": "laya",
            "MECHA_DECIDE_BASE_URL": "http://legacy:8009",
            "MECHA_DECIDE_MODEL": "kev",
        }
    )
    conn2 = SimpleHttpConnectionConfig.from_env(env=preferred)
    assert conn2.endpoint_url() == "http://judge:1/v1/systemone"
    assert conn2.model_id() == "laya"


def test_decision_log_jsonl_via_memory_filesystem() -> None:
    fs = MemoryFilesystem()
    log = DecisionLog(jsonl_path="/decisions.jsonl", filesystem=fs)
    log.record(
        DecisionRecord(
            eventId="d1",
            stateHash="h",
            policyVersion="p1",
            verdict="ALLOW",
        )
    )
    log.record(
        DecisionRecord(
            eventId="d2",
            stateHash="h2",
            policyVersion="p1",
            verdict="DENY",
        )
    )
    rows = list(log.iter_jsonl())
    assert [r.event_id for r in rows] == ["d1", "d2"]
    assert fs.read_text("/decisions.jsonl").count("\n") == 2


def test_checkpoint_effect_stamp_advances() -> None:
    clock = MockDateTimeService(datetime(2019, 6, 1, tzinfo=timezone.utc))
    store = EventLogCheckpointStore(
        GraphStore(InMemoryEventLog()),
        datetime_service=clock,
    )
    first = store.save_effect(
        EffectRecord(
            effect_id="r1:n:1",
            run_id="r1",
            node_id="n",
            node_attempt=1,
            backend_id="host.test",
            state=EffectState.INTENDED,
        )
    )
    assert first.created_at.startswith("2019-06-01")
    assert first.updated_at.startswith("2019-06-01")

    clock.set_time(datetime(2019, 6, 2, 12, 0, 0, tzinfo=timezone.utc))
    second = store.save_effect(
        first.model_copy(update={"state": EffectState.ACCEPTED, "external_handle": "h1"})
    )
    assert second.created_at.startswith("2019-06-01")
    assert second.updated_at.startswith("2019-06-02")
    assert second.revision == first.revision + 1


def test_sqlite_checkpoint_stamps_with_datetime_service(tmp_path) -> None:  # type: ignore[no-untyped-def]
    clock = MockDateTimeService(fixed_utc(2018, 3, 4, 5, 6, 7))
    store = SqliteCheckpointStore(tmp_path / "runs.sqlite", datetime_service=clock)
    try:
        graph = ExecutionGraph(goal="stamp")
        graph.add_node(GraphNode(id="n", kind="compute", status=NodeStatus.PENDING))
        store.save(graph, run_id="r1", boundary="dispatch", fingerprint="fp")
        effect = store.save_effect(
            EffectRecord(
                effect_id="r1:n:1",
                run_id="r1",
                node_id="n",
                node_attempt=1,
                backend_id="host.test",
                state=EffectState.INTENDED,
            )
        )
        assert effect.created_at.startswith("2018-03-04T05:06:07")
        clock.set_time(fixed_utc(2018, 3, 5))
        again = store.save_effect(
            effect.model_copy(update={"state": EffectState.ACCEPTED})
        )
        assert again.created_at.startswith("2018-03-04")
        assert again.updated_at.startswith("2018-03-05")
    finally:
        store.close()


def test_logging_event_log_memory_factory() -> None:
    factory = MemoryLoggerFactory()
    log = LoggingEventLog(logger_factory=factory)
    log.emit(
        Event(
            type=event_type_key(RunStart),
            agent_id="a",
            run_id="r1",
            payload={"prompt_chars": "3"},
        )
    )
    records = factory.get(LOGGER_NAME).records
    assert len(records) == 1
    assert '"core:run_start"' in records[0].message
