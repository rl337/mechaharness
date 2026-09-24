"""Shadow judge, routing, graph, CTX, EXP tests."""

from __future__ import annotations

import pytest

from mechaharness.context_experiments import (
    CtxFlags,
    ObservationRef,
    ObservationStore,
    compact_at_boundary,
    fuse_actions,
    reduce_evidence,
)
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    GraphStore,
    NodeStatus,
    bounded_repair,
)
from mechaharness.inference.judge import (
    FixtureJudgeProvider,
    JudgeRequest,
    NoulQuestion,
    hash_state,
)
from mechaharness.research import EvalProtocol, ResearchLab, run_bounded_search
from mechaharness.routing import ShadowJudgeLog, activate_scoped_policy, route_at_boundary, shadow_judge
from mechaharness.policy import JudgementFacts, JudgementPolicy, JudgementThreshold
from mechaharness.inference.judge import NoulSignal


@pytest.mark.asyncio
async def test_shadow_judge_does_not_require_activation() -> None:
    log = ShadowJudgeLog()
    provider = FixtureJudgeProvider({"e": {"p_true": 0.4}})
    req = JudgeRequest(
        state="s",
        state_hash=hash_state("s"),
        questions=[NoulQuestion(id="e", instructions="?")],
        question_set_version="v1",
    )
    result = await shadow_judge(req, provider=provider, log=log, activate=False)
    assert result.answers
    assert log.entries[0]["activated"] is False


def test_route_at_boundary_logs_candidates() -> None:
    decision = route_at_boundary(boundary="task_entry", task_kind="judge")
    assert decision.selected.lane == "judge"
    assert len(decision.candidates) >= 2
    assert any(c.lane == "reason" for c in decision.candidates)


def test_activate_scoped_policy_requires_calibration() -> None:
    policy = JudgementPolicy(
        version="v1",
        thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
    )
    assert (
        activate_scoped_policy(
            facts=JudgementFacts(),
            signals=[NoulSignal(id="e", p_true=0.9)],
            policy=policy,
            calibrated=False,
        )
        is None
    )
    verdict = activate_scoped_policy(
        facts=JudgementFacts(),
        signals=[NoulSignal(id="e", p_true=0.9)],
        policy=policy,
        calibrated=True,
    )
    assert verdict is not None
    assert verdict.kind == "ALLOW"


def test_graph_checkpoint_resume_and_verification() -> None:
    graph = ExecutionGraph(goal="media render")
    n1 = graph.add_node(GraphNode(id="submit", kind="tool", acceptance=["prompt_id"]))
    n2 = graph.add_node(
        GraphNode(id="fetch", kind="tool", depends_on=["submit"], acceptance=["file"])
    )
    n1.status = NodeStatus.SUCCEEDED
    n1.evidence = {"prompt_id": "p1"}
    ready = graph.ready_nodes()
    assert any(n.id == "fetch" for n in ready)

    store = GraphStore()
    store.save(graph, run_id="r1")
    restored = store.latest(run_id="r1")
    assert restored is not None
    assert "fetch" in restored.nodes

    def has_file(node: GraphNode) -> tuple[bool, dict]:
        ok = bool(node.payload.get("path"))
        return ok, {"file": node.payload.get("path")}

    node = GraphNode(id="x", payload={})
    failed = bounded_repair(node, verifiers=[has_file], repair=lambda n: n.model_copy(update={"payload": {"path": "/tmp/out.png"}}))
    # first attempt fails, repair adds path, second succeeds
    assert failed.status == NodeStatus.SUCCEEDED


def test_ctx_flags_default_off_and_provenance() -> None:
    store = ObservationStore()
    ref = store.put(ObservationRef(tool_name="comfy", content="raw bytes"))
    flags = CtxFlags(evidence_reduction=True, economic_compaction=True, action_fusion=True)
    receipt = reduce_evidence(store, ref.id, summary="ok", flags=flags)
    assert receipt.fabricated is False
    fake = reduce_evidence(store, "obs:missing", summary="lie", flags=flags)
    assert fake.fabricated is True
    compacted = compact_at_boundary(
        [{"role": "user", "content": str(i)} for i in range(10)],
        flags=flags,
        keep_last=2,
    )
    assert len(compacted) < 10
    assert fuse_actions(["edit", "test"], allowed_sequences=[["edit", "test"]], flags=flags) == [
        "edit",
        "test",
    ]
    assert fuse_actions(["edit", "test"], allowed_sequences=[["edit", "test"]], flags=CtxFlags()) is None


def test_research_rejects_cheaper_worse() -> None:
    lab = ResearchLab(
        EvalProtocol(task_split="frozen-v1"),
        baseline_metric=0.8,
    )
    results = run_bounded_search(
        lab,
        [
            ("use tiny model", {"model": "tiny"}, 0.5, True),
            ("better prompt", {"prompt": "v2"}, 0.85, True),
        ],
    )
    assert results[0].status.value == "rejected"
    assert results[1].status.value == "accepted"
    lab.promote(results[1])
    assert lab.promoted is results[1]
