"""Execution graph, dependencies, fan-in, and verifier qualification tests."""

from __future__ import annotations

from mechaharness.graph import (
    DependencyEdge,
    ExecutionGraph,
    FanInItem,
    GraphNode,
    GraphStore,
    NodeStatus,
    VerificationOracle,
    bounded_repair,
    hierarchical_fan_in,
    merge_branch_artifacts,
    qualify_validator,
    select_strongest_oracle,
    validator_qualified,
)


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
    store.save(graph, run_id="r1", boundary="commit")
    restored = store.latest(run_id="r1")
    assert restored is not None
    assert "fetch" in restored.nodes
    assert store.latest_boundary(run_id="r1") == "commit"

    def has_file(node: GraphNode) -> tuple[bool, dict]:
        ok = bool(node.payload.get("path"))
        return ok, {"file": node.payload.get("path")}

    node = GraphNode(id="x", payload={})
    repaired = bounded_repair(
        node,
        verifiers=[has_file],
        repair=lambda n: n.model_copy(update={"payload": {"path": "/tmp/out.png"}}),
    )
    assert repaired.status == NodeStatus.SUCCEEDED


def test_dependency_justification_and_conflicts() -> None:
    graph = ExecutionGraph(goal="parallel")
    graph.add_node(GraphNode(id="a", write_scopes=["x"]))
    graph.add_node(GraphNode(id="b", write_scopes=["x"]))
    graph.add_dependency(
        DependencyEdge(
            from_node="a",
            to_node="b",
            types=["resource"],
            reason="exclusive write on x",
            evidence_ref="inf:scope",
        )
    )
    assert graph.concurrent_write_conflicts(["a", "b"])


def test_fan_in_preserves_failures_and_budget() -> None:
    result = hierarchical_fan_in(
        [
            FanInItem(id="1", source_ref="s1", payload={"id": "dup"}),
            FanInItem(id="2", source_ref="s2", payload={"id": "dup"}),
            FanInItem(id="3", source_ref="s3", payload={"id": "ok"}, failed=True),
            FanInItem(id="4", source_ref="s4", payload={"id": "c"}, conflict=True),
        ],
        budget=2,
    )
    assert result.duplicates_collapsed == 1
    assert "3" in result.failures
    assert "4" in result.conflicts
    assert len(result.items) <= 2


def test_merge_conflicts_and_validator_qualification() -> None:
    merged = merge_branch_artifacts(
        base_revision="r0",
        branches=[
            {"path": "a.py", "content": "1", "status": "ok"},
            {"path": "a.py", "content": "2", "status": "ok"},
            {"path": "b.py", "content": "x", "status": "failed"},
        ],
    )
    assert "a.py" in merged["conflicts"]
    assert "b.py" not in merged["artifacts"]

    oracle = select_strongest_oracle(
        [
            VerificationOracle(name="schema", strength="schema"),
            VerificationOracle(name="test", strength="executable"),
        ]
    )
    assert oracle is not None and oracle.name == "test"

    def good_bad(item: str) -> str:
        if item == "missing":
            return "unknown"
        return "pass" if item.startswith("ok") else "fail"

    results = qualify_validator(
        name="len_check",
        verifier=good_bad,
        good_fixtures=["ok1"],
        bad_fixtures=["bad1"],
        missing_fixtures=["missing"],
    )
    assert validator_qualified(results)

    always = qualify_validator(
        name="noop",
        verifier=lambda _x: "pass",
        good_fixtures=["ok"],
        bad_fixtures=["bad"],
    )
    assert not validator_qualified(always)
