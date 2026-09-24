"""OperationRegistry tests."""

from __future__ import annotations

from mechaharness.operation_registry import UnsupportedOperation, default_operations


def test_operation_registry_rejects_unknown() -> None:
    ops = default_operations()
    assert ops.supports("judge")
    try:
        ops.require("predictive_world_model")
        raise AssertionError("expected UnsupportedOperation")
    except UnsupportedOperation:
        pass
