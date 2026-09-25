"""OperationRegistry and OperationContract tests (INF-01)."""

from __future__ import annotations

import pytest

from mechaharness.operation_registry import (
    ContractMismatch,
    NodeContractBind,
    OperationContract,
    ResourceScope,
    UnsupportedOperation,
    default_operations,
)


def test_operation_registry_rejects_unknown() -> None:
    ops = default_operations()
    assert ops.supports("judge")
    with pytest.raises(UnsupportedOperation):
        ops.require("predictive_world_model")


def test_contract_bind_and_conflicts() -> None:
    ops = default_operations()
    write = OperationContract(
        name="edit_a",
        version="1",
        write_scopes=[ResourceScope(name="file.txt", mode="write")],
        preconditions=["unlocked"],
        external_effects="write",
    )
    ops.register("edit_a", lambda **_: None, contract=write)
    ops.register(
        "edit_b",
        lambda **_: None,
        contract=OperationContract(
            name="edit_b",
            version="1",
            write_scopes=[ResourceScope(name="file.txt", mode="write")],
            external_effects="write",
        ),
    )
    bind = NodeContractBind(
        operation="edit_a",
        contract_version="1",
        state_revision="r1",
        planned_effects="write",
    )
    assert ops.bind_node(bind).name == "edit_a"
    with pytest.raises(ContractMismatch):
        ops.bind_node(bind.model_copy(update={"contract_version": "9"}))
    assert ops.conflicts(ops.contract("edit_a"), ops.contract("edit_b"))
    assert ops.recheck_preconditions("edit_a", satisfied=[]) == ["unlocked"]
    assert ops.recheck_preconditions("edit_a", satisfied=["unlocked"]) == []
