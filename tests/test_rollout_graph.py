from mechaharness.rollout_graph import build_rollout_graph, rollout_from_events


def test_retry_and_delegated_roots() -> None:
    g = build_rollout_graph(
        [
            {"id": "root", "kind": "model_call", "parent_id": None},
            {
                "id": "retry",
                "kind": "retry",
                "parent_id": "root",
                "execution_node_id": "produce",
                "attempt": 2,
            },
            {"id": "review", "kind": "delegated_agent", "parent_id": None},
        ]
    )
    assert g.roots() == ["review", "root"]
    assert g.nodes["retry"].execution_node_id == "produce"


def test_rollout_from_events() -> None:
    g = rollout_from_events(
        [
            {"type": "core:inference", "payload": {"node_id": "m1"}},
            {
                "type": "core:tool_call",
                "payload": {"node_id": "t1", "parent_id": "m1"},
            },
        ],
        run_id="r1",
    )
    assert g.nodes["m1"].kind == "model_call"
    assert g.nodes["t1"].parent_id == "m1"
