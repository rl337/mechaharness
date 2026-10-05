"""Typed isolation and template/subgraph I/O contracts.

WalkingLabs L14 and the Codex harness design separate child isolation
(effects, context, budgets) from parent graph state and require typed I/O at
subgraph boundaries
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-14-graph-engineering/,
https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/codex/).

MechaHarness exposes reusable contracts hosts and templates can validate::

    >>> from mechaharness.isolation_contract import IsolationContract, TemplateIOContract
    >>> iso = IsolationContract(
    ...     effect_scope="workspace:branch",
    ...     input_context_refs=["goal", "diff"],
    ...     output_export_schema={"summary": "string"},
    ...     budget_share=0.25,
    ...     cancellable=True,
    ... )
    >>> iso.validation_issues()
    []
    >>> io = TemplateIOContract(
    ...     inputs={"goal": "string"},
    ...     outputs={"result": "object"},
    ...     write_scopes=["repo:src"],
    ...     required_capabilities=["core:fs.read"],
    ...     isolation=iso,
    ... )
    >>> io.describe()["outputs"]
    {'result': 'object'}
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IsolationContract(BaseModel):
    """Child execution isolation covering effects, context, and budgets."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    effect_scope: str = "none"
    input_context_refs: list[str] = Field(default_factory=list)
    output_export_schema: dict[str, Any] = Field(default_factory=dict)
    capability_envelope_ref: str | None = None
    budget_share: float = 1.0
    cancellable: bool = True
    supersedable: bool = False
    parent_visible_summary_keys: list[str] = Field(default_factory=list)

    def validation_issues(self) -> list[str]:
        issues: list[str] = []
        if not (0.0 < self.budget_share <= 1.0):
            issues.append("budget_share must be in (0, 1]")
        if self.effect_scope == "":
            issues.append("effect_scope must be non-empty")
        return issues


class TemplateIOContract(BaseModel):
    """Typed inputs/outputs and scopes for templates and nested subgraphs."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    state_scopes: list[str] = Field(default_factory=list)
    write_scopes: list[str] = Field(default_factory=list)
    outcome_contract_ref: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    budget_semantics: str = "share_parent"
    isolation: IsolationContract | None = None

    def validation_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.inputs and not self.outputs:
            issues.append("template I/O needs inputs or outputs")
        if self.isolation is not None:
            issues.extend(self.isolation.validation_issues())
        return issues

    def describe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
