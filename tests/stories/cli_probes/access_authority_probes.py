"""CLI probes for former ``access_authority`` stories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.approval_interrupt import resume_approval, suspend_for_approval
from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.cli_verb import CliProbe
from mechaharness.consequence import ActionConsequence, ConsequencePolicy
from mechaharness.core.access import (
    Ability,
    AccessControl,
    AccessPolicy,
    CompoundPolicy,
    FsWrite,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.environment import (
    InferenceEnvironment,
    InferenceEnvironmentError,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, ToolCall, ToolResult
from mechaharness.decision_log import (
    DecisionRecord,
)
from mechaharness.delegation_policy import DefaultDelegationPolicy, DelegationRequest
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    NodeStatus,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_state_governance import (
    FieldGovernance,
    GraphStateGovernance,
    authorize_write,
)
from mechaharness.handoff_record import HandoffRecord
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.isolation.isolation_contract import IsolationContract, TemplateIOContract
from mechaharness.isolation.workspace_isolation import (
    InMemoryWorkspaceIsolationProvider,
    WorkspaceIsolationRequest,
)
from mechaharness.operation_registry import (
    OperationContract,
    OperationRegistry,
)
from mechaharness.tool_result_freshness import ToolResultFreshnessPolicy
from mechaharness.tools.base import ToolRegistry
from mechaharness.trace_envelope import TraceEnvelope, envelope_complete
from tests.fakes import ScriptedInference
from tests.support.di import make_harness


class _LaneEnvironment(InferenceEnvironment):
    """Story double: real lane checks (unlike NoOpInferenceEnvironment)."""

    def __init__(self, lane: str) -> None:
        self._lane = lane

    def active_profile(self) -> str | None:
        return f"story-{self._lane}"

    def active_capabilities(self):
        from mechaharness.core.access import CapabilityProfile

        return CapabilityProfile()

    def active_lane(self) -> str | None:
        return self._lane


async def run_wrong_lane_deny(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    env: InferenceEnvironment = _LaneEnvironment(request["active_lane"])
    raised: Exception | None = None
    try:
        env.assert_compatible(require_lane=request["require_lane"])
    except Exception as exc:  # noqa: BLE001 — type checked via expect
        raised = exc
    assert raised is not None, "expected InferenceEnvironmentError"
    assert isinstance(raised, InferenceEnvironmentError)
    return {
        "error_type": type(raised).__name__,
        "error_match": str(raised),
    }


async def run_grant_gate_write(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    response = inputs

    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    tool_calls = [
        ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for tc in response.get("tool_calls", [])
    ]

    def _script() -> ScriptedInference:
        return ScriptedInference(
            [
                ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=tool_calls),
                ChatMessage(role=Role.ASSISTANT, content="done"),
            ]
        )

    read_only = AccessPolicy(grants=request.get("read_grants", []))
    with_write = CompoundPolicy.of(
        read_only,
        AccessPolicy(grants=request.get("write_grants", [FsWrite])),
    )

    denied_log = InMemoryEventLog()
    denied = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=denied_log,
        access_policy=read_only,
    ).run(request.get("prompt", "write"))
    denied_ok = any("Permission denied" in (m.content or "") for m in denied.messages)

    allow_log = InMemoryEventLog()
    allowed = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=allow_log,
        access_policy=with_write,
    ).run(request.get("prompt", "write"))
    allowed_ok = allowed.final_text == "done"

    actual = {
        "denied_without_write_grant": denied_ok,
        "allowed_with_compound": allowed_ok,
    }
    return actual


async def run_config_access_policy(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    layers = [AccessPolicy(grants=layer) for layer in request["layers"]]
    compound = CompoundPolicy.of(*layers)

    class StoryConfig(MechaHarnessConfig):
        def __init__(self) -> None:
            self._inference = ScriptedInference([])
            super().__init__()  # type: ignore[no-untyped-call]

        def get_inference_class(self) -> type[InferenceStrategy]:
            return type(self._inference)

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_access_policy(self):
            return compound

        def configure(self) -> None:
            super().configure()
            self.register_instance(InferenceStrategy, self._inference)

    control = get_injector(StoryConfig()).inject(AccessControl)
    assert isinstance(control, InMemoryAccessControl)
    allows = all(control.allows([g]) for g in request["must_allow"])
    denies = all(not control.allows([g]) for g in request["must_deny"])
    actual = {"allows_compound": allows, "denies_missing": denies}
    return actual


async def run_tool_gating(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    response = inputs

    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    tool_calls = [
        ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for tc in response.get("tool_calls", [])
    ]

    def _script() -> ScriptedInference:
        return ScriptedInference(
            [
                ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=tool_calls),
                ChatMessage(role=Role.ASSISTANT, content="done"),
            ]
        )

    deny_policy = AccessPolicy(grants=request.get("deny_grants", []))
    allow_policy = AccessPolicy(grants=request.get("allow_grants", [FsWrite]))

    denied_log = InMemoryEventLog()
    denied = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=denied_log,
        access_policy=deny_policy,
    ).run(request.get("prompt", "write"))
    denied_ok = any("Permission denied" in (m.content or "") for m in denied.messages)

    allow_log = InMemoryEventLog()
    allowed = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=allow_log,
        access_policy=allow_policy,
    ).run(request.get("prompt", "write"))
    allowed_ok = allowed.final_text == "done"

    actual = {
        "denied_without_grant": denied_ok,
        "allowed_with_grant": allowed_ok,
    }
    return actual


async def run_capability_envelope_narrow(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    parent = CapabilityEnvelope(grants=list(request["parent_grants"]))
    child = parent.narrow(grants=list(request["child_grants"]))
    widen_raises = False
    try:
        parent.narrow(grants=list(request["widen_grants"]))
    except ValueError:
        widen_raises = True
    decision = DefaultDelegationPolicy().decide(
        DelegationRequest(independence_required=True, parent_envelope=parent)
    )
    actual = {
        "narrow_ok": set(child.grants).issubset(set(parent.grants)),
        "child_grant_count": len(child.grants),
        "widen_raises": widen_raises,
        "delegation_choice": decision.choice,
    }
    return actual


async def run_consequence_risk_scale(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    policy = ConsequencePolicy(
        actions=[
            ActionConsequence(
                action=str(request["action"]),
                consequence=request.get("consequence", "high"),
                requires_approval=True,
            )
        ]
    )
    policy.record_approval_prompt()
    policy.record_approval_decision()
    actual = {
        "requires_stronger_controls": policy.requires_stronger_controls(str(request["action"])),
        "approval_frequency": policy.approval_frequency(),
    }
    return actual


async def run_isolation_io_contract(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    iso = IsolationContract(
        effect_scope=str(request.get("effect_scope") or "none"),
        budget_share=float(request.get("budget_share") or 1.0),
    )
    io = TemplateIOContract(
        inputs=dict(request.get("inputs") or {}),
        outputs=dict(request.get("outputs") or {}),
        isolation=iso,
    )
    actual = {"issues": io.validation_issues(), "budget_share": iso.budget_share}
    return actual


async def run_approval_interrupt_cycle(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    pending = suspend_for_approval(
        reason=str(request.get("reason") or "approve"),
        suspended_checkpoint_ref=request.get("checkpoint"),
    )
    done = resume_approval(
        pending,
        decision=str(request.get("decision") or "approve"),
        actor=str(request.get("actor") or "actor"),
    )
    actual = {
        "initial_status": pending.status,
        "final_status": done.status,
        "actor_contains": done.actor_provenance or "",
    }
    return actual


async def run_workspace_isolation_acquire(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    provider = InMemoryWorkspaceIsolationProvider()
    handle = provider.acquire(WorkspaceIsolationRequest(label=str(request.get("label") or "x")))
    provider.release(handle)
    actual = {"provider_kind": handle.provider_kind, "released": True}
    return actual


async def run_state_governance_write(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs
    gov = GraphStateGovernance(
        fields={
            "quality_target": FieldGovernance(
                owner=str(request.get("owner") or "ops"),
                writers=list(request.get("writers") or []),
                mutable=bool(request.get("mutable")),
            )
        }
    )
    actual = {
        "allowed": authorize_write(
            gov, field="quality_target", actor=str(request.get("actor") or "agent")
        )
    }
    return actual


async def run_execution_token_narrow(inputs: dict[str, Any]) -> dict[str, Any]:
    """Child envelopes attenuate token fields and refuse widening (MH-DOTS-01)."""
    request = inputs
    parent = CapabilityEnvelope.model_validate(request["parent"])
    outcomes: dict[str, str] = {}
    children: dict[str, CapabilityEnvelope] = {}
    for attempt in request["attempts"]:
        try:
            children[attempt["id"]] = parent.narrow(**attempt["narrow"])
            outcomes[attempt["id"]] = "ok"
        except ValueError as exc:
            reason = str(exc).removeprefix("child envelope ").split(":")[0]
            outcomes[attempt["id"]] = f"refused:{reason}"
    inherited = children.get(str(request.get("inherit_attempt") or ""))
    actual = {
        "outcomes": outcomes,
        "refused_ids": sorted(k for k, v in outcomes.items() if v.startswith("refused")),
        "accepted_ids": sorted(k for k, v in outcomes.items() if v == "ok"),
        "inherited_principal": inherited.principal if inherited else None,
        "inherited_epoch": inherited.authorization_epoch if inherited else None,
    }
    return actual


async def run_tool_phase_effect_guard(inputs: dict[str, Any]) -> dict[str, Any]:
    """Observe/prepare tools cannot register write/external effects (MH-DOTS-03)."""
    request = inputs
    registry = OperationRegistry()
    registered: list[str] = []
    refused: list[str] = []
    for raw in request["contracts"]:
        contract = OperationContract.model_validate(raw)
        try:
            registry.register(contract.name, lambda **_: None, contract=contract)
            registered.append(contract.name)
        except ValueError:
            refused.append(contract.name)
    actual = {
        "registered": registered,
        "refused": refused,
        "alias_supported": registry.supports(str(request.get("alias_probe") or "")),
    }
    return actual


async def run_auth_epoch_resume_refuse(inputs: dict[str, Any]) -> dict[str, Any]:
    """Resume fails closed when the live authorization epoch differs (MH-DOTS-06)."""
    request = inputs
    calls: list[str] = []

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        calls.append(node.id)
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

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
    graph = ExecutionGraph(goal=str(request.get("goal") or "epoch"), version="1")
    graph.add_node(GraphNode(id="a", kind="compute"))

    def envelope(epoch: int) -> CapabilityEnvelope:
        return CapabilityEnvelope(
            grants=["core:graph.execute"], authorization_epoch=epoch
        )

    first = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="insp-epoch",
        envelope=envelope(int(request["first_epoch"])),
    )
    calls.clear()
    resumed = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="insp-epoch",
        resume=True,
        envelope=envelope(int(request["resume_epoch"])),
    )
    from tests.stories.cli_probes.graph_cost import with_graph_cost

    actual = with_graph_cost(
        {
            "first_status": first.status,
            "checkpoint_epoch": executor.store.latest_authorization_epoch(
                run_id="insp-epoch"
            ),
            "resume_status": resumed.status,
            "error_contains": resumed.error or "",
            "runner_calls_after_resume": len(calls),
        },
        first,
        resumed,
    )
    return actual


async def run_tool_result_freshness_reject(inputs: dict[str, Any]) -> dict[str, Any]:
    """Expired or too-old tool results are rejected before a decision (MH-PA-01)."""
    from mechaharness.iso_timestamp import parse_iso_timestamp
    request = inputs
    now = parse_iso_timestamp(request["now"])
    policy = ToolResultFreshnessPolicy(**(request.get("policy") or {}))
    rejected: list[str] = []
    passed: list[str] = []
    for raw in request["results"]:
        result = ToolResult.model_validate(raw)
        checked = policy.reject_if_stale(result, now=now)
        (rejected if checked.is_error and not result.is_error else passed).append(
            result.tool_call_id
        )
    actual = {"rejected_ids": rejected, "passed_ids": passed}
    return actual


async def run_effect_revalidation_check(inputs: dict[str, Any]) -> dict[str, Any]:
    """Authority is rechecked right before an execute-phase effect (MH-DOTS-02)."""
    from mechaharness.effect_revalidation import revalidate_before_effect
    from mechaharness.iso_timestamp import parse_iso_timestamp
    request = inputs
    now = parse_iso_timestamp(request["now"])
    envelope = CapabilityEnvelope.model_validate(request["envelope"])
    results: dict[str, str] = {}
    for check in request["checks"]:
        outcome = revalidate_before_effect(
            envelope=envelope,
            required_grants=check.get("required_grants") or [],
            live_authorization_epoch=check.get("live_authorization_epoch"),
            now=now,
        )
        results[check["id"]] = "ok" if outcome.ok else str(outcome.reason)
    # Wire check: a paused graph resumed after revocation must not run the effect.
    calls: list[str] = []

    async def effect(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        calls.append(node.id)
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["publish"], effect)])

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
    executor.live_authorization_epoch = lambda: int(request["revoked_epoch"])
    graph = ExecutionGraph(goal="publish", version="1")
    graph.add_node(GraphNode(id="publish_post", kind="publish"))
    run = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        envelope=CapabilityEnvelope(
            grants=["core:graph.execute"],
            authorization_epoch=int(request["envelope"].get("authorization_epoch", 0)),
        ),
    )
    from tests.stories.cli_probes.graph_cost import with_graph_cost

    actual = with_graph_cost(
        {
            "results": results,
            "graph_status": run.status,
            "node_error_contains": graph.nodes["publish_post"].error or "",
            "effect_calls": len(calls),
        },
        run,
    )
    return actual


async def run_authority_gate_evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    """One gate composes access, envelope, consequence, trust, and verdict (MH-PA-02)."""
    from mechaharness.authority_gate import AuthorityGate
    from mechaharness.core.events import InMemoryEventLog as _Log
    from mechaharness.iso_timestamp import parse_iso_timestamp
    from mechaharness.judgement_policy import Verdict
    request = inputs
    now = parse_iso_timestamp(request["now"])
    gate = AuthorityGate(
        access=InMemoryAccessControl(
            _Log(), AccessPolicy(grants=list(request["access_grants"]))
        ),
        consequence=ConsequencePolicy(
            actions=[ActionConsequence.model_validate(a) for a in request["actions"]]
        ),
    )
    decisions: dict[str, str] = {}
    for scenario in request["scenarios"]:
        kwargs = dict(scenario["evaluate"])
        if "envelope" in kwargs:
            kwargs["envelope"] = CapabilityEnvelope.model_validate(kwargs["envelope"])
        if "verdict" in kwargs:
            kwargs["verdict"] = Verdict.model_validate(kwargs["verdict"])
        decision = gate.evaluate(now=now, **kwargs)
        decisions[scenario["id"]] = ":".join([decision.outcome, *decision.reason_codes])
    return {"decisions": decisions}


async def run_denial_store_equivalence(inputs: dict[str, Any]) -> dict[str, Any]:
    """A denied intent stays denied across tools until explicitly lifted (MH-DOTS-05)."""
    from mechaharness.authority_gate import AuthorityGate
    from mechaharness.denial_store import InMemoryDenialStore, equivalent_action_digest
    from mechaharness.judgement_policy import Verdict
    request = inputs
    store = InMemoryDenialStore()
    gate = AuthorityGate(denials=store)
    denied = request["denied"]
    first_digest = equivalent_action_digest(denied["effect_class"], denied["target"])
    first = gate.evaluate(
        action=denied["effect_class"],
        verdict=Verdict(kind="DENY", reasonCodes=["user_denied"], policyVersion="1"),
        action_digest=first_digest,
        tool_name=denied["tool_name"],
    )
    retries: dict[str, str] = {}
    for retry in request["retries"]:
        digest = equivalent_action_digest(retry["effect_class"], retry["target"])
        decision = gate.evaluate(
            action=retry["effect_class"],
            approved=True,
            action_digest=digest,
            tool_name=retry["tool_name"],
        )
        retries[retry["id"]] = ":".join([decision.outcome, *decision.reason_codes])
    lifted = store.lift(first_digest)
    after_lift = gate.evaluate(
        action=denied["effect_class"], approved=True, action_digest=first_digest
    )
    actual = {
        "first": ":".join([first.outcome, *first.reason_codes]),
        "retries": retries,
        "lifted": lifted,
        "after_lift": after_lift.outcome,
    }
    return actual


async def run_cross_task_isolation_bleed(inputs: dict[str, Any]) -> dict[str, Any]:
    """Task-local refs do not bleed across intervening tasks (MH-DOTS-07)."""
    from mechaharness.isolation.cross_task_isolation import (
        CrossTaskIsolationGuard,
        IsolationViolation,
    )
    from mechaharness.isolation.isolation_contract import IsolationContract
    request = inputs
    contract = IsolationContract.model_validate(request["contract"])
    guard = CrossTaskIsolationGuard()
    guard.open_task("origin", contract)
    for ref in request["published_refs"]:
        guard.publish("origin", ref)
    bleed: dict[str, bool] = {}
    for count in request["intervening_counts"]:
        leaked = False
        for i in range(int(count)):
            task = f"task_{count}_{i}"
            guard.open_task(task, contract)
            leaked = leaked or any(guard.can_read(task, r) for r in request["published_refs"])
            guard.close_task(task)
        bleed[str(count)] = leaked
    guard.open_task("receiver", contract)
    shared = HandoffRecord.model_validate(request["handoff"])
    guard.share("origin", "receiver", shared)
    try:
        guard.share("origin", "receiver", HandoffRecord(evidence_refs=["memo:ghost"]))
        ghost_refused = False
    except IsolationViolation:
        ghost_refused = True
    actual = {
        "bleed_by_intervening_count": bleed,
        "receiver_reads_shared": guard.can_read("receiver", shared.evidence_refs[0]),
        "receiver_reads_unshared": guard.can_read("receiver", request["published_refs"][-1]),
        "ghost_handoff_refused": ghost_refused,
    }
    return actual


async def run_alert_escalation_stages(inputs: dict[str, Any]) -> dict[str, Any]:
    """Counts map to log / surface / propose with no model in the loop (MH-PA-06)."""
    from mechaharness.alert_escalation import AlertEscalationPolicy, AlertOccurrenceCounter
    request = inputs
    policy = AlertEscalationPolicy.model_validate(request["policy"])
    counter = AlertOccurrenceCounter(policy)
    try:
        AlertEscalationPolicy.model_validate(request["unordered_policy"])
        unordered_refused = False
    except ValueError:
        unordered_refused = True
    actual = {
        "ladder": [policy.evaluate(request["alert"], n) for n in request["counts"]],
        "override_ladder": [
            policy.evaluate(request["override_alert"], n) for n in request["override_counts"]
        ],
        "counter_walk": [counter.record(request["alert"]) for _ in request["counts"]],
        "unordered_refused": unordered_refused,
    }
    return actual


async def run_recipe_audit_dimensions(inputs: dict[str, Any]) -> dict[str, Any]:
    """Recipe selection and freshness are first-class audit dimensions (MH-PA-08)."""
    from mechaharness.decision_log import summarize_recipe_audit
    from mechaharness.iso_timestamp import parse_iso_timestamp
    from mechaharness.tool_result_freshness import summarize_freshness
    request = inputs
    now = parse_iso_timestamp(request["now"])
    records: list[DecisionRecord] = []
    for raw in request["decisions"]:
        row = dict(raw)
        results = [ToolResult.model_validate(r) for r in row.pop("tool_results", [])]
        if results:
            row["freshnessSummary"] = summarize_freshness(results, now=now)
        records.append(DecisionRecord.model_validate(row))
    envelope = TraceEnvelope.model_validate(request["envelope"])
    rows = summarize_recipe_audit(records)
    actual = {
        "rows": [
            [
                r.recipe_id,
                r.recipe_version,
                r.decisions,
                r.verdicts,
                r.fresh_evidence,
                r.stale_evidence,
            ]
            for r in rows
        ],
        "unattributed_skipped": sum(r.decisions for r in rows)
        == sum(1 for r in records if r.recipe_id),
        "envelope_recipe": [envelope.recipe_id, envelope.recipe_version],
        "envelope_still_complete": envelope_complete(envelope),
    }
    return actual


async def run_review_audit_reconstruct(inputs: dict[str, Any]) -> dict[str, Any]:
    """A review is rebuilt from the decision log and trace envelope alone (MH-DOTS-09)."""
    from pyiv.files import MemoryFilesystem

    from mechaharness.decision_log import DecisionLog, ReviewAuditRecord
    request = inputs
    log = DecisionLog(InMemoryEventLog(), filesystem=MemoryFilesystem())
    results: dict[str, Any] = {}
    for scenario in request["scenarios"]:
        event = log.record(DecisionRecord.model_validate(scenario["decision"]))
        # Rebuild from the persisted event payload, not the in-memory object.
        rebuilt = DecisionRecord.model_validate(event.payload)
        envelope = (
            TraceEnvelope.model_validate(scenario["envelope"])
            if scenario.get("envelope")
            else None
        )
        audit = ReviewAuditRecord.from_records(
            rebuilt, envelope, **scenario.get("attested", {})
        )
        results[scenario["id"]] = {
            "reconstructable": audit.reconstructable(),
            "missing": audit.missing_dimensions(),
            "approvals": audit.approval_ids,
            "denials": audit.denial_ids,
            "effects": audit.effect_ids,
            "policy": [audit.policy_version, audit.policy_revision],
        }
    return {"scenarios": results}




ACCESS_AUTHORITY_HANDLERS: dict[str, Any] = {
    "wrong_lane_deny": run_wrong_lane_deny,
    "grant_gate_write": run_grant_gate_write,
    "config_access_policy": run_config_access_policy,
    "tool_gating": run_tool_gating,
    "capability_envelope_narrow": run_capability_envelope_narrow,
    "consequence_risk_scale": run_consequence_risk_scale,
    "isolation_io_contract": run_isolation_io_contract,
    "approval_interrupt_cycle": run_approval_interrupt_cycle,
    "workspace_isolation_acquire": run_workspace_isolation_acquire,
    "state_governance_write": run_state_governance_write,
    "execution_token_narrow": run_execution_token_narrow,
    "tool_phase_effect_guard": run_tool_phase_effect_guard,
    "auth_epoch_resume_refuse": run_auth_epoch_resume_refuse,
    "tool_result_freshness_reject": run_tool_result_freshness_reject,
    "effect_revalidation_check": run_effect_revalidation_check,
    "authority_gate_evaluate": run_authority_gate_evaluate,
    "denial_store_equivalence": run_denial_store_equivalence,
    "cross_task_isolation_bleed": run_cross_task_isolation_bleed,
    "alert_escalation_stages": run_alert_escalation_stages,
    "recipe_audit_dimensions": run_recipe_audit_dimensions,
    "review_audit_reconstruct": run_review_audit_reconstruct,
}


class AccessAuthorityParams(BaseModel):
    model_config = ConfigDict(extra="allow")


def _access_probe(name: str, fn: Any) -> type[CliProbe]:
    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            assert isinstance(params, AccessAuthorityParams)
            return await fn(params.model_dump())

    _P.name = name
    _P.params_model = AccessAuthorityParams
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def access_authority_cli_probe_classes() -> dict[str, type[CliProbe]]:
    return {
        name: _access_probe(name, fn)
        for name, fn in ACCESS_AUTHORITY_HANDLERS.items()
    }


__all__ = [
    "ACCESS_AUTHORITY_HANDLERS",
    "AccessAuthorityParams",
    "access_authority_cli_probe_classes",
]
