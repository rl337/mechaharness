from mechaharness.graph_state_governance import (
    FieldGovernance,
    GraphStateGovernance,
    authorize_write,
)


def test_frozen() -> None:
    gov = GraphStateGovernance(
        fields={
            "t": FieldGovernance(owner="ops", writers=["ops"], mutable=False),
        }
    )
    assert not authorize_write(gov, field="t", actor="ops")
