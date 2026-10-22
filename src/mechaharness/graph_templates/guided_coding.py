"""Guided coding Agentic Recipe — Cursor guides; local tools code; audited gate.

Catalog id: ``guided_coding``. Soft point ``external_guidance`` yields to a
frontier MCP driver. The graph tiles ``instruction_todo_plan`` (oneshot vs
todo list + acceptance) and ``audited_infer_accept`` (quality gate). Drive via
``DurableGraphGenerator`` / MCP with ``ProjectCodingConfig`` so local
``openai_local`` inference and workspace tools perform the token-heavy work.
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode
from mechaharness.graph_templates.audited_infer_accept import AuditedInferAcceptTemplate
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
)
from mechaharness.graph_templates.instruction_todo_plan import InstructionTodoPlanTemplate
from mechaharness.isolation.isolation_contract import TemplateIOContract
from mechaharness.stop_contract import StopContract


class GuidedCodingTemplate(GraphTemplate):
    """Frontier guidance → instruction todo plan → audited infer-accept gate.

    Example::

        >>> from mechaharness.graph_templates import (
        ...     GuidedCodingTemplate, GraphTemplateParams,
        ... )
        >>> graph = GuidedCodingTemplate().instantiate(
        ...     GraphTemplateParams(goal="add helper")
        ... )
        >>> graph.template_name
        'guided_coding'
        >>> "plan_tile" in graph.nodes and "audit_tile" in graph.nodes
        True
    """

    name = "guided_coding"
    version = "3"
    category = "agentic_recipe"
    summary = (
        "Cursor (or other frontier driver) answers engineering guidance; "
        "local openai_local classifies oneshot vs todo list, codes under "
        "workspace tools, then audited_infer_accept gates."
    )
    description = (
        "Yields external_guidance for approach/constraints, then tiles "
        "instruction_todo_plan (plan_tile) and audited_infer_accept "
        "(audit_tile) so local inference executes oneshot or ordered todos "
        "with pre/item/post acceptance and optional human refinement yields."
    )
    soft_points = (
        SoftPoint(
            name="external_guidance",
            kind="guidance",
            description=(
                "How should the local coding agent approach this change "
                "(scope, files, constraints, acceptance)?"
            ),
            required=True,
            default={
                "choices": [
                    {"id": "minimal", "label": "Minimal diff; match nearby style"},
                    {
                        "id": "thorough",
                        "label": "Thorough: tests + docs in the same change",
                    },
                ],
                "recommendation": "minimal",
                "requested_authority": "engineering_direction",
            },
        ),
        SoftPoint(
            name="max_iterations",
            kind="budget",
            description="Max tool-loop rounds per todo item when stop_contract omitted",
            default=8,
        ),
        SoftPoint(
            name="max_items",
            kind="budget",
            description="Max todo items in the instruction plan",
            default=8,
        ),
        SoftPoint(
            name="stop_contract",
            kind="budget",
            description="StopContract for the plan work_item loop",
            required=False,
        ),
        SoftPoint(
            name="acceptance",
            kind="policy",
            description="Acceptance criteria forwarded to plan + audited_infer_accept",
            required=False,
        ),
        SoftPoint(
            name="decide_principal",
            kind="policy",
            default="coding_decide",
            description="Decide principal for audit tile (must differ from QA)",
        ),
        SoftPoint(
            name="qa_principal",
            kind="policy",
            default="coding_qa",
            description="Independent QA principal for audit tile",
        ),
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "task": "string",
            "messages": "array",
            "instructions": "array|string",
            "instruction_mode": "string",
        },
        outputs={"result": "object", "final_text": "string", "plan": "object"},
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        max_iterations = int(
            bindings.get("max_iterations", inputs.get("max_iterations", 8))
        )
        max_items = int(bindings.get("max_items", inputs.get("max_items", 8)))
        stop = params.stop_contract or StopContract(
            version="1", max_iterations=max_items
        )
        goal = params.goal or inputs.get("goal") or inputs.get("task") or self.name

        graph = ExecutionGraph(
            goal=str(goal),
            version=self.version,
            template_name=self.name,
            template_version=self.version,
        )
        graph.add_node(
            GraphNode(
                id="brief",
                kind="prepare",
                goal="Capture task brief and pending guidance soft point",
                payload={
                    "goal": goal,
                    "soft_points": ["external_guidance"],
                    "task": inputs.get("task") or goal,
                },
            )
        )

        acceptance = params.acceptance or bindings.get("acceptance")
        if isinstance(acceptance, str):
            acceptance_list = [acceptance]
        elif isinstance(acceptance, list):
            acceptance_list = list(acceptance)
        else:
            acceptance_list = ["tests_ok", "lint_ok", "matches_guidance"]

        plan_child, plan_embed = InstructionTodoPlanTemplate().tile(
            GraphTemplateParams(
                goal=f"{goal}:plan",
                instance_key="plan",
                inputs={
                    **inputs,
                    "max_items": max_items,
                    "max_iterations": max_iterations,
                    "pre_acceptance": inputs.get("pre_acceptance") or acceptance_list,
                    "item_acceptance": inputs.get("item_acceptance")
                    or acceptance_list,
                    "post_acceptance": inputs.get("post_acceptance")
                    or acceptance_list,
                },
                soft_bindings={
                    "max_items": max_items,
                    "pre_acceptance": inputs.get("pre_acceptance") or acceptance_list,
                    "item_acceptance": inputs.get("item_acceptance")
                    or acceptance_list,
                    "post_acceptance": inputs.get("post_acceptance")
                    or acceptance_list,
                },
                acceptance=acceptance_list,
                stop_contract=stop,
            ),
            parent_node_id="plan_tile",
        )
        del plan_child
        plan_embed.depends_on = ["brief"]
        plan_embed.payload = {
            **dict(plan_embed.payload or {}),
            "soft_points": ["external_guidance"],
            "phase": "plan",
            "max_iterations": max_iterations,
        }
        graph.add_node(plan_embed)

        decide_principal = str(
            bindings.get("decide_principal")
            or inputs.get("decide_principal")
            or "coding_decide"
        )
        qa_principal = str(
            bindings.get("qa_principal") or inputs.get("qa_principal") or "coding_qa"
        )

        audit_child, audit_embed = AuditedInferAcceptTemplate().tile(
            GraphTemplateParams(
                goal=f"{goal}:audit",
                instance_key="audit",
                inputs={
                    **dict(inputs),
                    "task_id": str(inputs.get("task_id") or "guided-coding"),
                    "modality": "text",
                    "simple_ids": False,
                    "acceptance_criteria": acceptance_list,
                    "decide_principal": decide_principal,
                    "qa_principal": qa_principal,
                    "deterministic_kind": bindings.get(
                        "deterministic_kind", "audited.deterministic"
                    ),
                },
                soft_bindings={
                    "task_id": str(inputs.get("task_id") or "guided-coding"),
                    "modality": "text",
                    "acceptance_criteria": acceptance_list,
                    "decide_principal": decide_principal,
                    "qa_principal": qa_principal,
                    "deterministic_kind": bindings.get(
                        "deterministic_kind", "audited.deterministic"
                    ),
                },
            ),
            parent_node_id="audit_tile",
        )
        del audit_child
        audit_embed.depends_on = ["plan_tile"]
        audit_embed.payload = {
            **dict(audit_embed.payload or {}),
            "phase": "audit",
            "acceptance": acceptance_list,
        }
        graph.add_node(audit_embed)

        graph.add_dependency(
            DependencyEdge(
                from_node="brief",
                to_node="plan_tile",
                types=["control"],
                reason="after_guidance",
            )
        )
        graph.add_dependency(
            DependencyEdge(
                from_node="plan_tile",
                to_node="audit_tile",
                types=["control"],
                reason="audit_after_plan",
            )
        )
        return graph
