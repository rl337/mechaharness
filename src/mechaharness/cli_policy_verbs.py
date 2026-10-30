"""Product verbs for host authorization and budget surfaces.

These are thin CLI façades over Config-injected ``AccessControl`` /
``CapabilityEnvelope`` and ``GraphExecutor`` budget enforcement — not probe
case bags. See ``docs/reference/access.md`` and ``docs/reference/budget.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.cli_verb import CliVerb
from mechaharness.core.access import AccessControl, GraphExecute
from mechaharness.delegation_policy import DefaultDelegationPolicy, DelegationRequest
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.host_kit import host_graph_executor
from mechaharness.inference.base import InferenceStrategy


class AccessCheckCommand(BaseModel):
    """Probe Config-bound ``AccessControl`` allow/deny for listed grants."""

    model_config = ConfigDict(extra="forbid")

    must_allow: list[str] = Field(default_factory=list)
    must_deny: list[str] = Field(default_factory=list)


class AccessCheckVerb(CliVerb):
    name = "access_check"
    params_model = AccessCheckCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = AccessCheckCommand.model_validate(params.model_dump())
        control = runtime.access_control
        if control is None:
            raise RuntimeError(
                "access_check requires AccessControl on the instrumentor "
                "(bind via Config get_access_policy / environment)"
            )
        assert isinstance(control, AccessControl)
        allows = all(control.allows([g]) for g in body.must_allow)
        denies = all(not control.allows([g]) for g in body.must_deny)
        return {
            "allows_compound": allows,
            "denies_missing": denies,
            "allows": allows,
            "denies": denies,
        }


class CapabilityEnvelopeCommand(BaseModel):
    """Narrow / widen capability envelopes (parent from Config or params)."""

    model_config = ConfigDict(extra="forbid")

    parent_grants: list[str] | None = None
    child_grants: list[str] = Field(default_factory=list)
    widen_grants: list[str] | None = None


class CapabilityEnvelopeVerb(CliVerb):
    name = "capability_envelope"
    params_model = CapabilityEnvelopeCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = CapabilityEnvelopeCommand.model_validate(params.model_dump())
        if body.parent_grants is not None:
            parent = CapabilityEnvelope(grants=list(body.parent_grants))
        elif runtime.capability_envelope is not None:
            parent = runtime.capability_envelope
        else:
            raise RuntimeError(
                "capability_envelope needs parent_grants or a Config envelope"
            )
        child = parent.narrow(grants=list(body.child_grants))
        widen_raises = False
        if body.widen_grants is not None:
            try:
                parent.narrow(grants=list(body.widen_grants))
            except ValueError:
                widen_raises = True
        decision = DefaultDelegationPolicy().decide(
            DelegationRequest(independence_required=True, parent_envelope=parent)
        )
        return {
            "narrow_ok": set(child.grants).issubset(set(parent.grants)),
            "child_grant_count": len(child.grants),
            "widen_raises": widen_raises,
            "delegation_choice": decision.choice,
        }


class RunBudgetedGraphCommand(BaseModel):
    """Run a two-node compute graph under soft and/or hard budget policies."""

    model_config = ConfigDict(extra="forbid")

    node_cost: float = 1.0
    # Single-run overrides (when soft_policy/hard_policy omitted).
    soft_limit: float | None = None
    hard_limit: float | None = None
    # Dual-run shape (legacy probe / story complete keys).
    soft_policy: dict[str, Any] | None = None
    hard_policy: dict[str, Any] | None = None
    nest: bool = False


class RunBudgetedGraphVerb(CliVerb):
    name = "run_budgeted_graph"
    params_model = RunBudgetedGraphCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = RunBudgetedGraphCommand.model_validate(params.model_dump())
        cost = float(body.node_cost)

        async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
            del context
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"id": node.id},
                cost_units=cost,
            )

        # Host-kit default GraphExecute; budget is the under-test surface here.
        executor = host_graph_executor(
            runners=[CallableGraphNodeRunner(["compute"], ok)],
            event_log=runtime.event_log,
            agent_id=runtime.agent_id,
        )

        def linear() -> ExecutionGraph:
            g = ExecutionGraph(goal="budget-limits")
            g.add_node(GraphNode(id="a", kind="compute", payload={"cost_units": cost}))
            g.add_node(
                GraphNode(
                    id="b",
                    kind="compute",
                    depends_on=["a"],
                    payload={"cost_units": cost},
                )
            )
            return g

        def nested() -> ExecutionGraph:
            from mechaharness.graph_templates.base import SubgraphNodeRunner

            child = ExecutionGraph(goal="child-budget")
            child.add_node(
                GraphNode(id="c1", kind="compute", payload={"cost_units": cost})
            )
            child.add_node(
                GraphNode(
                    id="c2",
                    kind="compute",
                    depends_on=["c1"],
                    payload={"cost_units": cost},
                )
            )
            parent = ExecutionGraph(goal="parent-budget")
            parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
            parent.add_node(
                GraphNode(
                    id="after",
                    kind="compute",
                    depends_on=["wrap"],
                    payload={"cost_units": cost},
                )
            )
            return parent

        graph_factory = nested if body.nest else linear

        if body.soft_policy is not None or body.hard_policy is not None:
            soft_map = body.soft_policy or {}
            hard_map = body.hard_policy or {}
            soft = await executor.run(
                graph_factory(),
                budget_policy=BudgetPolicy(
                    soft_limit=soft_map.get("soft_limit"),
                    hard_limit=soft_map.get("hard_limit"),
                ),
                run_id="cli:budget-soft",
                skip_linkage=True,
            )
            hard = await executor.run(
                graph_factory(),
                budget_policy=BudgetPolicy(
                    soft_limit=hard_map.get("soft_limit"),
                    hard_limit=hard_map.get("hard_limit"),
                ),
                run_id="cli:budget-hard",
                skip_linkage=True,
            )
            return {
                "soft_status": soft.status,
                "soft_error": soft.error,
                "soft_budget_level": soft.budget_level,
                "hard_status": hard.status,
                "hard_error": hard.error,
                "hard_budget_level": hard.budget_level,
                "budget_spent": hard.budget_spent,
                "status": hard.status,
                "error": hard.error,
                "budget_level": hard.budget_level,
            }

        policy = runtime.resolve_budget_policy(
            explicit=BudgetPolicy(
                soft_limit=body.soft_limit,
                hard_limit=body.hard_limit,
            )
            if body.soft_limit is not None or body.hard_limit is not None
            else None
        )
        graph = graph_factory()
        result = await executor.run(
            graph,
            budget_policy=policy,
            run_id="cli:budget",
            skip_linkage=True,
        )
        out: dict[str, Any] = {
            "status": result.status,
            "error": result.error,
            "budget_level": result.budget_level,
            "budget_spent": result.budget_spent,
        }
        if body.nest and "after" in graph.nodes:
            out["after_status"] = graph.nodes["after"].status.value
        return out


class AuthEpochResumeCommand(BaseModel):
    """Refuse resume when live authorization epoch advanced."""

    model_config = ConfigDict(extra="forbid")

    goal: str = "epoch"
    first_epoch: int = 2
    resume_epoch: int = 3


class AuthEpochResumeVerb(CliVerb):
    name = "auth_epoch_resume"
    params_model = AuthEpochResumeCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = AuthEpochResumeCommand.model_validate(params.model_dump())
        calls: list[str] = []

        async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
            del context
            calls.append(node.id)
            return NodeOutcome(status=NodeStatus.SUCCEEDED)

        registry = GraphNodeRunnerRegistry(
            [CallableGraphNodeRunner(["compute"], ok)]
        )

        class Cfg(MechaHarnessConfig):
            def get_inference_class(self) -> type[InferenceStrategy]:
                from mechaharness.inference.mock import MockInferenceStrategy

                return MockInferenceStrategy

            def get_harness_class(self) -> type[AbstractHarness]:
                return PassThroughHarness

            def get_grants(self) -> list[object]:
                return [GraphExecute]

            def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
                return registry

        executor = get_injector(Cfg()).inject(GraphExecutor)
        graph = ExecutionGraph(goal=body.goal, version="1")
        graph.add_node(GraphNode(id="a", kind="compute"))

        def envelope(epoch: int) -> CapabilityEnvelope:
            parent = runtime.capability_envelope
            if isinstance(parent, CapabilityEnvelope):
                return parent.model_copy(update={"authorization_epoch": epoch})
            return CapabilityEnvelope(
                grants=["core:graph.execute"], authorization_epoch=epoch
            )

        first = await executor.run(
            graph,
            budget_policy=runtime.resolve_budget_policy(),
            run_id="cli:auth-epoch",
            envelope=envelope(body.first_epoch),
        )
        calls.clear()
        resumed = await executor.run(
            graph,
            budget_policy=runtime.resolve_budget_policy(),
            run_id="cli:auth-epoch",
            resume=True,
            envelope=envelope(body.resume_epoch),
        )
        return {
            "first_status": first.status,
            "checkpoint_epoch": executor.store.latest_authorization_epoch(
                run_id="cli:auth-epoch"
            ),
            "resume_status": resumed.status,
            "error_contains": resumed.error or "",
            "runner_calls_after_resume": len(calls),
            "status": resumed.status,
            "error": resumed.error,
        }


class ApprovalInterruptCommand(BaseModel):
    """Suspend / resume durable human approval cycle."""

    model_config = ConfigDict(extra="forbid")

    reason: str = "approve"
    decision: str = "approve"
    actor: str = "actor"
    checkpoint: str | None = None


class ApprovalInterruptVerb(CliVerb):
    name = "approval_interrupt"
    params_model = ApprovalInterruptCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.approval_interrupt import resume_approval, suspend_for_approval

        body = ApprovalInterruptCommand.model_validate(params.model_dump())
        pending = suspend_for_approval(
            reason=body.reason,
            suspended_checkpoint_ref=body.checkpoint,
        )
        done = resume_approval(
            pending,
            decision=body.decision,
            actor=body.actor,
        )
        return {
            "initial_status": pending.status,
            "final_status": done.status,
            "actor_contains": done.actor_provenance or "",
        }


class HumanReviewGateCommand(BaseModel):
    """JudgementPolicy ask-human gate via walk-bag ``ask`` / ``ans`` registers.

    First ``decide()`` without approvals must yield ``ASK_HUMAN``. Story YAML
    ``expect: [{kind: human_review, inject: …}]`` folds ``inject`` into this
    command; approvals from inject fill ``ans`` and a second ``decide()`` runs.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = "mutate"
    action_digest: str = "sha256:story"
    require_approval_for: list[str] = Field(default_factory=lambda: ["mutate"])
    policy_version: str = "story-review"
    signals: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"id": "destructive", "p_true": 0.95}]
    )
    thresholds: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {
                "signal_id": "destructive",
                "allow_above": 0.9,
                "ask_below": 0.9,
            }
        ]
    )
    # Populated by StoryStep when expect includes kind: human_review + inject.
    inject: dict[str, Any] | None = None


class HumanReviewGateVerb(CliVerb):
    name = "human_review_gate"
    params_model = HumanReviewGateCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.inference.judge import NoulSignal
        from mechaharness.judgement_policy import (
            JudgementFacts,
            JudgementPolicy,
            JudgementThreshold,
            decide,
        )
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = HumanReviewGateCommand.model_validate(params.model_dump())
        bag = WalkBag()
        policy = JudgementPolicy(
            version=body.policy_version,
            require_approval_for=list(body.require_approval_for),
            thresholds=[
                JudgementThreshold.model_validate(t) for t in body.thresholds
            ],
        )
        signals = [NoulSignal.model_validate(s) for s in body.signals]
        bag.put(
            WalkBagRegister.IN,
            {
                "action": body.action,
                "action_digest": body.action_digest,
                "policy_version": body.policy_version,
            },
        )
        ask = decide(
            JudgementFacts(
                action=body.action,
                action_digest=body.action_digest,
            ),
            signals,
            policy,
        )
        bag.put(WalkBagRegister.ASK, ask.model_dump(mode="json"))
        requested = ask.kind == "ASK_HUMAN"
        if not requested:
            bag.put(WalkBagRegister.ERR, {"reason": "human_review_not_requested"})
            return {
                "human_review_requested": False,
                "kind": "completed",
                "verdict_kinds": [ask.kind],
                "ask_reason_codes": list(ask.reason_codes),
                "bag": bag.snapshot(),
            }
        if body.inject is None:
            return {
                "human_review_requested": True,
                "kind": "human_review_requested",
                "verdict_kinds": [ask.kind],
                "ask_reason_codes": list(ask.reason_codes),
                "bag": bag.snapshot(),
            }
        approvals = body.inject.get("approvals")
        if not isinstance(approvals, dict):
            raise ValueError(
                "human_review inject requires approvals: {digest: approval_id}"
            )
        bag.put(WalkBagRegister.ANS, dict(body.inject))
        allow = decide(
            JudgementFacts(
                action=body.action,
                action_digest=body.action_digest,
                approvals={str(k): str(v) for k, v in approvals.items()},
            ),
            signals,
            policy,
        )
        bag.put(WalkBagRegister.OUT, allow.model_dump(mode="json"))
        bag.put(WalkBagRegister.ACC, {"verdict_kinds": [ask.kind, allow.kind]})
        return {
            "human_review_requested": True,
            "kind": "completed",
            "verdict_kinds": [ask.kind, allow.kind],
            "ask_reason_codes": list(ask.reason_codes),
            "final_verdict": allow.kind,
            "bag": bag.snapshot(),
        }


class AuthorityGateCommand(BaseModel):
    """Evaluate composed AuthorityGate scenarios (access + consequence + …)."""

    model_config = ConfigDict(extra="forbid")

    now: str
    access_grants: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    scenarios: list[dict[str, Any]] = Field(default_factory=list)


class AuthorityGateVerb(CliVerb):
    name = "authority_gate"
    params_model = AuthorityGateCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.authority_gate import AuthorityGate
        from mechaharness.consequence import ActionConsequence, ConsequencePolicy
        from mechaharness.core.access import AccessPolicy, InMemoryAccessControl
        from mechaharness.core.events import InMemoryEventLog
        from mechaharness.iso_timestamp import parse_iso_timestamp
        from mechaharness.judgement_policy import Verdict

        body = AuthorityGateCommand.model_validate(params.model_dump())
        now = parse_iso_timestamp(body.now)
        gate = AuthorityGate(
            access=InMemoryAccessControl(
                InMemoryEventLog(), AccessPolicy(grants=list(body.access_grants))
            ),
            consequence=ConsequencePolicy(
                actions=[ActionConsequence.model_validate(a) for a in body.actions]
            ),
        )
        decisions: dict[str, str] = {}
        for scenario in body.scenarios:
            kwargs = dict(scenario["evaluate"])
            if "envelope" in kwargs:
                kwargs["envelope"] = CapabilityEnvelope.model_validate(
                    kwargs["envelope"]
                )
            if "verdict" in kwargs:
                kwargs["verdict"] = Verdict.model_validate(kwargs["verdict"])
            decision = gate.evaluate(now=now, **kwargs)
            decisions[scenario["id"]] = ":".join(
                [decision.outcome, *decision.reason_codes]
            )
        return {"decisions": decisions}


class ExecutionTokenCommand(BaseModel):
    """Attenuate CapabilityEnvelope token fields across narrow attempts."""

    model_config = ConfigDict(extra="forbid")

    parent: dict[str, Any]
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    inherit_attempt: str | None = None


class ExecutionTokenVerb(CliVerb):
    name = "execution_token"
    params_model = ExecutionTokenCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = ExecutionTokenCommand.model_validate(params.model_dump())
        bag = WalkBag()
        parent = CapabilityEnvelope.model_validate(body.parent)
        bag.put(WalkBagRegister.IN, body.parent)
        outcomes: dict[str, str] = {}
        children: dict[str, CapabilityEnvelope] = {}
        for attempt in body.attempts:
            attempt_id = str(attempt["id"])
            try:
                children[attempt_id] = parent.narrow(**dict(attempt["narrow"]))
                outcomes[attempt_id] = "ok"
            except ValueError as exc:
                reason = str(exc).removeprefix("child envelope ").split(":")[0]
                outcomes[attempt_id] = f"refused:{reason}"
        inherited = children.get(str(body.inherit_attempt or ""))
        out = {
            "outcomes": outcomes,
            "refused_ids": sorted(
                k for k, v in outcomes.items() if v.startswith("refused")
            ),
            "accepted_ids": sorted(k for k, v in outcomes.items() if v == "ok"),
            "inherited_principal": inherited.principal if inherited else None,
            "inherited_epoch": inherited.authorization_epoch if inherited else None,
        }
        bag.put(WalkBagRegister.OUT, out)
        return {**out, "bag": bag.snapshot()}


class DenialEquivalenceCommand(BaseModel):
    """Persist a denial and block equivalent actions until lift()."""

    model_config = ConfigDict(extra="forbid")

    denied: dict[str, Any]
    retries: list[dict[str, Any]] = Field(default_factory=list)


class DenialEquivalenceVerb(CliVerb):
    name = "denial_equivalence"
    params_model = DenialEquivalenceCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.authority_gate import AuthorityGate
        from mechaharness.denial_store import InMemoryDenialStore, equivalent_action_digest
        from mechaharness.judgement_policy import Verdict
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = DenialEquivalenceCommand.model_validate(params.model_dump())
        bag = WalkBag()
        bag.put(WalkBagRegister.IN, {"denied": body.denied, "retries": body.retries})
        store = InMemoryDenialStore()
        gate = AuthorityGate(denials=store)
        denied = body.denied
        first_digest = equivalent_action_digest(
            denied["effect_class"], denied["target"]
        )
        first = gate.evaluate(
            action=denied["effect_class"],
            verdict=Verdict(
                kind="DENY",
                reason_codes=["user_denied"],
                policy_version="1",
            ),
            action_digest=first_digest,
            tool_name=denied["tool_name"],
        )
        retries: dict[str, str] = {}
        for retry in body.retries:
            digest = equivalent_action_digest(retry["effect_class"], retry["target"])
            decision = gate.evaluate(
                action=retry["effect_class"],
                approved=True,
                action_digest=digest,
                tool_name=retry["tool_name"],
            )
            retries[retry["id"]] = ":".join(
                [decision.outcome, *decision.reason_codes]
            )
        lifted = store.lift(first_digest)
        after_lift = gate.evaluate(
            action=denied["effect_class"],
            approved=True,
            action_digest=first_digest,
        )
        out = {
            "first": ":".join([first.outcome, *first.reason_codes]),
            "retries": retries,
            "lifted": lifted,
            "after_lift": after_lift.outcome,
        }
        bag.put(WalkBagRegister.OUT, out)
        return {**out, "bag": bag.snapshot()}


class AlertEscalationCommand(BaseModel):
    """Map occurrence counts to log / surface / propose stages."""

    model_config = ConfigDict(extra="forbid")

    policy: dict[str, Any]
    alert: str
    counts: list[int] = Field(default_factory=list)
    override_alert: str
    override_counts: list[int] = Field(default_factory=list)
    unordered_policy: dict[str, Any]


class AlertEscalationVerb(CliVerb):
    name = "alert_escalation"
    params_model = AlertEscalationCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.alert_escalation import (
            AlertEscalationPolicy,
            AlertOccurrenceCounter,
        )
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = AlertEscalationCommand.model_validate(params.model_dump())
        bag = WalkBag()
        bag.put(WalkBagRegister.IN, body.model_dump())
        policy = AlertEscalationPolicy.model_validate(body.policy)
        counter = AlertOccurrenceCounter(policy)
        try:
            AlertEscalationPolicy.model_validate(body.unordered_policy)
            unordered_refused = False
        except ValueError:
            unordered_refused = True
        out = {
            "ladder": [policy.evaluate(body.alert, n) for n in body.counts],
            "override_ladder": [
                policy.evaluate(body.override_alert, n) for n in body.override_counts
            ],
            "counter_walk": [counter.record(body.alert) for _ in body.counts],
            "unordered_refused": unordered_refused,
        }
        bag.put(WalkBagRegister.OUT, out)
        return {**out, "bag": bag.snapshot()}


class ToolResultFreshnessCommand(BaseModel):
    """Reject stale ToolResult evidence before a decision."""

    model_config = ConfigDict(extra="forbid")

    now: str
    policy: dict[str, Any] = Field(default_factory=dict)
    results: list[dict[str, Any]] = Field(default_factory=list)


class ToolResultFreshnessVerb(CliVerb):
    name = "tool_result_freshness"
    params_model = ToolResultFreshnessCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.core.types import ToolResult
        from mechaharness.iso_timestamp import parse_iso_timestamp
        from mechaharness.tool_result_freshness import ToolResultFreshnessPolicy
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = ToolResultFreshnessCommand.model_validate(params.model_dump())
        bag = WalkBag()
        bag.put(WalkBagRegister.IN, {"now": body.now, "policy": body.policy})
        now = parse_iso_timestamp(body.now)
        policy = ToolResultFreshnessPolicy(**body.policy)
        rejected: list[str] = []
        passed: list[str] = []
        for raw in body.results:
            result = ToolResult.model_validate(raw)
            checked = policy.reject_if_stale(result, now=now)
            (
                rejected if checked.is_error and not result.is_error else passed
            ).append(result.tool_call_id)
        out = {"rejected_ids": rejected, "passed_ids": passed}
        bag.put(WalkBagRegister.OUT, out)
        return {**out, "bag": bag.snapshot()}


class ToolPhaseGuardCommand(BaseModel):
    """Refuse observe/prepare contracts that smuggle write/external effects."""

    model_config = ConfigDict(extra="forbid")

    contracts: list[dict[str, Any]] = Field(default_factory=list)
    alias_probe: str = ""


class ToolPhaseGuardVerb(CliVerb):
    name = "tool_phase_guard"
    params_model = ToolPhaseGuardCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from mechaharness.operation_registry import OperationContract, OperationRegistry
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = ToolPhaseGuardCommand.model_validate(params.model_dump())
        bag = WalkBag()
        bag.put(WalkBagRegister.IN, {"contracts": body.contracts})
        registry = OperationRegistry()
        registered: list[str] = []
        refused: list[str] = []
        for raw in body.contracts:
            contract = OperationContract.model_validate(raw)
            try:
                registry.register(contract.name, lambda **_: None, contract=contract)
                registered.append(contract.name)
            except ValueError:
                refused.append(contract.name)
        out = {
            "registered": registered,
            "refused": refused,
            "alias_supported": registry.supports(body.alias_probe),
        }
        bag.put(WalkBagRegister.OUT, out)
        return {**out, "bag": bag.snapshot()}


class LocalPlanResumeCommand(BaseModel):
    """Crash-resume a local plan that requires a VFS file.

    First walk fails when ``required_path`` is missing. The verb seeds the
    shared :class:`~pyiv.files.Filesystem`, re-arms the failed node, and
    resumes the same ``run_id`` (stashed on walk-bag ``ctx``).
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = "cli:local-plan"
    required_path: str = "/work/input.txt"
    seed_content: str = "plan-payload"
    goal: str = "consume required input file"


class LocalPlanResumeVerb(CliVerb):
    name = "local_plan_resume"
    params_model = LocalPlanResumeCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        from pyiv.files import Filesystem, MemoryFilesystem

        from mechaharness.budget import BudgetPolicy
        from mechaharness.di import MechaHarnessConfig, get_injector
        from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
        from mechaharness.graph_executor import (
            CallableGraphNodeRunner,
            GraphExecutor,
            GraphFailureAction,
            GraphFailurePolicy,
            GraphNodeRunnerRegistry,
            NodeOutcome,
        )
        from mechaharness.harness.pass_through import PassThroughHarness
        from mechaharness.inference.mock import MockInferenceStrategy
        from mechaharness.walk_bag import WalkBag, WalkBagRegister

        body = LocalPlanResumeCommand.model_validate(params.model_dump())
        bag = WalkBag()
        bag.put(
            WalkBagRegister.IN,
            {
                "required_path": body.required_path,
                "seed_content": body.seed_content,
            },
        )
        bag.put(WalkBagRegister.CTX, {"run_id": body.run_id})
        fs = MemoryFilesystem()  # type: ignore[no-untyped-call]

        class _FailClosedPolicy(GraphFailurePolicy):
            """Retry while attempts remain; then fail (no escalate)."""

            def decide(
                self, node: GraphNode, *, error: str | None
            ) -> GraphFailureAction:
                del error
                if node.attempt < node.max_attempts:
                    return GraphFailureAction.RETRY
                return GraphFailureAction.FAIL

        async def require_file(
            node: GraphNode, context: GraphRunContext
        ) -> NodeOutcome:
            path = str(node.payload.get("path") or body.required_path)
            if not fs.exists(path):
                return NodeOutcome(
                    status=NodeStatus.FAILED,
                    error=f"missing_file:{path}",
                )
            content = fs.read_text(path)
            context.bag.put(
                WalkBagRegister.OUT, {"path": path, "content": content}
            )
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"path": path, "content": content},
            )

        registry = GraphNodeRunnerRegistry(
            [CallableGraphNodeRunner(["require_file"], require_file)]
        )

        class Cfg(MechaHarnessConfig):
            def get_inference_class(self) -> type[InferenceStrategy]:
                return MockInferenceStrategy

            def get_harness_class(self) -> type[AbstractHarness]:
                return PassThroughHarness

            def get_grants(self) -> list[object]:
                return [GraphExecute]

            def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
                return registry

            def get_filesystem(self) -> Filesystem:
                return fs

            def get_graph_failure_policy(self) -> GraphFailurePolicy:
                return _FailClosedPolicy()

        executor = get_injector(Cfg()).inject(GraphExecutor)
        graph = ExecutionGraph(goal=body.goal, version="1")
        graph.add_node(
            GraphNode(
                id="require_input",
                kind="require_file",
                payload={"path": body.required_path},
                max_attempts=1,
            )
        )

        first = await executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id=body.run_id,
            skip_linkage=True,
        )
        first_error = first.error or ""
        require = first.graph.nodes.get("require_input")
        if require is not None and require.error:
            first_error = require.error
        bag.put(
            WalkBagRegister.ERR,
            {"first_status": first.status, "error": first_error},
        )

        fs.write_text(body.required_path, body.seed_content)
        bag.put(
            WalkBagRegister.ANS,
            {"seeded_path": body.required_path, "content": body.seed_content},
        )

        # Re-arm the failed require node so resume can consume the seeded file.
        restored = executor.store.latest(run_id=body.run_id)
        assert restored is not None
        node = restored.nodes["require_input"]
        node.status = NodeStatus.PENDING
        node.error = None
        node.max_attempts = max(node.attempt + 1, 2)
        executor.store.save(restored, run_id=body.run_id, boundary="dispatch")

        resumed = await executor.run(
            restored,
            budget_policy=BudgetPolicy.unlimited(),
            run_id=body.run_id,
            resume=True,
            skip_linkage=True,
        )
        out_payload = resumed.graph.nodes["require_input"].payload
        bag.put(WalkBagRegister.OUT, dict(out_payload))
        bag.put(WalkBagRegister.ACC, {"resume_status": resumed.status})
        return {
            "run_id": body.run_id,
            "first_status": first.status,
            "first_error": first_error,
            "resume_status": resumed.status,
            "file_content": out_payload.get("content"),
            "required_path": body.required_path,
            "recovery_boundary": executor.store.latest_boundary(run_id=body.run_id),
            "bag": bag.snapshot(),
            "status": resumed.status,
            "error": resumed.error,
        }


class LanePublishCommand(BaseModel):
    """Append/open a lane run and put keys onto its WalkBag."""

    model_config = ConfigDict(extra="forbid")

    caller_lane: str
    run_id: str
    keys: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class LanePublishVerb(CliVerb):
    name = "lane_publish"
    params_model = LanePublishCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        from mechaharness.iso_timestamp import parse_iso_timestamp
        from mechaharness.job_lane_broker import JobLaneBroker
        from mechaharness.walk_bag import FileArtifact

        body = LanePublishCommand.model_validate(params.model_dump())
        broker = getattr(runtime, "job_lane_broker", None)
        if broker is None:
            raise RuntimeError(
                "lane_publish requires JobLaneBroker on the instrumentor "
                "(bind via Config get_job_lane_broker / environment.job_lanes)"
            )
        assert isinstance(broker, JobLaneBroker)
        started = parse_iso_timestamp(body.started_at) if body.started_at else None
        if started is None and body.started_at:
            raise ValueError(f"invalid started_at {body.started_at!r}")
        if started is None:
            started = runtime.datetime_service.now_utc()
        bag = broker.open_run(
            body.caller_lane,
            body.run_id,
            started_at=started,
            meta=body.meta or None,
        )
        published: dict[str, Any] = {}
        for key, raw in body.keys.items():
            value: Any = raw
            if isinstance(raw, dict) and ("url" in raw or "path" in raw):
                value = FileArtifact.model_validate(raw)
            broker.put(body.caller_lane, body.run_id, key, value)
            published[key] = (
                value.model_dump(exclude_none=True)
                if isinstance(value, FileArtifact)
                else value
            )
        return {
            "status": "ok",
            "lane": body.caller_lane,
            "run_id": body.run_id,
            "keys": sorted(published),
            "published": published,
            "bag": bag.snapshot(),
        }


class LaneObserveCommand(BaseModel):
    """Brokered observe of another (or same) lane run key/meta."""

    model_config = ConfigDict(extra="forbid")

    caller_lane: str
    target_lane: str
    selector: dict[str, Any]
    key: str | None = None
    meta: bool = False


class LaneObserveVerb(CliVerb):
    name = "lane_observe"
    params_model = LaneObserveCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        from mechaharness.job_lane_broker import JobLaneBroker, ObserveSelector

        body = LaneObserveCommand.model_validate(params.model_dump())
        broker = getattr(runtime, "job_lane_broker", None)
        if broker is None:
            raise RuntimeError(
                "lane_observe requires JobLaneBroker on the instrumentor "
                "(bind via Config get_job_lane_broker / environment.job_lanes)"
            )
        assert isinstance(broker, JobLaneBroker)
        result = broker.observe(
            body.caller_lane,
            body.target_lane,
            selector=ObserveSelector.model_validate(body.selector),
            key=body.key,
            meta=body.meta,
        )
        return result.model_dump(exclude_none=True)


class LaneGrantCommand(BaseModel):
    """Standing grant: caller lane may observe publisher keys/meta."""

    model_config = ConfigDict(extra="forbid")

    from_lane: str
    to_lane: str
    keys: list[str] = Field(default_factory=list)
    meta: bool = False


class LaneGrantVerb(CliVerb):
    name = "lane_grant"
    params_model = LaneGrantCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        from mechaharness.job_lane_broker import JobLaneBroker

        body = LaneGrantCommand.model_validate(params.model_dump())
        broker = getattr(runtime, "job_lane_broker", None)
        if broker is None:
            raise RuntimeError(
                "lane_grant requires JobLaneBroker on the instrumentor"
            )
        assert isinstance(broker, JobLaneBroker)
        broker.grant(
            from_lane=body.from_lane,
            to_lane=body.to_lane,
            keys=list(body.keys),
            meta=body.meta,
        )
        return {
            "status": "ok",
            "from_lane": body.from_lane,
            "to_lane": body.to_lane,
            "keys": list(body.keys),
            "meta": body.meta,
        }


class LaneHandoffCommand(BaseModel):
    """One-shot HandoffRecord share of evidence_refs across lanes."""

    model_config = ConfigDict(extra="forbid")

    from_lane: str
    to_lane: str
    evidence_refs: list[str] = Field(default_factory=list)
    handoff: dict[str, Any] | None = None


class LaneHandoffVerb(CliVerb):
    name = "lane_handoff"
    params_model = LaneHandoffCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        from mechaharness.handoff_record import HandoffRecord
        from mechaharness.job_lane_broker import IsolationViolation, JobLaneBroker

        body = LaneHandoffCommand.model_validate(params.model_dump())
        broker = getattr(runtime, "job_lane_broker", None)
        if broker is None:
            raise RuntimeError(
                "lane_handoff requires JobLaneBroker on the instrumentor"
            )
        assert isinstance(broker, JobLaneBroker)
        if body.handoff is not None:
            record = HandoffRecord.model_validate(body.handoff)
        else:
            record = HandoffRecord(evidence_refs=list(body.evidence_refs))
        try:
            broker.handoff(body.from_lane, body.to_lane, record)
        except IsolationViolation as exc:
            return {
                "status": "denied",
                "error": str(exc),
                "from_lane": body.from_lane,
                "to_lane": body.to_lane,
            }
        return {
            "status": "ok",
            "from_lane": body.from_lane,
            "to_lane": body.to_lane,
            "evidence_refs": list(record.evidence_refs),
        }


def _live_authorization_epoch_fn(epoch: int) -> Callable[[], int]:
    """Typed zero-arg epoch source for ``GraphExecutor.live_authorization_epoch``."""

    def _live() -> int:
        return epoch

    return _live


class GraphWalkCommand(BaseModel):
    """Stepped graph control: start / step / until / continue / set_live_epoch (SG-09)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["start", "step", "until", "continue", "set_live_epoch"] = "start"
    goal: str = "walk"
    run_id: str = "cli:graph-walk"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    until: str | None = None
    stop: Literal["before", "after"] = "before"
    live_authorization_epoch: int | None = None
    envelope_epoch: int | None = None
    grants: list[str] = Field(
        default_factory=lambda: ["core:graph.execute"]
    )


class GraphWalkVerb(CliVerb):
    name = "graph_walk"
    params_model = GraphWalkCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        from mechaharness.budget import BudgetPolicy
        from mechaharness.capability_envelope import CapabilityEnvelope
        from mechaharness.core.access import GraphExecute
        from mechaharness.di import MechaHarnessConfig, get_injector
        from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode, NodeStatus
        from mechaharness.graph_executor import (
            CallableGraphNodeRunner,
            GraphExecutor,
            GraphNodeRunnerRegistry,
            NodeOutcome,
            RunControl,
        )
        from mechaharness.harness.pass_through import PassThroughHarness
        from mechaharness.inference.mock import MockInferenceStrategy

        body = GraphWalkCommand.model_validate(params.model_dump())
        session = getattr(runtime, "graph_walk_session", None)

        if body.action == "set_live_epoch":
            if session is None:
                raise RuntimeError("graph_walk set_live_epoch needs an active session")
            if body.live_authorization_epoch is None:
                raise ValueError("set_live_epoch requires live_authorization_epoch")
            session["live_epoch"] = int(body.live_authorization_epoch)
            executor = session["executor"]
            assert isinstance(executor, GraphExecutor)
            epoch = int(session["live_epoch"])
            executor.live_authorization_epoch = _live_authorization_epoch_fn(epoch)
            return {
                "status": "ok",
                "action": "set_live_epoch",
                "live_authorization_epoch": epoch,
            }

        def _node_statuses(graph: ExecutionGraph) -> dict[str, str]:
            return {nid: n.status.value for nid, n in graph.nodes.items()}

        def _bag_observation(graph: ExecutionGraph) -> dict[str, Any]:
            return dict(graph.walk_bag or {})

        def _model_inputs_observation(*runners: Any) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for runner in runners:
                if runner is None:
                    continue
                out.update(dict(getattr(runner, "last_model_inputs", {}) or {}))
            return out

        def _inference_observation(*runners: Any) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for runner in runners:
                if runner is None:
                    continue
                out.update(dict(getattr(runner, "last_inference", {}) or {}))
            return out

        def _completion_scripts(nodes: list[dict[str, Any]]) -> dict[str, str]:
            out: dict[str, str] = {}
            for raw in nodes:
                payload = raw.get("payload")
                if not isinstance(payload, dict) or "completion" not in payload:
                    continue
                value = payload["completion"]
                if isinstance(value, (dict, list)):
                    out[str(raw["id"])] = json.dumps(value, sort_keys=True)
                else:
                    out[str(raw["id"])] = str(value)
            return out

        def _completion_turns(
            nodes: list[dict[str, Any]],
        ) -> dict[str, list[dict[str, Any]]]:
            out: dict[str, list[dict[str, Any]]] = {}
            for raw in nodes:
                payload = raw.get("payload")
                if not isinstance(payload, dict):
                    continue
                turns = payload.get("completion_turns")
                if isinstance(turns, list) and turns:
                    out[str(raw["id"])] = [dict(item) for item in turns]
            return out

        if body.action == "start":
            nodes_spec = list(body.nodes)
            inline = getattr(runtime, "inline_graph", None)
            if not nodes_spec and isinstance(inline, dict):
                nodes_spec = list(inline.get("nodes") or [])
                if not body.goal or body.goal == "walk":
                    body = body.model_copy(
                        update={"goal": str(inline.get("goal") or body.goal)}
                    )
                if not body.edges:
                    body = body.model_copy(
                        update={"edges": list(inline.get("edges") or [])}
                    )
            if not nodes_spec:
                raise ValueError("graph_walk start requires nodes or graph.inline")

            calls: list[str] = []

            async def run_node(node: GraphNode, context: Any) -> NodeOutcome:
                calls.append(node.id)
                puts = node.payload.get("bag_put")
                if isinstance(puts, dict):
                    for key, value in puts.items():
                        key_s = str(key)
                        if "." in key_s:
                            context.bag.path_put(key_s, value)
                        else:
                            context.bag.put(key_s, value)
                req = node.payload.get("bag_require")
                if req is not None:
                    req_s = str(req)
                    try:
                        if "." in req_s:
                            context.bag.path_require(req_s)
                        else:
                            context.bag.require(req_s)
                    except KeyError as exc:
                        return NodeOutcome(
                            status=NodeStatus.FAILED,
                            error=str(exc),
                        )
                return NodeOutcome(status=NodeStatus.SUCCEEDED)

            from mechaharness.cli_infer_runner import (
                DEFAULT_INFER_KINDS,
                CliInferRunner,
                NodeScriptedCompleter,
            )
            from mechaharness.cli_judge_runner import (
                DEFAULT_JUDGE_KINDS,
                CliJudgeRunner,
            )
            from mechaharness.core.access import InMemoryCostAccountant
            from mechaharness.core.completer import Completer
            from mechaharness.core.events import EventLog

            kinds = sorted({str(n.get("kind") or "compute") for n in nodes_spec})
            # Subgraph kind is handled by the executor; still register leaf kinds.
            infer_kind_set = set(DEFAULT_INFER_KINDS)
            judge_kind_set = set(DEFAULT_JUDGE_KINDS)
            special_kinds = infer_kind_set | judge_kind_set
            leaf_kinds = [k for k in kinds if k != "subgraph"]
            compute_kinds = [k for k in leaf_kinds if k not in special_kinds]
            needs_infer = any(k in infer_kind_set for k in leaf_kinds)
            needs_judge = any(k in judge_kind_set for k in leaf_kinds)

            scripts = _completion_scripts(nodes_spec)
            turns = _completion_turns(nodes_spec)
            infer_runner: CliInferRunner | None = None
            judge_runner: CliJudgeRunner | None = None
            runners: list[Any] = []
            if compute_kinds or not (needs_infer or needs_judge):
                runners.append(
                    CallableGraphNodeRunner(compute_kinds or ["compute"], run_node)
                )

            # Bind Completer / EventLog first so runners are in the registry
            # snapshot when Config.configure registers GraphNodeRunnerRegistry.
            class _ServicesCfg(MechaHarnessConfig):
                def get_inference_class(self) -> type[InferenceStrategy]:
                    return MockInferenceStrategy

                def get_harness_class(self) -> type[AbstractHarness]:
                    return PassThroughHarness

                def get_grants(self) -> list[object]:
                    return [GraphExecute, *list(body.grants)]

            services = get_injector(_ServicesCfg())
            if needs_infer or needs_judge:
                base_completer = services.inject(Completer)
                host_completer = getattr(runtime, "completer", None)
                if isinstance(host_completer, Completer):
                    base_completer = host_completer
                completer: Completer = base_completer
                # Scripted replies are for static/mock doubles only. Live
                # OpenAI-compat / Anthropic Completers must see the compiled
                # ContextSpec request (payload.completion is ignored).
                from mechaharness.inference.anthropic import AnthropicStrategy
                from mechaharness.inference.openai_compat import OpenAICompatStrategy

                if (scripts or turns) and not isinstance(
                    base_completer, (OpenAICompatStrategy, AnthropicStrategy)
                ):
                    completer = NodeScriptedCompleter(
                        scripts, base_completer, turns=turns
                    )
                event_log = services.inject(EventLog)
                host_log = getattr(runtime, "event_log", None)
                if host_log is not None:
                    event_log = host_log
                cost = InMemoryCostAccountant(event_log)
                host_model = getattr(runtime, "model", None)
                shared_priors: dict[str, Any] = {}
                if needs_infer:
                    infer_runner = CliInferRunner(
                        completer,
                        cost,
                        event_log,
                        model=str(host_model or "cli-default"),
                        kinds=list(DEFAULT_INFER_KINDS),
                    )
                    infer_runner.prior_responses = shared_priors
                    runners.append(infer_runner)
                if needs_judge:
                    judge_runner = CliJudgeRunner(
                        completer,
                        cost,
                        event_log,
                        model=str(host_model or "cli-judge"),
                        kinds=list(DEFAULT_JUDGE_KINDS),
                        prior_responses=shared_priors,
                    )
                    runners.append(judge_runner)

            class Cfg(MechaHarnessConfig):
                def get_inference_class(self) -> type[InferenceStrategy]:
                    return MockInferenceStrategy

                def get_harness_class(self) -> type[AbstractHarness]:
                    return PassThroughHarness

                def get_grants(self) -> list[object]:
                    return [GraphExecute, *list(body.grants)]

                def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
                    return GraphNodeRunnerRegistry(list(runners))

            executor = get_injector(Cfg()).inject(GraphExecutor)
            live = body.live_authorization_epoch
            if live is None and runtime.capability_envelope is not None:
                live = runtime.capability_envelope.authorization_epoch
            if live is not None:
                executor.live_authorization_epoch = _live_authorization_epoch_fn(
                    int(live)
                )

            graph = ExecutionGraph(goal=body.goal)
            for raw in nodes_spec:
                node = GraphNode(
                    id=str(raw["id"]),
                    kind=str(raw.get("kind") or "compute"),
                    depends_on=list(raw.get("depends_on") or []),
                    payload=dict(raw.get("payload") or {}),
                    subgraph=raw.get("subgraph"),
                )
                graph.add_node(node)
            for raw in body.edges:
                graph.add_dependency(
                    DependencyEdge(
                        from_node=str(raw["from"]),
                        to_node=str(raw["to"]),
                        types=list(raw.get("types") or ["control"]),
                        reason=str(raw.get("reason") or "graph_walk"),
                    )
                )

            env_epoch = body.envelope_epoch
            if env_epoch is None:
                env_epoch = live if live is not None else 0
            envelope = CapabilityEnvelope(
                grants=list(body.grants),
                authorization_epoch=int(env_epoch),
            )

            if body.until:
                control = RunControl(
                    mode="until", until=body.until, stop=body.stop
                )
            else:
                # Bare start binds the session and advances one frontier step
                # (stories that need to_completion use action=continue next).
                control = RunControl(mode="one_step")

            session = {
                "executor": executor,
                "graph": graph,
                "run_id": body.run_id,
                "envelope": envelope,
                "calls": calls,
                "live_epoch": live,
                "infer_runner": infer_runner,
                "judge_runner": judge_runner,
            }
            runtime.graph_walk_session = session
            result = await executor.run(
                graph,
                budget_policy=BudgetPolicy.unlimited(),
                run_id=body.run_id,
                envelope=envelope,
                skip_linkage=True,
                control=control,
            )
            session["graph"] = result.graph
            session["effect_calls"] = len(calls)
            node_error = ""
            for node in result.graph.nodes.values():
                if node.error:
                    node_error = node.error
                    break
            return {
                "status": result.status,
                "action": "start",
                "run_id": result.run_id,
                "stopped_before": result.stopped_before,
                "entered_node_id": result.entered_node_id,
                "active_run_id": result.active_run_id,
                "node_statuses": _node_statuses(result.graph),
                "effect_calls": len(calls),
                "node_error": node_error,
                "error": result.error,
                "bag": _bag_observation(result.graph),
                "model_inputs": _model_inputs_observation(infer_runner, judge_runner),
                "inference": _inference_observation(infer_runner, judge_runner),
            }

        if session is None:
            raise RuntimeError(f"graph_walk {body.action} needs an active session")

        executor = session["executor"]
        assert isinstance(executor, GraphExecutor)
        graph = session["graph"]
        envelope = session["envelope"]
        calls = session["calls"]
        assert isinstance(graph, ExecutionGraph)
        assert isinstance(envelope, CapabilityEnvelope)

        if body.live_authorization_epoch is not None:
            session["live_epoch"] = int(body.live_authorization_epoch)
            epoch = int(session["live_epoch"])
            executor.live_authorization_epoch = _live_authorization_epoch_fn(epoch)

        if body.action == "step":
            control = RunControl(mode="one_step")
        elif body.action == "until":
            if not body.until:
                raise ValueError("graph_walk until requires until=node_id")
            control = RunControl(mode="until", until=body.until, stop=body.stop)
        else:  # continue
            control = RunControl()
            if body.until:
                control = RunControl(
                    mode="until", until=body.until, stop=body.stop
                )

        before_calls = len(calls)
        result = await executor.run(
            graph,
            budget_policy=BudgetPolicy.unlimited(),
            run_id=session["run_id"],
            resume=True,
            envelope=envelope,
            skip_linkage=True,
            control=control,
        )
        session["graph"] = result.graph
        session["effect_calls"] = len(calls)
        node_error = ""
        for node in result.graph.nodes.values():
            if node.error:
                node_error = node.error
                break
        return {
            "status": result.status,
            "action": body.action,
            "run_id": result.run_id,
            "stopped_before": result.stopped_before,
            "entered_node_id": result.entered_node_id,
            "active_run_id": result.active_run_id,
            "node_statuses": _node_statuses(result.graph),
            "effect_calls": len(calls),
            "step_effect_calls": len(calls) - before_calls,
            "node_error": node_error,
            "error": result.error,
            "bag": _bag_observation(result.graph),
            "model_inputs": _model_inputs_observation(
                session.get("infer_runner"), session.get("judge_runner")
            ),
            "inference": _inference_observation(
                session.get("infer_runner"), session.get("judge_runner")
            ),
        }


def policy_cli_verb_classes() -> dict[str, type[CliVerb]]:
    return {
        AccessCheckVerb.name: AccessCheckVerb,
        CapabilityEnvelopeVerb.name: CapabilityEnvelopeVerb,
        RunBudgetedGraphVerb.name: RunBudgetedGraphVerb,
        AuthEpochResumeVerb.name: AuthEpochResumeVerb,
        ApprovalInterruptVerb.name: ApprovalInterruptVerb,
        HumanReviewGateVerb.name: HumanReviewGateVerb,
        AuthorityGateVerb.name: AuthorityGateVerb,
        ExecutionTokenVerb.name: ExecutionTokenVerb,
        DenialEquivalenceVerb.name: DenialEquivalenceVerb,
        AlertEscalationVerb.name: AlertEscalationVerb,
        ToolResultFreshnessVerb.name: ToolResultFreshnessVerb,
        ToolPhaseGuardVerb.name: ToolPhaseGuardVerb,
        LocalPlanResumeVerb.name: LocalPlanResumeVerb,
        LanePublishVerb.name: LanePublishVerb,
        LaneObserveVerb.name: LaneObserveVerb,
        LaneGrantVerb.name: LaneGrantVerb,
        LaneHandoffVerb.name: LaneHandoffVerb,
        GraphWalkVerb.name: GraphWalkVerb,
    }


__all__ = [
    "AccessCheckCommand",
    "AccessCheckVerb",
    "AlertEscalationCommand",
    "AlertEscalationVerb",
    "ApprovalInterruptCommand",
    "ApprovalInterruptVerb",
    "AuthEpochResumeCommand",
    "AuthEpochResumeVerb",
    "AuthorityGateCommand",
    "AuthorityGateVerb",
    "CapabilityEnvelopeCommand",
    "CapabilityEnvelopeVerb",
    "DenialEquivalenceCommand",
    "DenialEquivalenceVerb",
    "ExecutionTokenCommand",
    "ExecutionTokenVerb",
    "HumanReviewGateCommand",
    "HumanReviewGateVerb",
    "LaneGrantCommand",
    "LaneGrantVerb",
    "LaneHandoffCommand",
    "LaneHandoffVerb",
    "LaneObserveCommand",
    "LaneObserveVerb",
    "GraphWalkCommand",
    "GraphWalkVerb",
    "LanePublishCommand",
    "LanePublishVerb",
    "LocalPlanResumeCommand",
    "LocalPlanResumeVerb",
    "RunBudgetedGraphCommand",
    "RunBudgetedGraphVerb",
    "ToolPhaseGuardCommand",
    "ToolPhaseGuardVerb",
    "ToolResultFreshnessCommand",
    "ToolResultFreshnessVerb",
    "policy_cli_verb_classes",
]
