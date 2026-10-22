"""Instruction todo-plan Agentic Recipe — oneshot vs list with acceptance gates.

Catalog id: ``instruction_todo_plan``. Classifies the current instruction as a
oneshot or an ordered list, refines the list for conflicts, freezes pre-list
acceptance, executes each todo with per-item verify, then checks post-list
acceptance so later steps have not undone earlier ones. Human calling
refinement is a ``guidance`` soft point requested dynamically (generator
``request_guidance`` → ``advice_requested`` → restart with answers).
"""

from __future__ import annotations

from mechaharness.graph import DependencyEdge, ExecutionGraph
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.isolation.isolation_contract import TemplateIOContract
from mechaharness.stop_contract import StopContract


class InstructionTodoPlanTemplate(GraphTemplate):
    """classify → refine → pre_accept → work_item* → item_accept → post_accept.

    Example::

        >>> from mechaharness.graph_templates import (
        ...     InstructionTodoPlanTemplate, GraphTemplateParams,
        ... )
        >>> graph = InstructionTodoPlanTemplate().instantiate(
        ...     GraphTemplateParams(
        ...         goal="ship helpers",
        ...         inputs={"instruction_mode": "list", "max_items": 4},
        ...     )
        ... )
        >>> graph.template_name
        'instruction_todo_plan'
        >>> "classify" in graph.nodes and "work_item" in graph.nodes
        True
        >>> graph.nodes["work_item"].repeating
        True
    """

    name = "instruction_todo_plan"
    version = "1"
    category = "agentic_recipe"
    summary = (
        "Classify oneshot vs todo list; refine conflicts; pre/item/post "
        "acceptance; yield human refinement then restart."
    )
    description = (
        "Judge whether the current instruction is a oneshot or a list. Lists "
        "are refined for conflicts, then each todo runs under per-item "
        "acceptance with a post-list check. Soft points scope_refinement and "
        "list_refinement (kind=guidance, not required) are requested by local "
        "work when human calling refinement is needed; answering restarts the "
        "plan with guidance_history."
    )
    soft_points = (
        SoftPoint(
            name="scope_refinement",
            kind="guidance",
            required=False,
            description=(
                "Human calling refinement when oneshot vs list (or scope) is "
                "ambiguous — yielded only when local work requests it."
            ),
            default={
                "choices": [
                    {"id": "oneshot", "label": "One shot"},
                    {"id": "list", "label": "Ordered todo list"},
                ],
                "recommendation": "oneshot",
                "requested_authority": "engineering_direction",
            },
        ),
        SoftPoint(
            name="list_refinement",
            kind="guidance",
            required=False,
            description=(
                "Human calling refinement when the todo list has conflicts "
                "that would fail post-list acceptance."
            ),
            default={
                "choices": [
                    {"id": "revise", "label": "Revise the list"},
                    {"id": "accept_risk", "label": "Proceed anyway"},
                ],
                "recommendation": "revise",
                "requested_authority": "engineering_direction",
            },
        ),
        SoftPoint(
            name="max_items",
            kind="budget",
            description="Max todo / oneshot work_item iterations",
            default=8,
        ),
        SoftPoint(
            name="stop_contract",
            kind="budget",
            description="StopContract bounding the work_item loop",
            required=False,
        ),
        SoftPoint(
            name="pre_acceptance",
            kind="policy",
            description="Acceptance criteria frozen before list / oneshot work",
            required=False,
        ),
        SoftPoint(
            name="item_acceptance",
            kind="policy",
            description="Default per-item acceptance after each todo",
            required=False,
        ),
        SoftPoint(
            name="post_acceptance",
            kind="policy",
            description="Post-list acceptance (holistic; catches undo regressions)",
            required=False,
        ),
        SoftPoint(
            name="classify_kind",
            kind="runner_kind",
            default="instruction.classify",
            description="Node kind that judges oneshot vs list",
        ),
        SoftPoint(
            name="refine_kind",
            kind="runner_kind",
            default="instruction.refine_plan",
            description="Node kind that refines list and checks conflicts",
        ),
        SoftPoint(
            name="pre_accept_kind",
            kind="runner_kind",
            default="instruction.pre_accept",
            description="Freeze / check pre-list acceptance",
        ),
        SoftPoint(
            name="work_kind",
            kind="runner_kind",
            default="instruction.work_item",
            description="Execute one oneshot or todo item",
        ),
        SoftPoint(
            name="item_accept_kind",
            kind="runner_kind",
            default="instruction.item_accept",
            description="Verify per-item acceptance",
        ),
        SoftPoint(
            name="post_accept_kind",
            kind="runner_kind",
            default="instruction.post_accept",
            description="Verify post-list acceptance",
        ),
        SoftPoint(
            name="complete_kind",
            kind="runner_kind",
            default="instruction.complete",
            description="Terminal node after post-accept",
        ),
    )
    io_contract = TemplateIOContract(
        inputs={
            "goal": "string",
            "instructions": "array|string",
            "instruction_mode": "string",
            "pre_acceptance": "array",
            "item_acceptance": "array",
            "post_acceptance": "array",
        },
        outputs={"plan": "object", "results": "array"},
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        bindings = params.soft_bindings
        inputs = dict(params.inputs or {})
        max_items = int(bindings.get("max_items", inputs.get("max_items", 8)))
        stop = params.stop_contract or StopContract(
            version="1", max_iterations=max_items
        )
        goal = params.goal or inputs.get("goal") or inputs.get("task") or self.name

        pre_ac = (
            bindings.get("pre_acceptance")
            or inputs.get("pre_acceptance")
            or params.acceptance
            or []
        )
        item_ac = (
            bindings.get("item_acceptance")
            or inputs.get("item_acceptance")
            or params.acceptance
            or ["item_done"]
        )
        post_ac = (
            bindings.get("post_acceptance")
            or inputs.get("post_acceptance")
            or pre_ac
            or item_ac
        )
        if isinstance(pre_ac, str):
            pre_ac = [pre_ac]
        if isinstance(item_ac, str):
            item_ac = [item_ac]
        if isinstance(post_ac, str):
            post_ac = [post_ac]

        graph = ExecutionGraph(
            goal=str(goal),
            version=self.version,
            template_name=self.name,
            template_version=self.version,
        )

        classify = make_node(
            id="classify",
            kind=str(bindings.get("classify_kind", "instruction.classify")),
            goal="Judge oneshot vs ordered todo list",
            payload={
                "phase": "classify",
                "soft_points": ["scope_refinement"],
            },
        )
        refine = make_node(
            id="refine_plan",
            kind=str(bindings.get("refine_kind", "instruction.refine_plan")),
            goal="Refine list; detect conflicts vs post-list acceptance",
            depends_on=["classify"],
            payload={
                "phase": "refine_plan",
                "soft_points": ["list_refinement"],
            },
        )
        pre_accept = make_node(
            id="pre_accept",
            kind=str(bindings.get("pre_accept_kind", "instruction.pre_accept")),
            goal="Freeze / verify pre-list acceptance criteria",
            depends_on=["refine_plan"],
            acceptance=list(pre_ac),
            payload={
                "phase": "pre_accept",
                "soft_points": ["pre_acceptance"],
                "acceptance": list(pre_ac),
            },
        )
        work_item = make_node(
            id="work_item",
            kind=str(bindings.get("work_kind", "instruction.work_item")),
            goal="Execute one oneshot or todo item",
            depends_on=["pre_accept"],
            repeating=True,
            stop_contract=stop,
            payload={
                "phase": "work_item",
                "soft_points": ["max_items", "stop_contract"],
                "max_items": max_items,
            },
        )
        item_accept = make_node(
            id="item_accept",
            kind=str(bindings.get("item_accept_kind", "instruction.item_accept")),
            goal="Verify per-item acceptance after each todo",
            depends_on=["work_item"],
            acceptance=list(item_ac),
            payload={
                "phase": "item_accept",
                "soft_points": ["item_acceptance"],
                "acceptance": list(item_ac),
            },
        )
        post_accept = make_node(
            id="post_accept",
            kind=str(bindings.get("post_accept_kind", "instruction.post_accept")),
            goal="Verify post-list acceptance (no undo regressions)",
            depends_on=["item_accept"],
            acceptance=list(post_ac),
            payload={
                "phase": "post_accept",
                "soft_points": ["post_acceptance"],
                "acceptance": list(post_ac),
            },
        )
        complete = make_node(
            id="complete",
            kind=str(bindings.get("complete_kind", "instruction.complete")),
            goal="Plan complete",
            depends_on=["post_accept"],
            payload={"phase": "complete", "terminal": True},
        )

        for node in (
            classify,
            refine,
            pre_accept,
            work_item,
            item_accept,
            post_accept,
            complete,
        ):
            graph.add_node(node)

        edges = [
            ("classify", "refine_plan", "after_classify"),
            ("refine_plan", "pre_accept", "after_refine"),
            ("pre_accept", "work_item", "start_work"),
            ("work_item", "item_accept", "item_done"),
            ("item_accept", "post_accept", "items_verified"),
            ("post_accept", "complete", "holistic_ok"),
        ]
        for frm, to, reason in edges:
            graph.add_dependency(
                DependencyEdge(
                    from_node=frm,
                    to_node=to,
                    types=["control"],
                    reason=reason,
                )
            )
        return graph
