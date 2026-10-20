"""Host script instrumentor over :class:`DurableGraphGenerator`.

Verb-led steps (``start``, ``answer``, ``inspect``, ``rebuild``, …) advance a
durable run the same way a future CLI/TUI or MCP driver would. Soft-point
answers use :class:`GuidanceBinding`. Control flow stays in registered graphs;
this module only instruments the host session.

Story YAML may attach per-step ``expect`` blocks (test-only). The instrumentor
returns :class:`StepObservation` values and does not assert.

See ``docs/reference/durable-graph-generators.md``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.durable_generator_host import (
    GuidanceBinding,
    build_host_generator,
)
from mechaharness.durable_graph_generator import (
    GraphYield,
    InMemoryGeneratorRunStore,
    RunInspection,
    YieldKind,
)

StoreMode = Literal["memory", "shared"]
ScriptError = Literal["permission", "sequence", "unexpected_advice"]


class StartBody(BaseModel):
    """Begin a run on the script graph (or an override ``graph`` id)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    graph: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    controller: str | None = None


class AnswerBody(BaseModel):
    """Answer a pending advice yield (soft-point UI seam)."""

    model_config = ConfigDict(extra="forbid")

    choose: str | None = None
    choice_id: str | None = None
    text: str | None = None
    request_id: str | None = None
    soft_point: str | None = None
    structured: dict[str, Any] = Field(default_factory=dict)
    controller: str | None = None
    idempotency_key: str | None = None
    # Replay the prior advice sequence (idempotent double-resume).
    replay: bool = False
    # Deliberately send a stale expected_sequence.
    stale: bool = False


class InspectBody(BaseModel):
    """Diagnostics without advancing the run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None


class RebuildBody(BaseModel):
    """Rebuild the host generator on the same store (process restart)."""

    model_config = ConfigDict(extra="forbid")


class ListRecipesBody(BaseModel):
    """List recipes available on the current generator."""

    model_config = ConfigDict(extra="forbid")


class DurableScriptStep(BaseModel):
    """One verb-led controller action (exactly one verb key)."""

    model_config = ConfigDict(extra="forbid")

    start: StartBody | None = None
    answer: AnswerBody | None = None
    inspect: InspectBody | None = None
    rebuild: RebuildBody | None = None
    list_recipes: ListRecipesBody | None = None

    @model_validator(mode="after")
    def _exactly_one_verb(self) -> DurableScriptStep:
        verbs = [
            ("start", self.start),
            ("answer", self.answer),
            ("inspect", self.inspect),
            ("rebuild", self.rebuild),
            ("list_recipes", self.list_recipes),
        ]
        present = [name for name, body in verbs if body is not None]
        if len(present) != 1:
            raise ValueError(
                "each step needs exactly one of start/answer/inspect/"
                f"rebuild/list_recipes; got {present or 'none'}"
            )
        return self

    @property
    def verb(self) -> str:
        if self.start is not None:
            return "start"
        if self.answer is not None:
            return "answer"
        if self.inspect is not None:
            return "inspect"
        if self.rebuild is not None:
            return "rebuild"
        return "list_recipes"


class DurableScript(BaseModel):
    """Host-executable session script (no test expects).

    ``steps`` may be empty when the script only carries session knobs for a
    CLI instrumentor that drives verbs one at a time.
    """

    model_config = ConfigDict(extra="forbid")

    graph: str
    controller: str = "host"
    store: StoreMode = "memory"
    steps: list[DurableScriptStep] = Field(default_factory=list)


class StepObservation(BaseModel):
    """Structured view of one step outcome for hosts and hard story checks."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    kind: YieldKind | None = None
    sequence: int | None = None
    request_id: str | None = None
    question: str | None = None
    phase: str | None = None
    pending_question: str | None = None
    pending_cleared: bool = True
    same_request_id: bool = False
    guidance_yields: int | None = None
    resumes: int | None = None
    local_steps: int | None = None
    recipe_listed: bool = False
    recipes: list[str] = Field(default_factory=list)
    controller: str | None = None
    controller_ok: bool = False
    same_sequence: bool | None = None
    separate_calls: bool = False
    error: ScriptError | None = None
    yield_obj: GraphYield | None = Field(default=None, exclude=True)
    inspect_obj: RunInspection | None = Field(default=None, exclude=True)

    def as_expect_dict(self) -> dict[str, Any]:
        """Flat dict for hard ``expect`` / ``expect_error`` comparison."""
        data = self.model_dump(exclude={"yield_obj", "inspect_obj"})
        # Alias question onto pending_question when useful for YAML scans.
        if data.get("question") is None and data.get("pending_question"):
            data["question"] = data["pending_question"]
        return data


class DurableInstrumentor:
    """Run a :class:`DurableScript` against a host durable generator."""

    def __init__(self, script: DurableScript) -> None:
        self.script = script
        self._store: InMemoryGeneratorRunStore | None = (
            InMemoryGeneratorRunStore() if script.store == "shared" else None
        )
        self._gen = build_host_generator(run_store=self._store)
        self._last_yield: GraphYield | None = None
        self._last_advice: GraphYield | None = None
        self._start_yield: GraphYield | None = None
        self._run_id: str | None = None
        self._graph = script.graph

    def run(self) -> list[StepObservation]:
        if not self.script.steps:
            raise ValueError("script must declare at least one step to run()")
        return [self._run_step(step) for step in self.script.steps]

    def start(self, body: StartBody) -> StepObservation:
        return self._do_start(body)

    def answer(self, body: AnswerBody) -> StepObservation:
        return self._do_answer(body)

    def inspect(self, body: InspectBody) -> StepObservation:
        return self._do_inspect(body)

    def rebuild(self) -> StepObservation:
        return self._do_rebuild()

    def list_recipes(self) -> StepObservation:
        return self._do_list_recipes()

    def _run_step(self, step: DurableScriptStep) -> StepObservation:
        if step.start is not None:
            return self._do_start(step.start)
        if step.answer is not None:
            return self._do_answer(step.answer)
        if step.inspect is not None:
            return self._do_inspect(step.inspect)
        if step.rebuild is not None:
            return self._do_rebuild()
        return self._do_list_recipes()

    def _do_start(self, body: StartBody) -> StepObservation:
        graph = body.graph or self._graph
        controller = body.controller or self.script.controller
        y = self._gen.start(
            graph,
            body.inputs,
            controller_id=controller,
            run_id=body.run_id,
        )
        self._note_yield(y)
        self._start_yield = y
        self._run_id = y.run_id
        self._graph = graph
        return self._from_yield("start", y, inspect=True)

    def _do_answer(self, body: AnswerBody) -> StepObservation:
        if self._last_yield is None or self._run_id is None:
            raise ValueError("answer requires a prior start yield")

        choice = body.choice_id or body.choose
        if not choice and not body.text and not body.structured:
            # No soft-point answer available — same failure a strict UI sees.
            return StepObservation(verb="answer", error="unexpected_advice")

        advice = self._last_advice or self._last_yield
        if body.replay:
            if self._last_advice is None:
                raise ValueError("answer.replay requires a prior advice yield")
            expected_sequence = self._last_advice.sequence
            request_id = body.request_id or self._last_advice.request_id or ""
        elif body.stale:
            expected_sequence = advice.sequence + 100
            request_id = body.request_id or advice.request_id or ""
        else:
            expected_sequence = self._last_yield.sequence
            request_id = body.request_id or self._last_yield.request_id or ""

        binding = GuidanceBinding(
            soft_point=body.soft_point,
            choose=body.choose,
            choice_id=body.choice_id,
            text=body.text,
            request_id=request_id,
            structured=dict(body.structured or {}),
        )
        controller = body.controller or self.script.controller
        try:
            y = self._gen.resume(
                self._run_id,
                binding.to_response(request_id=request_id),
                expected_sequence=expected_sequence,
                request_id=request_id or None,
                controller_id=controller,
                idempotency_key=body.idempotency_key,
            )
        except PermissionError:
            return StepObservation(verb="answer", error="permission")
        except ValueError:
            return StepObservation(verb="answer", error="sequence")

        previous = self._last_yield
        self._note_yield(y)
        obs = self._from_yield("answer", y, inspect=True)
        if previous is not None:
            obs = obs.model_copy(
                update={"same_sequence": previous.sequence == y.sequence}
            )
        if self._start_yield is not None:
            obs = obs.model_copy(
                update={
                    "separate_calls": self._start_yield.sequence != y.sequence
                }
            )
        return obs

    def _do_inspect(self, body: InspectBody) -> StepObservation:
        run_id = body.run_id or self._run_id
        if not run_id:
            raise ValueError("inspect requires a run_id")
        insp = self._gen.inspect(run_id)
        recipes = [r.recipe_id for r in self._gen.list_recipes()]
        pending = insp.pending_request
        cost = dict(insp.cost or {})
        same_rid = bool(
            pending
            and self._last_advice
            and pending.request_id == self._last_advice.request_id
        )
        return StepObservation(
            verb="inspect",
            kind=insp.last_yield.kind if insp.last_yield else None,
            sequence=insp.sequence,
            request_id=pending.request_id if pending else None,
            question=pending.question if pending else None,
            phase=str(insp.phase),
            pending_question=pending.question if pending else None,
            pending_cleared=pending is None,
            same_request_id=same_rid,
            guidance_yields=cost.get("guidance_yields"),
            resumes=cost.get("resumes"),
            local_steps=cost.get("local_steps"),
            recipe_listed=self._graph in recipes,
            recipes=recipes,
            controller=insp.controller_id,
            controller_ok=insp.controller_id == self.script.controller,
            inspect_obj=insp,
        )

    def _do_rebuild(self) -> StepObservation:
        if self._store is None:
            raise ValueError("rebuild requires store: shared")
        self._gen = build_host_generator(run_store=self._store)
        return StepObservation(verb="rebuild")

    def _do_list_recipes(self) -> StepObservation:
        recipes = [r.recipe_id for r in self._gen.list_recipes()]
        return StepObservation(
            verb="list_recipes",
            recipe_listed=self._graph in recipes,
            recipes=recipes,
        )

    def _note_yield(self, y: GraphYield) -> None:
        self._last_yield = y
        self._run_id = y.run_id
        if y.kind == "advice_requested":
            self._last_advice = y

    def _from_yield(
        self,
        verb: str,
        y: GraphYield,
        *,
        inspect: bool,
    ) -> StepObservation:
        insp: RunInspection | None = None
        recipes: list[str] = []
        if inspect:
            insp = self._gen.inspect(y.run_id)
            recipes = [r.recipe_id for r in self._gen.list_recipes()]
        pending = insp.pending_request if insp else None
        cost = dict(insp.cost) if insp else {}
        question = None
        if pending:
            question = pending.question
        elif y.kind == "advice_requested":
            question = (y.payload or {}).get("question") or None
            if question is None and y.summary:
                question = y.summary
        same_rid = bool(
            pending and y.request_id and pending.request_id == y.request_id
        )
        return StepObservation(
            verb=verb,
            kind=y.kind,
            sequence=y.sequence,
            request_id=y.request_id,
            question=question,
            phase=str(insp.phase) if insp else None,
            pending_question=pending.question if pending else None,
            pending_cleared=pending is None,
            same_request_id=same_rid,
            guidance_yields=cost.get("guidance_yields"),
            resumes=cost.get("resumes"),
            local_steps=cost.get("local_steps"),
            recipe_listed=self._graph in recipes if recipes else False,
            recipes=recipes,
            controller=insp.controller_id if insp else None,
            controller_ok=(
                bool(insp and insp.controller_id == self.script.controller)
            ),
            yield_obj=y,
            inspect_obj=insp,
        )


def script_from_mapping(data: dict[str, Any]) -> DurableScript:
    """Build a product script from a mapping (strips test-only keys)."""
    steps_raw = data.get("steps") or []
    clean_steps: list[dict[str, Any]] = []
    for raw in steps_raw:
        if not isinstance(raw, dict):
            raise ValueError("each step must be a mapping")
        clean = {
            k: v
            for k, v in raw.items()
            if k not in {"expect", "expect_error"}
        }
        clean_steps.append(clean)
    return DurableScript.model_validate(
        {
            "graph": data.get("graph") or data.get("recipe"),
            "controller": data.get("controller", "host"),
            "store": data.get("store", "memory"),
            "steps": clean_steps,
        }
    )


__all__ = [
    "AnswerBody",
    "DurableInstrumentor",
    "DurableScript",
    "DurableScriptStep",
    "InspectBody",
    "ListRecipesBody",
    "RebuildBody",
    "ScriptError",
    "StartBody",
    "StepObservation",
    "StoreMode",
    "script_from_mapping",
]
