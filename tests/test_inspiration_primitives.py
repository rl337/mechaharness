"""Graph templates, verification, advisor, delegation, experiments."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.advisor import (
    AdvisorRequest,
    AdvisorContextContract,
    DefaultAdvisorPolicy,
    RejectAdvisor,
    consult_advisor,
)
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.consequence import ConsequencePolicy, ActionConsequence
from mechaharness.context_provider import StaticContextProvider, ContextProviderRegistry
from mechaharness.core.access import GraphExecute
from mechaharness.delegation_policy import DefaultDelegationPolicy, DelegationRequest
from mechaharness.di import MechaHarnessConfig
from mechaharness.failure_attribution import attribute_error, detect_repeated_failure_classes
from mechaharness.graph import ExecutionGraph, GraphNode, GraphStore, NodeStatus, VerificationOracle
from mechaharness.graph_executor import GraphExecutor
from mechaharness.graph_template import (
    GraphTemplateParams,
    IndependentReviewTemplate,
    SubgraphNodeRunner,
    default_graph_templates,
)
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness_experiment import HarnessExperiment, HarnessExperimentRunner
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.instruction_component import InstructionCatalog
from mechaharness.outcome_contract import OutcomeContract
from mechaharness.routing import route_for_capability_needs
from mechaharness.verification_policy import DefaultVerificationPolicy


class _TplConfig(MechaHarnessConfig):
    def get_inference_class(self):
        return MockInferenceStrategy

    def get_harness_class(self):
        return PassThroughHarness

    def get_grants(self):
        return [GraphExecute]


def test_default_templates_registered_via_di() -> None:
    inj = get_injector(_TplConfig())
    from mechaharness.graph_template import GraphTemplateRegistry

    registry = inj.inject(GraphTemplateRegistry)
    for name in (
        "fan_out_aggregate",
        "verify_repair",
        "independent_review",
        "environment_repair",
    ):
        assert registry.get(name) is not None


def test_independent_review_template_isolates_reviewers() -> None:
    graph = IndependentReviewTemplate().instantiate(
        GraphTemplateParams(
            goal="review me",
            inputs={"reviewer_count": 2},
            acceptance=["lgtm"],
        )
    )
    assert "produce" in graph.nodes
    assert "review_0" in graph.nodes
    assert "review_1" in graph.nodes
    assert graph.nodes["review_0"].payload.get("omit_producer_reasoning") is True
    assert graph.nodes["aggregate_reviews"].payload.get("retain_disagreement") is True


@pytest.mark.asyncio
async def test_subgraph_node_runs_nested_graph() -> None:
    inj = get_injector(_TplConfig())
    executor = inj.inject(GraphExecutor)
    # Register a compute runner via mutating registry
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome, GraphNodeRunnerRegistry

    async def ok(node, context):
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"ok": node.id})

    registry = inj.inject(GraphNodeRunnerRegistry)
    registry.register(CallableGraphNodeRunner(["compute"], ok))

    child = ExecutionGraph(goal="child")
    child.add_node(GraphNode(id="c1", kind="compute"))
    parent = ExecutionGraph(goal="parent")
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    # Parent also needs linkage for subgraph kind — register noop subgraph is handled by executor
    result = await executor.run(parent, skip_linkage=True)
    assert result.status == "ok"
    assert parent.nodes["wrap"].status == NodeStatus.SUCCEEDED
    assert parent.nodes["wrap"].payload.get("child_status") == "ok"


@pytest.mark.asyncio
async def test_resume_refuses_fingerprint_mismatch() -> None:
    inj = get_injector(_TplConfig())
    executor = inj.inject(GraphExecutor)
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome, GraphNodeRunnerRegistry

    async def ok(node, context):
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = inj.inject(GraphNodeRunnerRegistry)
    registry.register(CallableGraphNodeRunner(["compute"], ok))

    graph = ExecutionGraph(goal="fp", version="1")
    graph.add_node(GraphNode(id="a", kind="compute"))
    first = await executor.run(graph, run_id="fp-run")
    assert first.status == "ok"
    assert graph.config_fingerprint

    executor.fingerprint_parts = {"harness_version": "changed"}
    resumed = await executor.run(graph, run_id="fp-run", resume=True)
    assert resumed.status == "failed"
    assert resumed.error and "incompatible_checkpoint_fingerprint" in resumed.error


def test_verification_and_outcome_contract() -> None:
    policy = DefaultVerificationPolicy()
    node = GraphNode(id="n", kind="compute")
    oracles = [
        VerificationOracle(name="schema", strength="schema"),
        VerificationOracle(name="exec", strength="executable"),
    ]

    def good(_node):
        return True, {"ok": True}

    outcome = OutcomeContract(require_verification=True, acceptance=["done"])
    result = policy.verify(
        node,
        oracles=oracles,
        verifiers=[good],
        outcome=outcome,
        answer_generated=True,
    )
    assert result.passed
    assert result.completion == "complete"
    assert result.plan and result.plan.oracle_names == ["exec"]


def test_delegation_and_advisor_and_routing() -> None:
    decision = DefaultDelegationPolicy().decide(
        DelegationRequest(
            independence_required=True,
            parent_envelope=CapabilityEnvelope(grants=["core:graph.execute"]),
        )
    )
    assert decision.choice == "child"

    route = route_for_capability_needs(
        capability_needs=["model:reason-large"],
        available_model_classes=["reason-fast", "reason-large"],
    )
    assert route["selected_model_class"] == "reason-large"


@pytest.mark.asyncio
async def test_advisor_sparse_non_binding() -> None:
    policy = DefaultAdvisorPolicy(max_consultations=1)
    observations = []
    guidance = await consult_advisor(
        RejectAdvisor(),
        policy,
        AdvisorRequest(
            trigger="user_initiated",
            context=AdvisorContextContract(summary="what next?"),
        ),
        observations=observations,
    )
    assert guidance is not None
    assert observations[0].guidance is not None
    # Second consultation blocked by budget
    again = await consult_advisor(
        RejectAdvisor(),
        policy,
        AdvisorRequest(trigger="user_initiated"),
        observations=observations,
    )
    assert again is None


def test_harness_experiment_retirement() -> None:
    runner = HarnessExperimentRunner()
    exp = runner.propose(
        HarnessExperiment(
            hypothesis="drop redundant prompt",
            intervention="remove_scaffold_x",
            failure_mode="token_bloat",
            evidence="blog:token-efficiency",
        )
    )
    runner.evaluate(
        exp,
        with_intervention=lambda: {"task_success_rate": 0.7},
        without_intervention=lambda: {"task_success_rate": 0.9},
    )
    assert exp.status == "retired"
    assert runner.retirement_candidates()


def test_instruction_gotcha_metrics_and_consequence() -> None:
    catalog = InstructionCatalog()
    gotcha = catalog.append_gotcha("watch path", "never dump full KG", provenance={"source": "june"})
    gotcha.record_trigger(used=True, appropriate=False)
    assert catalog.metrics()[gotcha.id]["over_trigger"] == 1.0
    catalog.promote(gotcha.id)
    assert catalog.active(kind="gotcha")

    policy = ConsequencePolicy(
        actions=[ActionConsequence(action="fs.write", consequence="high", requires_approval=True)]
    )
    policy.record_approval_prompt()
    policy.record_approval_decision()
    assert policy.requires_stronger_controls("fs.write")
    assert policy.approval_frequency() == 1.0


def test_context_provider_index_before_load() -> None:
    provider = StaticContextProvider("june.kg", {"fact:1": "alpha beta " * 50})
    registry = ContextProviderRegistry([provider])
    entries = registry.get("june.kg").index(budget=8)
    assert entries[0].ref == "fact:1"
    chunks = provider.load([entries[0].ref])
    assert chunks[0].provider_id == "june.kg"


def test_failure_attribution_repeated_classes() -> None:
    attrs = [
        attribute_error("no_runner:x", node_id="a"),
        attribute_error("no_runner:y", node_id="b"),
        attribute_error("permission_denied", node_id="c"),
    ]
    assert "no_runner" in detect_repeated_failure_classes(attrs)


def test_checkpoint_store_fingerprint() -> None:
    from mechaharness.checkpoint_store import EventLogCheckpointStore
    from mechaharness.core.events import InMemoryEventLog

    store = EventLogCheckpointStore(GraphStore(InMemoryEventLog()))
    graph = ExecutionGraph(goal="g")
    graph.add_node(GraphNode(id="a", kind="compute"))
    store.save(graph, run_id="r1", fingerprint="abc123", boundary="dispatch")
    assert store.latest_fingerprint(run_id="r1") == "abc123"
    assert store.latest(run_id="r1") is not None


def test_default_templates_count() -> None:
    assert len(default_graph_templates().names()) >= 4
