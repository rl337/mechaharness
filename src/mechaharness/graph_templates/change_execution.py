"""ChangeExecution Agentic Recipe (gastronomic M6 increment 3).

Applies one approved ChangePlan slice with scoped file revisions and explicit
write grants, then publishes a typed ChangeExecution (diff + hashes).

Completer may propose revisions via soft point ``propose_payload``; host
``in.file_revisions`` remain authoritative when non-empty.
"""

from __future__ import annotations

from typing import Any

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.isolation.isolation_contract import TemplateIOContract


class ChangeExecutionTemplate(GraphTemplate):
    """Constrain → propose → materialize → apply → publish → validate.

    Catalog id: ``change_execution``.

    Example:
        >>> from mechaharness.graph_templates import (
        ...     GraphTemplateParams, ChangeExecutionTemplate,
        ... )
        >>> graph = ChangeExecutionTemplate().instantiate(GraphTemplateParams(
        ...     goal="Apply multiply helper",
        ...     inputs={
        ...         "goal": "Apply multiply helper",
        ...         "approved_slice": {
        ...             "id": "arithmetic",
        ...             "scope": {"paths": ["src/calc/arithmetic.py"]},
        ...         },
        ...         "workspace": {"root": "."},
        ...     },
        ... ))
        >>> graph.template_name
        'change_execution'
        >>> "propose" in graph.nodes and "materialize" in graph.nodes
        True
    """

    name = "change_execution"
    version = "1"
    summary = (
        "Propose or host-seed scoped file revisions, apply with write grants, "
        "and publish diff plus changed-file hashes."
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "approved_slice": "object",
            "change_plan": "object",
            "file_revisions": "object",
            "workspace": "object",
        },
        outputs={"change_execution": "object"},
    )
    soft_points = (
        SoftPoint(
            name="propose_payload",
            kind="task_state",
            description=(
                "Completer ContextSpec for proposing scoped file revisions "
                "(JSON list or {revisions:[...]})"
            ),
            required=False,
        ),
        SoftPoint(
            name="apply_payload",
            kind="task_state",
            description=(
                "Optional parameters for execution_apply (e.g. inline revisions)"
            ),
            required=False,
        ),
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        goal = params.goal or str(inputs.get("goal") or "execute change slice")
        graph = ExecutionGraph(goal=goal, version=self.version)

        seed_put: dict[str, Any] = {}
        if "goal" in inputs or params.goal:
            seed_put["in.goal"] = inputs.get("goal", params.goal)
        for key in (
            "approved_slice",
            "change_plan",
            "file_revisions",
            "workspace",
        ):
            if key in inputs:
                seed_put[f"in.{key}"] = inputs[key]
        graph.add_node(
            make_node(
                id="seed",
                kind="compute",
                payload={"bag_put": seed_put} if seed_put else {},
            )
        )
        graph.add_node(
            make_node(
                id="constrain",
                kind="execution_constrain",
                depends_on=["seed"],
                payload={
                    "reads": {
                        "approved_slice": "in.approved_slice",
                        "change_plan": "in.change_plan",
                    },
                    "writes": {"destination": "acc.execution.constraints"},
                },
            )
        )
        propose_payload = dict(bindings.get("propose_payload") or {})
        propose_payload.setdefault("soft_point", "propose_payload")
        propose_payload.setdefault(
            "context",
            {
                "version": "1",
                "system": (
                    "Do not think aloud. Put JSON only in answer content (not "
                    "only in reasoning). Return exactly "
                    '{"revisions":[{"path":"...","content":"...full file..."}]} '
                    "with no markdown fences. Stay inside approved slice "
                    "allowed_paths. Do not use eval/exec. Prefer extending "
                    "existing files; keep evaluate and main(argv=None)."
                ),
                # Qwen-style thinking Completers honor /no_think in the user
                # turn so JSON lands in content instead of burning the budget.
                "user_preamble": (
                    "/no_think\nUse only the following bag evidence."
                ),
                "reads": [
                    {"path": "in.goal", "required": True},
                    {"path": "acc.execution.constraints", "required": True},
                    {"path": "in.approved_slice", "required": False},
                    {"path": "in.change_plan", "required": False},
                    {"path": "in.workspace", "required": False},
                    {"path": "in.file_revisions", "required": False},
                ],
                "response": {
                    "writes": "acc.execution.proposed",
                    "parse": "json",
                },
            },
        )
        graph.add_node(
            make_node(
                id="propose",
                kind="infer",
                depends_on=["constrain"],
                payload=propose_payload,
            )
        )
        graph.add_node(
            make_node(
                id="materialize",
                kind="execution_materialize",
                depends_on=["propose"],
                payload={
                    "reads": {
                        "host_revisions": "in.file_revisions",
                        "proposed": "acc.execution.proposed",
                    },
                    "writes": {"destination": "acc.execution.revisions"},
                    "parameters": {"fail_if_incomplete": True},
                },
            )
        )
        apply_payload = dict(bindings.get("apply_payload") or {})
        apply_reads = {
            "constraints": "acc.execution.constraints",
            "revisions": "acc.execution.revisions",
            "workspace": "in.workspace",
        }
        apply_parameters = dict(apply_payload.get("parameters") or {})
        graph.add_node(
            make_node(
                id="apply",
                kind="execution_apply",
                depends_on=["materialize"],
                payload={
                    "soft_point": "apply_payload",
                    "reads": apply_reads,
                    "writes": {"destination": "acc.execution.apply_receipt"},
                    "parameters": apply_parameters,
                },
            )
        )
        graph.add_node(
            make_node(
                id="publish",
                kind="execution_publish",
                depends_on=["apply"],
                payload={
                    "reads": {
                        "constraints": "acc.execution.constraints",
                        "receipt": "acc.execution.apply_receipt",
                    },
                    "writes": {"destination": "out.change_execution"},
                },
            )
        )
        graph.add_node(
            make_node(
                id="validate",
                kind="execution_validate",
                depends_on=["publish"],
                payload={
                    "reads": {"source": "out.change_execution"},
                    "writes": {"destination": "acc.execution.validation"},
                    "parameters": {"fail_if_invalid": True},
                },
            )
        )
        order = [
            "seed",
            "constrain",
            "propose",
            "materialize",
            "apply",
            "publish",
            "validate",
        ]
        for left, right in zip(order, order[1:]):
            graph.add_dependency(
                DependencyEdge(
                    from_node=left,
                    to_node=right,
                    types=["control"],
                    reason="change_execution",
                )
            )
        return graph


__all__ = ["ChangeExecutionTemplate"]
