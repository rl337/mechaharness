from mechaharness.graph_state_governance import FieldGovernance, GraphStateGovernance, authorize_write

def test_frozen():
    g = GraphStateGovernance(fields={"t": FieldGovernance(owner="ops", writers=["ops"], mutable=False)})
    assert not authorize_write(g, field="t", actor="ops")
