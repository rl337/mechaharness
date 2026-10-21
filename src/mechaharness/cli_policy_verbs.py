"""Product verbs for host authorization and budget surfaces.

These are thin CLI façades over Config-injected ``AccessControl`` /
``CapabilityEnvelope`` and ``GraphExecutor`` budget enforcement — not probe
case bags. See ``docs/reference/access.md`` and ``docs/reference/budget.md``.
"""

from __future__ import annotations

from typing import Any

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
    "RunBudgetedGraphCommand",
    "RunBudgetedGraphVerb",
    "ToolPhaseGuardCommand",
    "ToolPhaseGuardVerb",
    "ToolResultFreshnessCommand",
    "ToolResultFreshnessVerb",
    "policy_cli_verb_classes",
]
