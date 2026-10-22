"""Durable graph-generator IoC: host-facing driven runs with ordered yields.

This is the primary long-run execution façade for judgment-bearing graphs.
A frontier agent, human CLI/TUI, or :class:`ScriptedDriver` advances a durable
run through ``start`` / ``resume`` / ``inspect`` / ``cancel``. Local workers and
deterministic tools perform token-heavy work; higher-level judgment returns as
an ``advice_requested`` yield — an ordinary call result in the driver session,
not a recursive callback into a pending MCP tool.

``GraphExecutor`` remains the internal node walker. MCP is a transport adapter
(not shipped here). Approval interrupts and sparse in-process advisors are
distinct primitives — ordinary guidance must not unlock approval-only mutations.

See ``docs/requirements/durable-graph-generators.md`` and
``docs/reference/durable-graph-generators.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from pyiv.time import DateTimeService

from mechaharness.checkpoint_store import CheckpointStore
from mechaharness.core.events import CoreEvent, Event, EventLog, event_type_key
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph_templates import GraphTemplateRegistry
from mechaharness.graph_templates.base import GraphTemplate

YieldKind = Literal[
    "progress",
    "advice_requested",
    "running",
    "completed",
    "failed",
    "cancelled",
]
RunPhase = Literal[
    "created",
    "running",
    "guidance_required",
    "suspended",
    "completed",
    "failed",
    "cancelled",
]


class GraphYieldPublished(CoreEvent):
    """A committed generator yield became externally observable."""

    name = "graph_yield"


class GuidanceResumeApplied(CoreEvent):
    """Authorized guidance was applied to a pending yield."""

    name = "guidance_resume"


class GeneratorRunCancelled(CoreEvent):
    """A durable generator run was cancelled."""

    name = "generator_cancel"


class GuidanceChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: str = ""


class GuidanceRequest(BaseModel):
    """Typed external guidance request surfaced as a yield payload."""

    model_config = ConfigDict(extra="allow")

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    choices: list[GuidanceChoice] = Field(default_factory=list)
    recommendation: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    requested_authority: str = "advisory"
    context_version: str = ""
    parent_node_id: str | None = None
    response_schema: dict[str, Any] = Field(default_factory=dict)


class GuidanceResponse(BaseModel):
    """Driver answer to a pending :class:`GuidanceRequest`."""

    model_config = ConfigDict(extra="allow")

    request_id: str
    choice_id: str | None = None
    text: str | None = None
    structured: dict[str, Any] = Field(default_factory=dict)
    deferred: bool = False
    refused: bool = False


class GraphYield(BaseModel):
    """Ordered, immutable externally visible yield envelope."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    sequence: int
    kind: YieldKind
    checkpoint_id: str | None = None
    request_id: str | None = None
    recipe_id: str | None = None
    graph_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class RecipeDescriptor(BaseModel):
    """Discoverable recipe entry for ``list_recipes``."""

    model_config = ConfigDict(extra="allow")

    recipe_id: str
    version: str | None = None
    status: str = "active"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    soft_points: list[str] = Field(default_factory=list)


class RunInspection(BaseModel):
    """Diagnostics without advancing the run."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    recipe_id: str
    graph_id: str | None = None
    phase: RunPhase
    sequence: int
    controller_id: str
    pending_request: GuidanceRequest | None = None
    checkpoint_id: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    cost: dict[str, Any] = Field(default_factory=dict)
    last_yield: GraphYield | None = None


class GeneratorCostCounters(BaseModel):
    model_config = ConfigDict(extra="allow")

    local_steps: int = 0
    guidance_yields: int = 0
    resumes: int = 0
    rejected_resumes: int = 0


class GeneratorRunRecord(BaseModel):
    """Durable continuation record for one generator-driven run."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    recipe_id: str
    graph_id: str
    controller_id: str
    phase: RunPhase = "created"
    sequence: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)
    pending_request: GuidanceRequest | None = None
    checkpoint_id: str | None = None
    guidance_queue: list[GuidanceRequest] = Field(default_factory=list)
    guidance_history: list[dict[str, Any]] = Field(default_factory=list)
    last_yield: GraphYield | None = None
    idempotency: dict[str, GraphYield] = Field(default_factory=dict)
    cost: GeneratorCostCounters = Field(default_factory=GeneratorCostCounters)
    artifact_refs: list[str] = Field(default_factory=list)
    error: str | None = None


class GeneratorRunStore(ABC):
    """Persistence for generator run records (process-restart capable when durable)."""

    @abstractmethod
    def save(self, record: GeneratorRunRecord) -> None: ...

    @abstractmethod
    def load(self, run_id: str) -> GeneratorRunRecord | None: ...


class InMemoryGeneratorRunStore(GeneratorRunStore):
    """Shared in-process store; inject the same instance across “restarts”."""

    def __init__(self) -> None:
        self._records: dict[str, GeneratorRunRecord] = {}

    def save(self, record: GeneratorRunRecord) -> None:
        self._records[record.run_id] = record.model_copy(deep=True)

    def load(self, run_id: str) -> GeneratorRunRecord | None:
        found = self._records.get(run_id)
        return None if found is None else found.model_copy(deep=True)


class FileGeneratorRunStore(GeneratorRunStore):
    """JSON-file run store so MCP stdio processes can share durable state."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def save(self, record: GeneratorRunRecord) -> None:
        import json

        data = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            data = {}
        data[record.run_id] = record.model_dump(mode="json")
        self._path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def load(self, run_id: str) -> GeneratorRunRecord | None:
        import json

        data = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return None
        raw = data.get(run_id)
        if not isinstance(raw, dict):
            return None
        return GeneratorRunRecord.model_validate(raw)


class CheckpointBackedGeneratorRunStore(GeneratorRunStore):
    """Persist run records via :class:`CheckpointStore` graph payloads."""

    def __init__(self, checkpoint_store: CheckpointStore) -> None:
        self._store = checkpoint_store
        self._cache = InMemoryGeneratorRunStore()

    def save(self, record: GeneratorRunRecord) -> None:
        self._cache.save(record)
        graph = ExecutionGraph(
            id=record.graph_id,
            goal=f"generator:{record.recipe_id}",
        )
        graph.add_node(
            GraphNode(
                id="generator_continuation",
                kind="generator_continuation",
                payload={
                    "run_id": record.run_id,
                    "phase": record.phase,
                    "generator_run": record.model_dump(mode="json"),
                },
            )
        )
        rev = self._store.save(
            graph,
            run_id=record.run_id,
            boundary="commit",
            fingerprint=f"generator:{record.recipe_id}",
        )
        record.checkpoint_id = f"{record.run_id}@{rev}"
        self._cache.save(record)

    def load(self, run_id: str) -> GeneratorRunRecord | None:
        cached = self._cache.load(run_id)
        if cached is not None:
            return cached
        graph = self._store.latest(run_id=run_id)
        if graph is None:
            return None
        node = graph.nodes.get("generator_continuation")
        raw = node.payload.get("generator_run") if node is not None else None
        if not isinstance(raw, dict):
            return None
        record = GeneratorRunRecord.model_validate(raw)
        self._cache.save(record)
        return record


class GeneratorControllerAuth(ABC):
    """Controller lease / ownership for generator operations."""

    @abstractmethod
    def authorize(
        self,
        record: GeneratorRunRecord,
        *,
        controller_id: str | None,
        operation: str,
    ) -> None: ...


class LeaseControllerAuth(GeneratorControllerAuth):
    """Require the controlling identity; run_id alone never confers control."""

    def authorize(
        self,
        record: GeneratorRunRecord,
        *,
        controller_id: str | None,
        operation: str,
    ) -> None:
        if operation == "inspect":
            return
        if not controller_id:
            raise PermissionError(
                f"controller identity required for {operation} on run {record.run_id}"
            )
        if controller_id != record.controller_id:
            raise PermissionError(
                f"controller {controller_id!r} does not own run {record.run_id}"
            )


class DurableGraphGenerator:
    """Transport-neutral durable generator over registered recipes."""

    def __init__(
        self,
        registry: GraphTemplateRegistry,
        run_store: GeneratorRunStore,
        event_log: EventLog,
        datetime_service: DateTimeService,
        controller_auth: GeneratorControllerAuth | None = None,
        checkpoint_store: CheckpointStore | None = None,
        local_work: Any | None = None,
    ) -> None:
        self._registry = registry
        self._runs = run_store
        self._events = event_log
        self._datetime = datetime_service
        self._auth = controller_auth or LeaseControllerAuth()
        self._checkpoints = checkpoint_store
        # Optional GeneratorLocalWork (duck-typed) for post-guidance bursts.
        self._local_work = local_work

    def list_recipes(self) -> list[RecipeDescriptor]:
        out: list[RecipeDescriptor] = []
        for recipe_id in sorted(self._registry.names()):
            template = self._registry.get(recipe_id)
            if template is None:
                continue
            out.append(
                RecipeDescriptor(
                    recipe_id=recipe_id,
                    version=self._registry.active_version(recipe_id),
                    status=getattr(template, "status", "active"),
                    input_schema=_input_schema_for(template),
                    soft_points=[p.name for p in template.soft_points],
                )
            )
        return out

    def start(
        self,
        recipe_id: str,
        inputs: dict[str, Any] | None = None,
        *,
        controller_id: str,
        run_id: str | None = None,
        graph_id: str | None = None,
    ) -> GraphYield:
        template = self._registry.get(recipe_id)
        if template is None:
            raise KeyError(f"unknown recipe {recipe_id!r}")
        inputs = dict(inputs or {})
        run_id = run_id or str(uuid4())
        graph_id = graph_id or f"graph-{run_id}"
        record = GeneratorRunRecord(
            run_id=run_id,
            recipe_id=recipe_id,
            graph_id=graph_id,
            controller_id=controller_id,
            phase="running",
            inputs=inputs,
            guidance_queue=_guidance_queue_from(template, inputs),
            artifact_refs=list(inputs.get("artifact_refs") or ()),
        )
        if self._checkpoints is not None:
            # Touch checkpoint seam so durability is real, not decorative.
            graph = ExecutionGraph(id=graph_id, goal=inputs.get("goal") or recipe_id)
            graph.add_node(
                GraphNode(
                    id="generator_root",
                    kind="generator_root",
                    payload={"recipe_id": recipe_id},
                )
            )
            rev = self._checkpoints.save(
                graph,
                run_id=run_id,
                boundary="commit",
                fingerprint=f"generator:{recipe_id}",
            )
            record.checkpoint_id = f"{run_id}@{rev}"
        return self._advance(record, emit_start=True)

    def resume(
        self,
        run_id: str,
        response: GuidanceResponse | dict[str, Any] | None = None,
        *,
        expected_sequence: int,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        controller_id: str | None = None,
    ) -> GraphYield:
        record = self._require(run_id)
        if idempotency_key and idempotency_key in record.idempotency:
            return record.idempotency[idempotency_key]
        try:
            self._auth.authorize(record, controller_id=controller_id, operation="resume")
        except PermissionError:
            record.cost.rejected_resumes += 1
            self._runs.save(record)
            raise
        if record.phase in {"completed", "failed", "cancelled"}:
            raise ValueError(f"run {run_id} is already {record.phase}")
        if expected_sequence != record.sequence:
            record.cost.rejected_resumes += 1
            self._runs.save(record)
            raise ValueError(
                f"stale sequence: expected {record.sequence}, got {expected_sequence}"
            )
        if record.phase == "guidance_required":
            if record.pending_request is None:
                raise RuntimeError("guidance_required without pending_request")
            if response is None:
                record.cost.rejected_resumes += 1
                self._runs.save(record)
                raise ValueError("guidance response required")
            if isinstance(response, dict):
                response = GuidanceResponse.model_validate(response)
            pending = record.pending_request
            rid = request_id or response.request_id
            if rid != pending.request_id:
                record.cost.rejected_resumes += 1
                self._runs.save(record)
                raise ValueError(
                    f"request_id mismatch: pending {pending.request_id}, got {rid}"
                )
            if pending.requested_authority == "final_approval":
                record.cost.rejected_resumes += 1
                self._runs.save(record)
                raise PermissionError(
                    "ordinary guidance cannot satisfy final_approval; "
                    "use ApprovalInterrupt"
                )
            if response.refused:
                record.phase = "failed"
                record.error = "guidance_refused"
                record.pending_request = None
                y = self._publish(
                    record,
                    kind="failed",
                    payload={"error": "guidance_refused"},
                    summary="guidance refused",
                )
                if idempotency_key:
                    record.idempotency[idempotency_key] = y
                    self._runs.save(record)
                return y
            if response.deferred:
                record.phase = "suspended"
                y = self._publish(
                    record,
                    kind="running",
                    payload={"deferred": True, "request_id": pending.request_id},
                    summary="guidance deferred",
                    request_id=pending.request_id,
                )
                if idempotency_key:
                    record.idempotency[idempotency_key] = y
                    self._runs.save(record)
                return y
            if pending.choices and response.choice_id:
                allowed = {c.id for c in pending.choices}
                if response.choice_id not in allowed:
                    record.cost.rejected_resumes += 1
                    self._runs.save(record)
                    raise ValueError(
                        f"choice {response.choice_id!r} not in {sorted(allowed)}"
                    )
            record.guidance_history.append(
                {
                    "request": pending.model_dump(mode="json"),
                    "response": response.model_dump(mode="json"),
                }
            )
            record.pending_request = None
            record.phase = "running"
            record.cost.resumes += 1
            self._emit(
                GuidanceResumeApplied,
                record,
                {
                    "request_id": pending.request_id,
                    "choice_id": response.choice_id,
                    "sequence": record.sequence,
                },
            )
        elif response is not None:
            record.cost.rejected_resumes += 1
            self._runs.save(record)
            raise ValueError("no pending guidance for this resume")
        y = self._advance(record)
        if idempotency_key:
            record.idempotency[idempotency_key] = y
            self._runs.save(record)
        return y

    def inspect(self, run_id: str) -> RunInspection:
        record = self._require(run_id)
        self._auth.authorize(record, controller_id=None, operation="inspect")
        return RunInspection(
            run_id=record.run_id,
            recipe_id=record.recipe_id,
            graph_id=record.graph_id,
            phase=record.phase,
            sequence=record.sequence,
            controller_id=record.controller_id,
            pending_request=record.pending_request,
            checkpoint_id=record.checkpoint_id,
            artifact_refs=list(record.artifact_refs),
            cost=record.cost.model_dump(),
            last_yield=record.last_yield,
        )

    def cancel(
        self,
        run_id: str,
        *,
        controller_id: str | None = None,
        expected_sequence: int | None = None,
    ) -> GraphYield:
        record = self._require(run_id)
        self._auth.authorize(record, controller_id=controller_id, operation="cancel")
        if expected_sequence is not None and expected_sequence != record.sequence:
            raise ValueError(
                f"stale sequence: expected {record.sequence}, got {expected_sequence}"
            )
        if record.phase in {"completed", "failed", "cancelled"}:
            if record.last_yield is not None and record.last_yield.kind == "cancelled":
                return record.last_yield
            raise ValueError(f"run {run_id} is already {record.phase}")
        record.phase = "cancelled"
        record.pending_request = None
        self._emit(GeneratorRunCancelled, record, {"sequence": record.sequence})
        return self._publish(
            record,
            kind="cancelled",
            payload={},
            summary="cancelled",
        )

    def _require(self, run_id: str) -> GeneratorRunRecord:
        record = self._runs.load(run_id)
        if record is None:
            raise KeyError(f"unknown run {run_id!r}")
        return record

    def _advance(
        self, record: GeneratorRunRecord, *, emit_start: bool = False
    ) -> GraphYield:
        if emit_start:
            self._runs.save(record)
        # Local work between yields (token-heavy work stands in as a step count).
        record.cost.local_steps += 1
        if record.guidance_queue:
            req = record.guidance_queue.pop(0)
            record.pending_request = req
            record.phase = "guidance_required"
            record.cost.guidance_yields += 1
            return self._publish(
                record,
                kind="advice_requested",
                payload=req.model_dump(mode="json"),
                summary=req.question,
                request_id=req.request_id,
            )
        work_payload: dict[str, Any] = {}
        if self._local_work is not None:
            run_fn = getattr(self._local_work, "run", self._local_work)
            raw = run_fn(record)
            if isinstance(raw, dict):
                work_payload = raw
            if work_payload.get("result") == "failed":
                record.phase = "failed"
                record.error = str(work_payload.get("error") or "local_work_failed")
                return self._publish(
                    record,
                    kind="failed",
                    payload={
                        **work_payload,
                        "guidance_history": list(record.guidance_history),
                    },
                    summary=record.error,
                )
        record.phase = "completed"
        return self._publish(
            record,
            kind="completed",
            payload={
                "result": work_payload.get("result", record.inputs.get("result", "ok")),
                "guidance_history": list(record.guidance_history),
                **{k: v for k, v in work_payload.items() if k != "result"},
            },
            summary="completed",
        )

    def _publish(
        self,
        record: GeneratorRunRecord,
        *,
        kind: YieldKind,
        payload: dict[str, Any],
        summary: str,
        request_id: str | None = None,
    ) -> GraphYield:
        record.sequence += 1
        if self._checkpoints is not None:
            graph = ExecutionGraph(
                id=record.graph_id,
                goal=record.recipe_id,
            )
            graph.add_node(
                GraphNode(
                    id="generator_continuation",
                    kind="generator_continuation",
                    payload={
                        "phase": record.phase,
                        "sequence": record.sequence,
                        "generator_run": record.model_dump(mode="json"),
                    },
                )
            )
            rev = self._checkpoints.save(
                graph,
                run_id=record.run_id,
                boundary="commit",
                fingerprint=f"generator:{record.recipe_id}",
            )
            record.checkpoint_id = f"{record.run_id}@{rev}"
        y = GraphYield(
            run_id=record.run_id,
            sequence=record.sequence,
            kind=kind,
            checkpoint_id=record.checkpoint_id,
            request_id=request_id,
            recipe_id=record.recipe_id,
            graph_id=record.graph_id,
            payload=payload,
            summary=summary,
        )
        record.last_yield = y
        self._runs.save(record)
        self._emit(
            GraphYieldPublished,
            record,
            {
                "sequence": y.sequence,
                "kind": y.kind,
                "request_id": y.request_id,
                "checkpoint_id": y.checkpoint_id,
            },
        )
        return y

    def _emit(
        self,
        event_cls: type[CoreEvent],
        record: GeneratorRunRecord,
        payload: dict[str, Any],
    ) -> None:
        body = {
            "run_id": record.run_id,
            "graph_id": record.graph_id,
            "recipe_id": record.recipe_id,
            "controller_id": record.controller_id,
            **payload,
        }
        self._events.emit(
            Event(
                type=event_type_key(event_cls),
                agent_id="durable_graph_generator",
                run_id=record.run_id,
                payload=body,
                ts=self._datetime.now_utc(),
            )
        )


class ScriptedDriver:
    """Deterministic driver for offline regression of yield sequences."""

    def __init__(self, generator: DurableGraphGenerator) -> None:
        self._gen = generator

    def run(
        self,
        recipe_id: str,
        inputs: dict[str, Any] | None = None,
        *,
        controller_id: str = "scripted",
        responses: Sequence[GuidanceResponse | dict[str, Any]] | None = None,
        expected_kinds: list[YieldKind] | None = None,
        strict_unexpected_advice: bool = True,
        run_id: str | None = None,
    ) -> list[GraphYield]:
        responses = list(responses or ())
        resp_i = 0
        yields: list[GraphYield] = []
        status = self._gen.start(
            recipe_id, inputs, controller_id=controller_id, run_id=run_id
        )
        yields.append(status)
        while status.kind not in {"completed", "failed", "cancelled"}:
            if status.kind == "advice_requested":
                if resp_i >= len(responses):
                    if strict_unexpected_advice:
                        raise AssertionError(
                            f"unexpected advice at sequence {status.sequence}: "
                            f"{status.summary!r}"
                        )
                    break
                answer = responses[resp_i]
                resp_i += 1
                if isinstance(answer, dict):
                    answer = GuidanceResponse.model_validate(answer)
                if not answer.request_id:
                    answer = answer.model_copy(
                        update={"request_id": status.request_id or ""}
                    )
                status = self._gen.resume(
                    status.run_id,
                    answer,
                    expected_sequence=status.sequence,
                    request_id=status.request_id,
                    controller_id=controller_id,
                    idempotency_key=f"{status.run_id}:{status.sequence}",
                )
            else:
                status = self._gen.resume(
                    status.run_id,
                    expected_sequence=status.sequence,
                    controller_id=controller_id,
                )
            yields.append(status)
        if expected_kinds is not None:
            got = [y.kind for y in yields]
            if got != list(expected_kinds):
                raise AssertionError(f"yield kinds {got} != {expected_kinds}")
        if resp_i != len(responses) and strict_unexpected_advice:
            raise AssertionError(
                f"unused scripted responses: {len(responses) - resp_i} left"
            )
        return yields


def _input_schema_for(template: GraphTemplate) -> dict[str, Any]:
    props = {
        "goal": {"type": "string"},
        "guidance": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Optional M1 schedule of GuidanceRequest objects",
        },
    }
    for point in template.soft_points:
        props[point.name] = {
            "type": "string",
            "description": point.description or point.kind,
        }
    return {"type": "object", "properties": props}


def _guidance_queue_from(
    template: GraphTemplate, inputs: dict[str, Any]
) -> list[GuidanceRequest]:
    raw = inputs.get("guidance")
    if isinstance(raw, list) and raw:
        return [GuidanceRequest.model_validate(item) for item in raw]
    queue: list[GuidanceRequest] = []
    for point in template.soft_points:
        if getattr(point, "kind", None) == "guidance" or point.name.startswith(
            "external_guidance"
        ):
            # Prefer host/default choices from SoftPoint.default when provided.
            default = point.default if isinstance(point.default, dict) else {}
            raw_choices = default.get("choices")
            if isinstance(raw_choices, list) and raw_choices:
                choices = [GuidanceChoice.model_validate(c) for c in raw_choices]
                recommendation = default.get("recommendation")
            else:
                choices = [
                    GuidanceChoice(id="accept", label="Accept recommendation"),
                    GuidanceChoice(id="revise", label="Request revision"),
                ]
                recommendation = "accept"
            queue.append(
                GuidanceRequest(
                    question=point.description
                    or f"Guidance for soft point {point.name}",
                    requested_authority=str(default.get("requested_authority") or "advisory"),
                    context_version=point.name,
                    parent_node_id=None,
                    choices=choices,
                    recommendation=recommendation if isinstance(recommendation, str) else None,
                    evidence_refs=list(default.get("evidence_refs") or ()),
                )
            )
    # Soft bindings may inject one-shot guidance without template soft points.
    binding = inputs.get("soft_bindings") or {}
    if isinstance(binding, dict) and "guidance_request" in binding:
        queue.append(GuidanceRequest.model_validate(binding["guidance_request"]))
    return queue


def clone_run_store(store: GeneratorRunStore) -> GeneratorRunStore:
    """Test helper: new store object sharing durable records when possible."""
    if isinstance(store, InMemoryGeneratorRunStore):
        cloned = InMemoryGeneratorRunStore()
        cloned._records = deepcopy(store._records)  # noqa: SLF001
        return cloned
    return store
