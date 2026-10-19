"""Grant, authority, effect-phase, isolation, and audit story runners."""

from __future__ import annotations

from typing import Any

from mechaharness.approval_interrupt import resume_approval, suspend_for_approval
from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
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
from mechaharness.inference.judge import (
    NoulSignal,
)
from mechaharness.isolation.isolation_contract import IsolationContract, TemplateIOContract
from mechaharness.isolation.workspace_isolation import (
    InMemoryWorkspaceIsolationProvider,
    WorkspaceIsolationRequest,
)
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
    decide,
)
from mechaharness.operation_registry import (
    OperationContract,
    OperationRegistry,
)
from mechaharness.tool_result_freshness import ToolResultFreshnessPolicy
from mechaharness.tools.base import ToolRegistry
from mechaharness.trace_envelope import TraceEnvelope, envelope_complete
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect, _LaneEnvironment
from tests.support.di import make_harness


async def _run_wrong_lane_deny(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    env: InferenceEnvironment = _LaneEnvironment(request["active_lane"])
    raised: Exception | None = None
    try:
        env.assert_compatible(require_lane=request["require_lane"])
    except Exception as exc:  # noqa: BLE001 — type checked via expect
        raised = exc
    assert raised is not None, "expected InferenceEnvironmentError"
    assert isinstance(raised, InferenceEnvironmentError)
    actual = {
        "error_type": type(raised).__name__,
        "error_match": str(raised),
    }
    assert actual["error_type"] == expect["error_type"]
    assert expect["error_match"].lower() in actual["error_match"].lower()


async def _run_grant_gate_write(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")

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
    _assert_expect(actual, expect)


async def _run_config_access_policy(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_human_review_pending(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    policy = JudgementPolicy(
        version="story-review",
        require_approval_for=["mutate"],
        thresholds=[
            JudgementThreshold(signal_id="destructive", allow_above=0.9, ask_below=0.9),
        ],
    )
    ask = decide(
        JudgementFacts(action="mutate", action_digest="sha256:story"),
        [NoulSignal(id="destructive", p_true=0.95)],
        policy,
    )
    allow = decide(
        JudgementFacts(
            action="mutate",
            action_digest="sha256:story",
            approvals={"sha256:story": "approved-1"},
        ),
        [NoulSignal(id="destructive", p_true=0.95)],
        policy,
    )
    actual = {"verdict_kinds": [ask.kind, allow.kind]}
    _assert_expect(actual, expect)


async def _run_tool_gating(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")

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
    _assert_expect(actual, expect)


async def _run_capability_envelope_narrow(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_consequence_risk_scale(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_isolation_io_contract(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_approval_interrupt_cycle(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_workspace_isolation_acquire(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    provider = InMemoryWorkspaceIsolationProvider()
    handle = provider.acquire(WorkspaceIsolationRequest(label=str(request.get("label") or "x")))
    provider.release(handle)
    actual = {"provider_kind": handle.provider_kind, "released": True}
    _assert_expect(actual, expect)


async def _run_state_governance_write(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_execution_token_narrow(case: StoryCase, backend: StoryBackend) -> None:
    """Child envelopes attenuate token fields and refuse widening (MH-DOTS-01)."""
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_tool_phase_effect_guard(case: StoryCase, backend: StoryBackend) -> None:
    """Observe/prepare tools cannot register write/external effects (MH-DOTS-03)."""
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_auth_epoch_resume_refuse(case: StoryCase, backend: StoryBackend) -> None:
    """Resume fails closed when the live authorization epoch differs (MH-DOTS-06)."""
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    actual = {
        "first_status": first.status,
        "checkpoint_epoch": executor.store.latest_authorization_epoch(run_id="insp-epoch"),
        "resume_status": resumed.status,
        "error_contains": resumed.error or "",
        "runner_calls_after_resume": len(calls),
    }
    _assert_expect(actual, expect)


async def _run_tool_result_freshness_reject(case: StoryCase, backend: StoryBackend) -> None:
    """Expired or too-old tool results are rejected before a decision (MH-PA-01)."""
    del backend
    from mechaharness.iso_timestamp import parse_iso_timestamp

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_effect_revalidation_check(case: StoryCase, backend: StoryBackend) -> None:
    """Authority is rechecked right before an execute-phase effect (MH-DOTS-02)."""
    del backend
    from mechaharness.effect_revalidation import revalidate_before_effect
    from mechaharness.iso_timestamp import parse_iso_timestamp

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    actual = {
        "results": results,
        "graph_status": run.status,
        "node_error_contains": graph.nodes["publish_post"].error or "",
        "effect_calls": len(calls),
    }
    _assert_expect(actual, expect)


async def _run_authority_gate_evaluate(case: StoryCase, backend: StoryBackend) -> None:
    """One gate composes access, envelope, consequence, trust, and verdict (MH-PA-02)."""
    del backend
    from mechaharness.authority_gate import AuthorityGate
    from mechaharness.core.events import InMemoryEventLog as _Log
    from mechaharness.iso_timestamp import parse_iso_timestamp
    from mechaharness.judgement_policy import Verdict

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect({"decisions": decisions}, expect)


async def _run_denial_store_equivalence(case: StoryCase, backend: StoryBackend) -> None:
    """A denied intent stays denied across tools until explicitly lifted (MH-DOTS-05)."""
    del backend
    from mechaharness.authority_gate import AuthorityGate
    from mechaharness.denial_store import InMemoryDenialStore, equivalent_action_digest
    from mechaharness.judgement_policy import Verdict

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_cross_task_isolation_bleed(case: StoryCase, backend: StoryBackend) -> None:
    """Task-local refs do not bleed across intervening tasks (MH-DOTS-07)."""
    del backend
    from mechaharness.isolation.cross_task_isolation import (
        CrossTaskIsolationGuard,
        IsolationViolation,
    )
    from mechaharness.isolation.isolation_contract import IsolationContract

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_alert_escalation_stages(case: StoryCase, backend: StoryBackend) -> None:
    """Counts map to log / surface / propose with no model in the loop (MH-PA-06)."""
    del backend
    from mechaharness.alert_escalation import AlertEscalationPolicy, AlertOccurrenceCounter

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_recipe_audit_dimensions(case: StoryCase, backend: StoryBackend) -> None:
    """Recipe selection and freshness are first-class audit dimensions (MH-PA-08)."""
    del backend
    from mechaharness.decision_log import summarize_recipe_audit
    from mechaharness.iso_timestamp import parse_iso_timestamp
    from mechaharness.tool_result_freshness import summarize_freshness

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
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
    _assert_expect(actual, expect)


async def _run_review_audit_reconstruct(case: StoryCase, backend: StoryBackend) -> None:
    """A review is rebuilt from the decision log and trace envelope alone (MH-DOTS-09)."""
    del backend
    from mechaharness.decision_log import DecisionLog, ReviewAuditRecord

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    log = DecisionLog(InMemoryEventLog())
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
    _assert_expect({"scenarios": results}, expect)



RUNNERS: dict[str, StoryRunner] = {
    "wrong_lane_deny": _run_wrong_lane_deny,
    "grant_gate_write": _run_grant_gate_write,
    "config_access_policy": _run_config_access_policy,
    "human_review_pending": _run_human_review_pending,
    "tool_gating": _run_tool_gating,
    "capability_envelope_narrow": _run_capability_envelope_narrow,
    "consequence_risk_scale": _run_consequence_risk_scale,
    "isolation_io_contract": _run_isolation_io_contract,
    "approval_interrupt_cycle": _run_approval_interrupt_cycle,
    "workspace_isolation_acquire": _run_workspace_isolation_acquire,
    "state_governance_write": _run_state_governance_write,
    "execution_token_narrow": _run_execution_token_narrow,
    "tool_phase_effect_guard": _run_tool_phase_effect_guard,
    "auth_epoch_resume_refuse": _run_auth_epoch_resume_refuse,
    "tool_result_freshness_reject": _run_tool_result_freshness_reject,
    "effect_revalidation_check": _run_effect_revalidation_check,
    "authority_gate_evaluate": _run_authority_gate_evaluate,
    "denial_store_equivalence": _run_denial_store_equivalence,
    "cross_task_isolation_bleed": _run_cross_task_isolation_bleed,
    "alert_escalation_stages": _run_alert_escalation_stages,
    "recipe_audit_dimensions": _run_recipe_audit_dimensions,
    "review_audit_reconstruct": _run_review_audit_reconstruct,
}
