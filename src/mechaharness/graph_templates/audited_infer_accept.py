"""Audited infer-accept Agentic Recipe (RDG-aligned generate → QA → gate).

Catalog id: ``audited_infer_accept``. Expands::

    [precheck?] → collect → freeze_criteria → decide → independent_qa
      → deterministic → gate

Modality (``text`` | ``image``) only swaps decide/QA kinds. Hosts bind runners
(FOLK: ``folk.infer.*``). Library defaults use ``audited.*`` placeholder kinds.

Provenance: FOLK ``ideation.infer.accept`` / ``append_infer_accept`` lifted for
library reuse so hosts can migrate catalog ids while keeping produce/QA tools.
"""

from __future__ import annotations

from typing import Any

from mechaharness.audited_decision import (
    STAGES,
    assert_principals_distinct,
    default_stage_kinds,
)
from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode
from mechaharness.graph_templates.base import (
    GraphTemplate,
    GraphTemplateParams,
    SoftPoint,
    make_node,
)
from mechaharness.isolation.isolation_contract import TemplateIOContract


def audited_node_prefix(task_id: str) -> str:
    """Stable node-id prefix for resumes / prior pins."""
    safe = task_id.replace("-", "_").replace(".", "_").replace("/", "_")
    return f"aa_{safe}"


def prior_accepted(stage_id: str) -> dict[str, str]:
    """Prior-stage pin for require_prior."""
    return {"stage_id": stage_id, "verdict": "accepted"}


def _criteria_from_intent(intent_fields: dict[str, Any] | None) -> list[str]:
    if not intent_fields:
        return []
    brief = (
        intent_fields.get("fountain_brief")
        or intent_fields.get("image_prompt")
        or intent_fields.get("brief")
        or intent_fields.get("prompt")
        or intent_fields.get("goal")
        or intent_fields.get("task")
    )
    if not brief:
        return []
    return [
        f"Satisfy brief: {str(brief).strip()[:240]}",
        "Deliver a non-empty on-brief artifact",
    ]


def append_audited_infer_accept(
    nodes: list[GraphNode],
    *,
    after: str | None,
    task_id: str | None = None,
    modality: str = "text",
    base: dict[str, Any] | None = None,
    stage_id: str | None = None,
    produce_kind: str = "noop",
    require_prior: list[dict[str, Any]] | None = None,
    intent_fields: dict[str, Any] | None = None,
    artifact_src_rel: str | None = None,
    simple_ids: bool = False,
    kind_overrides: dict[str, str] | None = None,
) -> str:
    """Append audited spine onto *nodes*; return gate node id.

    Soft subgraph::

      modality=text  → audited.text.decide / audited.text.qa  (or host overrides)
      modality=image → audited.image.decide / audited.image.qa

    ``stage_id`` aliases ``task_id`` for hosts migrating from FOLK stage.verify.
    """
    modality_norm = str(modality or "text").strip().lower()
    if modality_norm not in ("text", "image"):
        raise ValueError(f"modality must be text|image, got {modality!r}")

    tid = str(task_id or stage_id or "infer-task")
    payload: dict[str, Any] = dict(base or {})
    payload["task_id"] = tid
    payload["stage_id"] = tid
    payload["modality"] = modality_norm
    payload["produce_kind"] = produce_kind or payload.get("produce_kind") or "noop"
    payload["hop"] = str(payload.get("hop") or tid)
    if require_prior is not None:
        payload["require_prior"] = list(require_prior)
    if artifact_src_rel:
        payload["artifact_src_rel"] = artifact_src_rel
    if intent_fields:
        payload.update(intent_fields)

    criteria = list(payload.get("acceptance_criteria") or [])
    if not criteria:
        criteria = _criteria_from_intent(intent_fields) or _criteria_from_intent(payload)
    if not criteria:
        criteria = [
            f"Complete audited hop {tid}",
            "Artifact satisfies acceptance for this stage",
        ]
    payload["acceptance_criteria"] = criteria

    if "require_evidence_anchors" not in payload:
        seed = payload.get("seed_evidence") or []
        payload["require_evidence_anchors"] = bool(seed)

    payload.setdefault("decide_principal", "decide_agent")
    payload.setdefault("qa_principal", "qa_agent")
    assert_principals_distinct(
        str(payload["decide_principal"]),
        str(payload["qa_principal"]),
        hop=str(payload["hop"]),
    )

    if simple_ids:
        stage_ids = {
            "precheck": "precheck",
            "collect": "collect",
            "freeze_criteria": "freeze",
            "decide": "decide",
            "independent_qa": "qa",
            "deterministic": "deterministic",
            "gate": "gate",
        }
    else:
        prefix = audited_node_prefix(tid)
        stage_ids = {
            "precheck": f"{prefix}_precheck",
            "collect": f"{prefix}_collect",
            "freeze_criteria": f"{prefix}_freeze",
            "decide": f"{prefix}_decide",
            "independent_qa": f"{prefix}_qa",
            "deterministic": f"{prefix}_det",
            "gate": f"{prefix}_gate",
        }

    ov = dict(kind_overrides or {})
    kinds = default_stage_kinds(
        modality_norm,  # type: ignore[arg-type]
        decide_kind=ov.get("decide") or payload.get("decide_kind"),
        qa_kind=ov.get("independent_qa") or payload.get("qa_kind"),
        collect_kind=ov.get("collect") or payload.get("collect_kind"),
        freeze_kind=ov.get("freeze_criteria") or payload.get("freeze_kind"),
        deterministic_kind=ov.get("deterministic")
        or payload.get("deterministic_kind"),
        gate_kind=ov.get("gate") or payload.get("gate_kind"),
        precheck_kind=ov.get("precheck") or payload.get("precheck_kind"),
    )
    goals = {
        "precheck": "Prior stages accepted",
        "collect": "Collect evidence",
        "freeze_criteria": "Freeze + hash acceptance criteria",
        "decide": f"Decide ({modality_norm})",
        "independent_qa": f"Independent QA ({modality_norm})",
        "deterministic": "Deterministic checks",
        "gate": "Gate — QA pass ≠ publish",
    }

    prev: str | None = after
    if require_prior:
        nid = stage_ids["precheck"]
        nodes.append(
            make_node(
                id=nid,
                kind=kinds["precheck"],
                goal=goals["precheck"],
                depends_on=[prev] if prev else [],
                payload=dict(payload),
            )
        )
        prev = nid

    for stage in STAGES:
        nid = stage_ids[stage]
        nodes.append(
            make_node(
                id=nid,
                kind=kinds[stage],
                goal=goals[stage],
                depends_on=[prev] if prev else [],
                payload=dict(payload),
            )
        )
        prev = nid
    return stage_ids["gate"]


class AuditedInferAcceptTemplate(GraphTemplate):
    """Audited decision spine with soft modality for decide/QA kinds.

    Example::

        >>> from mechaharness.graph_templates import (
        ...     AuditedInferAcceptTemplate, GraphTemplateParams,
        ... )
        >>> graph = AuditedInferAcceptTemplate().instantiate(
        ...     GraphTemplateParams(
        ...         goal="accept hop",
        ...         soft_bindings={"task_id": "demo", "simple_ids": True},
        ...         inputs={"simple_ids": True, "task_id": "demo"},
        ...     )
        ... )
        >>> graph.template_name
        'audited_infer_accept'
        >>> "collect" in graph.nodes or any("collect" in n for n in graph.nodes)
        True
    """

    name = "audited_infer_accept"
    version = "1"
    category = "agentic_recipe"
    summary = (
        "Audited decision: collect → freeze criteria → decide → independent QA → "
        "deterministic → gate. Soft modality selects text or image decide/QA kinds."
    )
    description = (
        "RDG-aligned generate/verify spine. Hosts bind runners for each stage; "
        "modality only swaps decide/QA. FOLK migrates from ideation.infer.accept."
    )
    soft_points = (
        SoftPoint(
            name="task_id",
            kind="task_state",
            required=True,
            default="infer-task",
        ),
        SoftPoint(name="run_id", kind="task_state", required=False, default="infer-run"),
        SoftPoint(
            name="modality",
            kind="policy",
            default="text",
            description="text | image — selects decide/QA soft subgraph kinds",
        ),
        SoftPoint(name="hop", kind="task_state", description="Named hop for audit"),
        SoftPoint(
            name="acceptance_criteria",
            kind="policy",
            description="List of criteria strings frozen before decide",
            default=[],
        ),
        SoftPoint(
            name="decide_principal",
            kind="policy",
            default="decide_agent",
        ),
        SoftPoint(
            name="qa_principal",
            kind="policy",
            default="qa_agent",
            description="Must differ from decide_principal (RDG-05)",
        ),
        SoftPoint(name="max_retries", kind="budget", default=3),
        SoftPoint(
            name="produce_kind",
            kind="runner_kind",
            default="noop",
            description="Image/custom produce under decide (image modality)",
        ),
        SoftPoint(
            name="decide_kind",
            kind="runner_kind",
            description="Override decide node kind (default audited.{modality}.decide)",
            required=False,
        ),
        SoftPoint(
            name="qa_kind",
            kind="runner_kind",
            description="Override independent_qa node kind",
            required=False,
        ),
        SoftPoint(
            name="collect_kind",
            kind="runner_kind",
            required=False,
        ),
        SoftPoint(
            name="freeze_kind",
            kind="runner_kind",
            required=False,
        ),
        SoftPoint(
            name="deterministic_kind",
            kind="runner_kind",
            required=False,
        ),
        SoftPoint(
            name="gate_kind",
            kind="runner_kind",
            required=False,
        ),
        SoftPoint(
            name="hop_recipe",
            kind="policy",
            description="Host leaf recipe id (e.g. FOLK hop_accept)",
            required=False,
        ),
        SoftPoint(
            name="seed_evidence",
            kind="task_state",
            description="Evidence items with anchor/passage",
            default=[],
        ),
        SoftPoint(name="require_evidence_anchors", kind="policy", default=True),
        SoftPoint(
            name="simple_ids",
            kind="policy",
            default=False,
            description="When true, use collect/freeze/decide/… ids (demos/tests)",
        ),
    )
    io_contract = TemplateIOContract(
        inputs={
            "task_id": "string",
            "modality": "string",
            "acceptance_criteria": "array",
            "goal": "string",
        },
        outputs={"gate": "object", "verdict": "string"},
    )

    def build(self, params: GraphTemplateParams) -> ExecutionGraph:
        b = params.soft_bindings
        inputs = dict(params.inputs or {})
        task_id = str(b.get("task_id") or inputs.get("task_id") or "infer-task")
        run_id = str(b.get("run_id") or inputs.get("run_id") or "infer-run")
        modality = str(b.get("modality") or inputs.get("modality") or "text")
        criteria = b.get("acceptance_criteria") or inputs.get("acceptance_criteria") or []
        if isinstance(criteria, str):
            criteria = [criteria]
        simple_ids = bool(b.get("simple_ids", inputs.get("simple_ids", False)))

        base = {
            "task_id": task_id,
            "run_id": run_id,
            "modality": modality,
            "hop": b.get("hop") or inputs.get("hop") or task_id,
            "acceptance_criteria": list(criteria),
            "decide_principal": b.get("decide_principal")
            or inputs.get("decide_principal")
            or "decide_agent",
            "qa_principal": b.get("qa_principal")
            or inputs.get("qa_principal")
            or "qa_agent",
            "max_retries": int(b.get("max_retries") or inputs.get("max_retries") or 3),
            "produce_kind": b.get("produce_kind") or inputs.get("produce_kind") or "noop",
            "hop_recipe": b.get("hop_recipe") or inputs.get("hop_recipe") or "",
            "seed_evidence": b.get("seed_evidence") or inputs.get("seed_evidence") or [],
            "require_evidence_anchors": bool(
                b.get(
                    "require_evidence_anchors",
                    inputs.get("require_evidence_anchors", True),
                )
            ),
            "decide_kind": b.get("decide_kind") or inputs.get("decide_kind"),
            "qa_kind": b.get("qa_kind") or inputs.get("qa_kind"),
            "collect_kind": b.get("collect_kind") or inputs.get("collect_kind"),
            "freeze_kind": b.get("freeze_kind") or inputs.get("freeze_kind"),
            "deterministic_kind": b.get("deterministic_kind")
            or inputs.get("deterministic_kind"),
            "gate_kind": b.get("gate_kind") or inputs.get("gate_kind"),
        }
        g = ExecutionGraph(
            id=f"audited-infer-accept-{run_id}-{task_id}",
            goal=params.goal or f"Audited decision {task_id} ({modality})",
            version=self.version,
            template_name=self.name,
            template_version=self.version,
        )
        nodes: list[GraphNode] = []
        append_audited_infer_accept(
            nodes,
            after=None,
            task_id=task_id,
            modality=modality,
            base=base,
            produce_kind=str(base["produce_kind"]),
            simple_ids=simple_ids,
        )
        for n in nodes:
            g.add_node(n)
        # Linear depends_on already set; add explicit control edges for tooling.
        ordered = [n.id for n in nodes]
        for i in range(len(ordered) - 1):
            g.add_dependency(
                DependencyEdge(
                    from_node=ordered[i],
                    to_node=ordered[i + 1],
                    types=["control"],
                    reason="audited_spine",
                )
            )
        return g
