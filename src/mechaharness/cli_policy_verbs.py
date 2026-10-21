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


def policy_cli_verb_classes() -> dict[str, type[CliVerb]]:
    return {
        AccessCheckVerb.name: AccessCheckVerb,
        CapabilityEnvelopeVerb.name: CapabilityEnvelopeVerb,
        RunBudgetedGraphVerb.name: RunBudgetedGraphVerb,
        AuthEpochResumeVerb.name: AuthEpochResumeVerb,
        ApprovalInterruptVerb.name: ApprovalInterruptVerb,
        AuthorityGateVerb.name: AuthorityGateVerb,
    }


__all__ = [
    "AccessCheckCommand",
    "AccessCheckVerb",
    "ApprovalInterruptCommand",
    "ApprovalInterruptVerb",
    "AuthEpochResumeCommand",
    "AuthEpochResumeVerb",
    "AuthorityGateCommand",
    "AuthorityGateVerb",
    "CapabilityEnvelopeCommand",
    "CapabilityEnvelopeVerb",
    "RunBudgetedGraphCommand",
    "RunBudgetedGraphVerb",
    "policy_cli_verb_classes",
]
