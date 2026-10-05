from mechaharness.context_layers import GraphSharedState, project_node_context


def test_private_projection_and_export() -> None:
    shared = GraphSharedState(data={"goal": "x", "secret": "no"})
    private = project_node_context(shared, needs=["goal"], node_id="n1")
    assert private.data == {"goal": "x"}
    private.export_to_shared(shared, {"result": 1})
    assert shared.data["result"] == 1
    assert "secret" not in private.data
