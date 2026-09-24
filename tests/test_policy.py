"""Policy verdict + decision log + replay tests."""

from __future__ import annotations

from pathlib import Path

from mechaharness.decisions import DecisionLog, DecisionRecord, replay_verdict
from mechaharness.inference.judge import NoulSignal
from mechaharness.operations import UnsupportedOperation, default_operations
from mechaharness.policy import JudgementFacts, JudgementPolicy, JudgementThreshold, decide


def test_deny_precedence_and_unknown_signal() -> None:
    policy = JudgementPolicy(
        version="gate-fixture-v1",
        thresholds=[
            JudgementThreshold(signal_id="destructive", deny_below=0.3, allow_above=0.8, ask_below=0.8),
        ],
    )
    deny = decide(
        JudgementFacts(action="delete"),
        [NoulSignal(id="destructive", p_true=0.1)],
        policy,
    )
    assert deny.kind == "DENY"

    unknown = decide(
        JudgementFacts(action="delete"),
        [NoulSignal(id="other", p_true=0.9)],
        policy,
    )
    assert unknown.kind == "DENY"
    assert "UNKNOWN_SIGNAL" in unknown.reason_codes


def test_ask_human_band_and_approval_reuse() -> None:
    policy = JudgementPolicy(
        version="gate-fixture-v1",
        require_approval_for=["mutate"],
        thresholds=[
            JudgementThreshold(signal_id="destructive", allow_above=0.9, ask_below=0.9),
        ],
    )
    ask = decide(
        JudgementFacts(action="noop"),
        [NoulSignal(id="destructive", p_true=0.52)],
        policy,
    )
    assert ask.kind == "ASK_HUMAN"

    missing = decide(
        JudgementFacts(action="mutate", action_digest="sha256:abc"),
        [NoulSignal(id="destructive", p_true=0.95)],
        policy,
    )
    assert missing.kind == "ASK_HUMAN"
    assert "MISSING_APPROVAL" in missing.reason_codes

    ok = decide(
        JudgementFacts(
            action="mutate",
            action_digest="sha256:abc",
            approvals={"sha256:abc": "approved-1"},
        ),
        [NoulSignal(id="destructive", p_true=0.95)],
        policy,
    )
    assert ok.kind == "ALLOW"


def test_decisions_jsonl_and_replay(tmp_path: Path) -> None:
    path = tmp_path / "decisions.jsonl"
    log = DecisionLog(jsonl_path=path)
    policy = JudgementPolicy(
        version="gate-fixture-v1",
        thresholds=[JudgementThreshold(signal_id="destructive", allow_above=0.5)],
    )
    signals = [NoulSignal(id="destructive", p_true=0.52)]
    verdict = decide(JudgementFacts(action="x"), signals, policy)
    log.record(
        DecisionRecord(
            event_id="d17",
            run_id="r1",
            state_hash="sha256:example",
            signals={"destructive": 0.52},
            policy_version=policy.version,
            verdict=verdict.kind,
            reason_codes=verdict.reason_codes,
        )
    )
    rows = list(log.iter_jsonl())
    assert len(rows) == 1
    assert rows[0].verdict == verdict.kind
    replayed = replay_verdict(facts=JudgementFacts(action="x"), signals=signals, policy=policy)
    assert replayed.kind == verdict.kind
    assert replayed.reason_codes == verdict.reason_codes


def test_operation_registry_rejects_unknown() -> None:
    ops = default_operations()
    assert ops.supports("judge")
    try:
        ops.require("predictive_world_model")
        raise AssertionError("expected UnsupportedOperation")
    except UnsupportedOperation:
        pass
