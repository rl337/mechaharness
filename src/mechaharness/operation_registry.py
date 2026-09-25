"""Shared computation contracts and registry (INF-01 / INF-03)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.core.exceptions import MechaHarnessError


class UnsupportedOperation(MechaHarnessError):
    """Requested operation is not registered."""


class ContractMismatch(MechaHarnessError):
    """Node bind or I/O incompatible with the operation contract."""


EffectKind = Literal["none", "read", "write", "external", "unknown"]


class ResourceScope(BaseModel):
    """Declared read/write resource scope (INF-01)."""

    model_config = ConfigDict(extra="allow")

    name: str
    mode: Literal["read", "write", "read_write"] = "read"


class OperationContract(BaseModel):
    """Versioned operation contract reused by compiler, graph, and decision backends."""

    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "1"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = None
    cancellable: bool = True
    resource_budget: dict[str, Any] = Field(default_factory=dict)
    error_semantics: str = "fail_closed"
    provenance: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    read_scopes: list[ResourceScope] = Field(default_factory=list)
    write_scopes: list[ResourceScope] = Field(default_factory=list)
    external_effects: EffectKind = "none"
    isolation: str = "none"
    retry_policy: str = "none"
    idempotent: bool = False


class NodeContractBind(BaseModel):
    """Bind a node instance to a contract version and planning revision (INF-01)."""

    model_config = ConfigDict(extra="allow")

    operation: str
    contract_version: str
    input_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    state_revision: str
    planned_effects: EffectKind = "none"


class OperationRegistry:
    """Register contracts + handlers; reject unsupported ops (INF-01/03)."""

    def __init__(self) -> None:
        self._ops: dict[str, Callable[..., Any]] = {}
        self._contracts: dict[str, OperationContract] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        contract: OperationContract | None = None,
    ) -> None:
        self._ops[name] = handler
        if contract is not None:
            if contract.name != name:
                raise ContractMismatch(
                    f"contract name {contract.name!r} != registry key {name!r}"
                )
            self._contracts[name] = contract
        elif name not in self._contracts:
            self._contracts[name] = OperationContract(name=name)

    def register_contract(self, contract: OperationContract) -> None:
        self._contracts[contract.name] = contract

    def supports(self, name: str) -> bool:
        return name in self._ops

    def require(self, name: str) -> Callable[..., Any]:
        try:
            return self._ops[name]
        except KeyError as exc:
            raise UnsupportedOperation(
                f"unsupported operation {name!r}; known: {sorted(self._ops)}"
            ) from exc

    def contract(self, name: str) -> OperationContract:
        if name not in self._contracts:
            raise UnsupportedOperation(f"no contract for operation {name!r}")
        return self._contracts[name]

    def bind_node(self, bind: NodeContractBind) -> OperationContract:
        """Reject incompatible binds before scheduling."""
        contract = self.contract(bind.operation)
        if bind.contract_version != contract.version:
            raise ContractMismatch(
                f"contract version mismatch: node={bind.contract_version!r} "
                f"registry={contract.version!r}"
            )
        if bind.planned_effects == "unknown" and contract.external_effects == "none":
            # Unknown effects must be explicit on the contract too.
            raise ContractMismatch(
                "unknown effects cannot bind to a none-effect contract"
            )
        if (
            contract.external_effects == "unknown"
            and bind.planned_effects != "unknown"
        ):
            raise ContractMismatch(
                "contract declares unknown effects; node must plan unknown explicitly"
            )
        return contract

    def conflicts(
        self, a: OperationContract, b: OperationContract
    ) -> list[str]:
        """Detect read/write and write/write scope conflicts for concurrent scheduling."""
        issues: list[str] = []
        a_writes = {s.name for s in a.write_scopes}
        b_writes = {s.name for s in b.write_scopes}
        a_reads = {s.name for s in a.read_scopes} | a_writes
        b_reads = {s.name for s in b.read_scopes} | b_writes
        for name in a_writes & b_writes:
            issues.append(f"write_write:{name}")
        for name in a_writes & b_reads:
            if name not in a_writes & b_writes:
                issues.append(f"write_read:{name}")
        for name in b_writes & a_reads:
            if name not in a_writes & b_writes and f"write_read:{name}" not in issues:
                issues.append(f"write_read:{name}")
        if a.external_effects == "unknown" or b.external_effects == "unknown":
            issues.append("unknown_effect_scope")
        return issues

    def recheck_preconditions(
        self, name: str, *, satisfied: Sequence[str]
    ) -> list[str]:
        """Return unsatisfied preconditions (stale check before an effect)."""
        contract = self.contract(name)
        have = set(satisfied)
        return [p for p in contract.preconditions if p not in have]

    def names(self) -> list[str]:
        return sorted(self._ops)

    def merge(self, other: Mapping[str, Callable[..., Any]]) -> OperationRegistry:
        for name, handler in other.items():
            self.register(name, handler)
        return self


def default_operations() -> OperationRegistry:
    registry = OperationRegistry()
    registry.register(
        "chat",
        lambda **_: None,
        contract=OperationContract(
            name="chat",
            version="1",
            external_effects="none",
            idempotent=False,
        ),
    )
    registry.register(
        "judge",
        lambda **_: None,
        contract=OperationContract(
            name="judge",
            version="1",
            external_effects="none",
            idempotent=True,
        ),
    )
    registry.register(
        "tool",
        lambda **_: None,
        contract=OperationContract(
            name="tool",
            version="1",
            external_effects="unknown",
            isolation="sandbox",
            idempotent=False,
        ),
    )
    return registry
