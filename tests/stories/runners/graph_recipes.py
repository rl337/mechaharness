"""Agentic Recipe / GraphTemplate story runners."""

from __future__ import annotations

from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.core.access import (
    GraphExecute,
)
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.evaluator import (
    EvaluatorResult,
)
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    NodeStatus,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_templates import (
    BoundedRetryTemplate,
    ConversationalToolLoopTemplate,
    EnvironmentRepairTemplate,
    FanOutAggregateTemplate,
    GraphTemplateParams,
    IndependentReviewTemplate,
    InitializePreflightTemplate,
    VerifyRepairTemplate,
    default_graph_templates,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.host_kit import host_graph_executor
from mechaharness.inference.base import InferenceStrategy
from mechaharness.node_component import (
    NODE_COMPONENT_KINDS,
    embed_recipe_as_tool,
    node_components_for,
    traversal_from_events,
)
from mechaharness.objective_policy import ObjectivePolicy, aggregate_objective
from mechaharness.research import EvalProtocol, ResearchLab
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect


async def _run_graph_template_soft_points(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    template = registry.get(str(request["template"]))
    assert template is not None
    n = int(request.get("branch_count", 2))
    graph = template.instantiate(
        GraphTemplateParams(
            goal=str(request.get("goal") or ""),
            branch_payloads=[{"index": i} for i in range(n)],
            acceptance=list(request.get("acceptance") or []),
            source_workflow_ref=request.get("source_workflow_ref"),
        )
    )
    demoted = FanOutAggregateTemplate()
    demoted.status = "demoted"
    refused = False
    try:
        demoted.instantiate(GraphTemplateParams(goal="nope"))
    except RuntimeError:
        refused = True
    catalog = registry.catalog()
    soft_nonempty = all(bool(row.get("soft_points")) for row in catalog)
    actual = {
        "template_name": graph.template_name,
        "template_status": graph.template_status,
        "node_ids_include": list(graph.nodes),
        "source_workflow_ref": graph.source_workflow_ref,
        "catalog_soft_points_nonempty": soft_nonempty,
        "demoted_refused": refused,
    }
    _assert_expect(actual, expect)


async def _run_independent_review_template(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = IndependentReviewTemplate().instantiate(
        GraphTemplateParams(
            goal="review",
            inputs={"reviewer_count": int(request.get("reviewer_count", 1))},
            acceptance=list(request.get("acceptance") or []),
        )
    )
    reviews = [n for n in graph.nodes if n.startswith("review_")]
    actual = {
        "review_count": len(reviews),
        "omit_producer_reasoning": graph.nodes[reviews[0]].payload.get(
            "omit_producer_reasoning"
        ),
        "retain_disagreement": graph.nodes["aggregate_reviews"].payload.get(
            "retain_disagreement"
        ),
        "template_name": graph.template_name,
    }
    _assert_expect(actual, expect)


async def _run_node_components(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    template = ConversationalToolLoopTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="components",
            inputs={"max_iterations": int(request.get("max_iterations") or 3)},
        )
    )
    comps = node_components_for(graph, template=template)
    kinds = {c.kind for c in comps}
    actual = {
        "all_have_parent": all(bool(c.parent_node_id) for c in comps),
        "kinds_subset_catalog": kinds <= NODE_COMPONENT_KINDS,
        "has_stop_contract": "stop_contract" in kinds,
        "has_soft_point": "soft_point" in kinds,
    }
    _assert_expect(actual, expect)


async def _run_traversal_contract(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    records = traversal_from_events(list(request.get("events") or []))
    kinds = {r.kind for r in records}
    actual = {
        "record_count_min": len(records),
        "has_inference": "inference" in kinds,
        "has_tool_call": "tool_call" in kinds,
        "all_have_parent": all(bool(r.parent_node_id) for r in records),
    }
    _assert_expect(actual, expect)


async def _run_recipe_as_tool(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    child = ExecutionGraph(goal=str(request.get("child_goal") or "child"))
    child.add_node(GraphNode(id="prompt", kind="compute"))
    child.template_name = "oneshot"
    parent = ExecutionGraph(goal="parent")
    parent.add_node(
        embed_recipe_as_tool(
            child,
            parent_node_id=str(request.get("parent_node_id") or "generate_image"),
            tool_name=str(request.get("tool_name") or "generate_image"),
        )
    )
    executor = host_graph_executor(
        runners=[CallableGraphNodeRunner(["compute"], ok)],
    )
    result = await executor.run(
        parent,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="story-rat",
        skip_linkage=True,
    )
    wrap = result.graph.nodes[str(request.get("parent_node_id") or "generate_image")]
    comps = node_components_for(result.graph)
    actual = {
        "status": result.status,
        "child_run_id_nonempty": bool(wrap.payload.get("child_run_id")),
        "child_status": wrap.payload.get("child_status"),
        "has_child_graph_component": any(c.kind == "child_graph" for c in comps),
    }
    _assert_expect(actual, expect)


async def _run_initialize_preflight_template(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = InitializePreflightTemplate().instantiate(
        GraphTemplateParams(goal=str(request.get("goal") or "preflight"))
    )
    actual = {"nodes_include": sorted(graph.nodes)}
    _assert_expect(actual, expect)


async def _run_environment_repair_recipe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    template = EnvironmentRepairTemplate()
    graph = template.instantiate(
        GraphTemplateParams(goal=str(request.get("goal") or "environment_repair"))
    )
    actual = {
        "template_name": graph.template_name,
        "nodes_include": list(graph.nodes),
        "recipe_category": template.category,
    }
    _assert_expect(actual, expect)


async def _run_verify_repair_recipe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = VerifyRepairTemplate().instantiate(
        GraphTemplateParams(goal=str(request.get("goal") or "verify_repair"))
    )
    actual = {
        "template_name": graph.template_name,
        "nodes_include": list(graph.nodes),
    }
    _assert_expect(actual, expect)


async def _run_recipe_namespace_tile(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    recipe_name = str(request.get("recipe") or "verify_repair")
    template = registry.get(recipe_name)
    assert template is not None
    keys = list(request.get("instance_keys") or ["left", "right"])
    parent = ExecutionGraph(goal="parent")
    children = []
    embeds = []
    for key in keys:
        child, embed = template.tile(
            GraphTemplateParams(
                goal=f"{recipe_name}:{key}",
                instance_key=str(key),
            ),
            parent_node_id=f"embed_{key}",
        )
        children.append(child)
        embeds.append(embed)
        parent.add_node(embed)
    id_sets = [set(c.nodes) for c in children]
    overlap = bool(id_sets[0].intersection(*id_sets[1:])) if len(id_sets) > 1 else False
    left = children[0]
    prefix_left = f"{recipe_name}/{keys[0]}/"
    assert any(nid.startswith(prefix_left) for nid in left.nodes)
    actual = {
        "instance_count": len(children),
        "node_id_overlap": overlap,
        "distinct_instance_ids": len({c.recipe_instance_id for c in children})
        == len(children),
        "parent_embed_kinds": [e.kind for e in embeds],
        "namespaced_prefix_left": prefix_left,
    }
    _assert_expect(actual, expect)


async def _run_bounded_retry_recipe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = BoundedRetryTemplate().instantiate(
        GraphTemplateParams(
            goal=str(request.get("goal") or "bounded_retry"),
            inputs={"max_attempts": int(request.get("max_attempts") or 3)},
        )
    )
    attempt = graph.nodes["attempt"]
    stop = attempt.stop_contract or {}
    actual = {
        "template_name": graph.template_name,
        "nodes_include": list(graph.nodes),
        "attempt_repeating": attempt.repeating,
        "max_iterations": stop.get("max_iterations"),
        "requires_effect_reconciliation": attempt.payload.get(
            "requires_effect_reconciliation"
        ),
    }
    _assert_expect(actual, expect)


async def _run_recipe_registry_versions(case: StoryCase, backend: StoryBackend) -> None:
    """Immutable recipe versions, lineage, evals, and a reversible pointer (MH-SR-01/05)."""
    del backend
    from mechaharness.graph_templates import GraphTemplateRegistry

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    base = default_graph_templates().get(str(request["recipe"]))
    assert base is not None
    registry = GraphTemplateRegistry([base])
    errors: list[str] = []

    def variant(version: str) -> Any:
        return type(f"V{version}", (type(base),), {"version": version})()

    for step in request["steps"]:
        op = step["op"]
        try:
            if op == "add_version":
                registry.add_version(
                    variant(step["version"]), parent_version=step.get("parent_version")
                )
            elif op == "promote":
                registry.promote(base.name, step["version"])
            elif op == "rollback":
                registry.rollback(base.name)
            elif op == "attach_evaluation":
                registry.attach_evaluation(base.name, step["version"], step["result"])
            else:
                raise AssertionError(f"unknown registry op {op!r}")
        except (KeyError, ValueError) as exc:
            errors.append(f"{op}:{type(exc).__name__}")
    actual = {
        "active_version": registry.active_version(base.name),
        "versions": registry.versions(base.name),
        "lineage": registry.lineage(base.name),
        "evaluation_counts": {
            v: len(registry.evaluations(base.name, v)) for v in registry.versions(base.name)
        },
        "errors": errors,
    }
    _assert_expect(actual, expect)


async def _run_soft_point_evolution_allowlist(case: StoryCase, backend: StoryBackend) -> None:
    """Only declared evolvable soft points may be rewritten (MH-SR-03)."""
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    outcomes: dict[str, str] = {}
    for attempt in request["attempts"]:
        template = registry.get(attempt["recipe"])
        assert template is not None
        try:
            template.assert_evolution_allowed(attempt["changed"])
            outcomes[attempt["id"]] = "allowed"
        except ValueError:
            outcomes[attempt["id"]] = "refused"
    evolvable = {
        name: (registry.get(name).evolvable_soft_point_names())  # type: ignore[union-attr]
        for name in request["recipes"]
    }
    _assert_expect({"outcomes": outcomes, "evolvable": evolvable}, expect)


async def _run_registry_only_compose(case: StoryCase, backend: StoryBackend) -> None:
    """Production graphs compose only registered recipes (MH-SR-02)."""
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    results: dict[str, list[str]] = {}
    for scenario in request["scenarios"]:
        parent = ExecutionGraph(goal=scenario["id"])
        for tile in scenario.get("tiles", []):
            template = registry.get(tile["recipe"])
            assert template is not None
            child, embed = template.tile(
                GraphTemplateParams(goal=tile["recipe"], instance_key=tile["key"]),
                parent_node_id=f"embed_{tile['key']}",
            )
            if tile.get("forge_version"):
                child.template_version = tile["forge_version"]
                embed = embed.model_copy(update={"subgraph": child.checkpoint()})
            parent.add_node(embed)
        for node_id in scenario.get("free_form_nodes", []):
            parent.add_node(GraphNode(id=node_id, kind="shell"))
        results[scenario["id"]] = registry.composition_violations(parent)
    _assert_expect({"violations": results}, expect)


async def _run_produce_critique_refine_recipe(case: StoryCase, backend: StoryBackend) -> None:
    """`produce_critique_refine` expands with isolated critique and node components (MH-PA-03)."""
    del backend
    from mechaharness.node_component import node_components_for

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    template = default_graph_templates().get("produce_critique_refine")
    assert template is not None
    graph = template.instantiate(
        GraphTemplateParams(
            goal=str(request["goal"]),
            acceptance=list(request["acceptance"]),
            soft_bindings=dict(request["soft_bindings"]),
        )
    )
    comps = node_components_for(graph, template=template)
    parents: dict[str, list[str]] = {}
    for comp in comps:
        parents.setdefault(comp.parent_node_id, []).append(comp.soft_point_name or comp.kind)
    actual = {
        "template_name": graph.template_name,
        "nodes_include": list(graph.nodes),
        "critic_isolated": graph.nodes["critique"].payload["isolated_context"]
        and graph.nodes["critique"].payload["omit_producer_reasoning"],
        "refine_max_iterations": graph.nodes["refine"].stop_contract["max_iterations"],
        "component_parents": {k: sorted(v) for k, v in sorted(parents.items())},
        "evolvable": template.evolvable_soft_point_names(),
    }
    _assert_expect(actual, expect)


async def _run_recipe_final_test_gate(case: StoryCase, backend: StoryBackend) -> None:
    """Promotion needs a passing held-out final-test result (MH-SR-07)."""
    del backend
    from mechaharness.evaluator import FinalTestGateError

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    lab_outcomes: dict[str, str] = {}
    registry_outcomes: dict[str, str] = {}
    registry = default_graph_templates()
    base = registry.get("verify_repair")
    assert base is not None
    registry.add_version(type("V2", (type(base),), {"version": "2"})(), parent_version="1")
    for attempt in request["attempts"]:
        final = (
            EvaluatorResult(evaluator_id="story:final", version="1", **attempt["final_test"])
            if attempt["final_test"] is not None
            else None
        )
        lab = ResearchLab(EvalProtocol(task_split="story"), baseline_metric=0.5)
        cand = lab.propose("h", {"prompt": "v2"})
        lab.evaluate(cand, metric=0.9)
        try:
            lab.promote(cand, final_test=final)
            lab_outcomes[attempt["id"]] = "promoted"
        except FinalTestGateError:
            lab_outcomes[attempt["id"]] = "refused"
        try:
            registry.promote_with_final_test("verify_repair", "2", final_test=final)
            registry_outcomes[attempt["id"]] = "promoted"
            registry.rollback("verify_repair")
        except FinalTestGateError:
            registry_outcomes[attempt["id"]] = "refused"
    unprotected = ResearchLab(
        EvalProtocol(task_split="story", held_out_protected=False), baseline_metric=0.5
    )
    free = unprotected.propose("h", {"prompt": "v2"})
    unprotected.evaluate(free, metric=0.9)
    unprotected.promote(free)
    actual = {
        "lab": lab_outcomes,
        "registry": registry_outcomes,
        "registry_pointer_after_refusals": registry.active_version("verify_repair"),
        "unprotected_protocol_promotes": unprotected.promoted is free,
    }
    _assert_expect(actual, expect)


async def _run_recipe_evolution_candidates(case: StoryCase, backend: StoryBackend) -> None:
    """Traces → bounded soft-binding candidates → objective selection (MH-SR-06)."""
    del backend
    from mechaharness.eval_evidence import Claim
    from mechaharness.recipe_lifecycle.recipe_evolution import (
        RecipeTraceSummary,
        ScoredCandidate,
        propose_candidates,
        select_candidate,
    )

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    summaries = [RecipeTraceSummary.model_validate(s) for s in request["summaries"]]
    proposal = propose_candidates(
        summaries, registry, allowlist=request.get("allowlist"), max_candidates=3
    )
    again = propose_candidates(
        summaries, registry, allowlist=request.get("allowlist"), max_candidates=3
    )
    policy = ObjectivePolicy.model_validate(request["objective_policy"])
    scored: list[ScoredCandidate] = []
    for row in request["scored"]:
        candidate = next(
            c for c in proposal.candidates if c.soft_bindings == {row["soft_point"]: row["value"]}
        )
        result = aggregate_objective(
            policy,
            [Claim(id=k, statement=k, status=v) for k, v in row["claims"].items()],
            metrics=row["metrics"],
        )
        scored.append(ScoredCandidate(candidate=candidate, result=result))
    picked = select_candidate(scored)
    beaten = select_candidate(scored, baseline_scalar=request["baseline_scalar"])
    actual = {
        "candidate_bindings": [c.soft_bindings for c in proposal.candidates],
        "rejected": [[r.soft_point, r.reason] for r in proposal.rejected],
        "deterministic": proposal.model_dump() == again.model_dump(),
        "graphs_synthesized": any("graph" in c.model_dump() for c in proposal.candidates),
        "selected_bindings": picked.soft_bindings if picked else None,
        "selected_over_baseline": beaten.soft_bindings if beaten else None,
    }
    _assert_expect(actual, expect)


async def _run_safety_eval_recipe(case: StoryCase, backend: StoryBackend) -> None:
    """`safety_eval` runs a scenario, reviews it in isolation, then scores it (MH-DOTS-08)."""
    del backend
    from mechaharness.node_component import node_components_for

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    template = registry.get("safety_eval")
    assert template is not None
    graph = template.instantiate(
        GraphTemplateParams(
            goal=str(request["goal"]),
            inputs=dict(request["inputs"]),
            acceptance=list(request["acceptance"]),
        )
    )
    comps = node_components_for(graph, template=template)
    parents: dict[str, list[str]] = {}
    for comp in comps:
        parents.setdefault(comp.parent_node_id, []).append(comp.soft_point_name or comp.kind)
    score = graph.nodes["score"].payload
    actual = {
        "template_name": graph.template_name,
        "nodes_include": list(graph.nodes),
        "reviewer_isolated": graph.nodes["review"].payload["isolated_context"]
        and graph.nodes["review"].payload["omit_producer_reasoning"],
        "score_deterministic": score["deterministic"],
        "report_fields": score["report_fields"],
        "reported_versions": [score["model_version"], score["recipe_version"]],
        "scenario_classes": graph.nodes["produce"].payload["scenario_classes"],
        "evolvable": template.evolvable_soft_point_names(),
        "component_parents": {k: sorted(v) for k, v in sorted(parents.items())},
        "in_default_catalog": "safety_eval" in registry.names(),
    }
    _assert_expect(actual, expect)


async def _run_recipe_port_search(case: StoryCase, backend: StoryBackend) -> None:
    """Typed-port search returns catalog ids only (MH-SR-04)."""
    del backend
    from mechaharness.recipe_lifecycle.recipe_port_search import search_compatible_recipes

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    found = {
        q["id"]: search_compatible_recipes(
            registry, q.get("required_inputs"), q.get("required_outputs")
        )
        for q in request["queries"]
    }
    actual = {
        "found": found,
        "all_catalog_ids": all(
            name in registry.names() for names in found.values() for name in names
        ),
        "undeclared_recipes_skipped": not any(
            registry.get(name).io_contract is None  # type: ignore[union-attr]
            for names in found.values()
            for name in names
        ),
    }
    _assert_expect(actual, expect)


async def _run_evolution_ownership_split(case: StoryCase, backend: StoryBackend) -> None:
    """Host owns campaign and promotion policy; the library keeps the gates (MH-SR-09)."""
    del backend
    from mechaharness.recipe_lifecycle.evolution_campaign_hooks import (
        EvolutionCampaignHooks,
        NoopEvolutionCampaignHooks,
    )
    from mechaharness.recipe_lifecycle.recipe_promotion_policy import (
        NoopRecipePromotionPolicy,
        RecipePromotionDecision,
        RecipePromotionPolicy,
        RecipePromotionRequest,
        promote_recipe,
    )

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    class _Freeze(RecipePromotionPolicy):
        def decide(self, request: RecipePromotionRequest) -> RecipePromotionDecision:
            return RecipePromotionDecision(allowed=False, reasons=["release_freeze"])

    class _Campaign(NoopEvolutionCampaignHooks):
        def __init__(self) -> None:
            self.promotions: list[list[str]] = []

        def on_promotion(self, recipe_id: str, version: str) -> None:
            self.promotions.append([recipe_id, version])

        def select_workloads(self, recipe_id: str) -> list[str]:
            return [f"{recipe_id}:{w}" for w in request["workloads"]]

        def experiment_budget(self, recipe_id: str) -> float | None:
            return float(request["budget"])

    class _Base(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

    class _Host(_Base):
        def get_recipe_promotion_policy(self) -> RecipePromotionPolicy:
            return _Freeze()

        def get_evolution_campaign_hooks(self) -> EvolutionCampaignHooks:
            return _Campaign()

    default = get_injector(_Base())
    host = get_injector(_Host())
    default_hooks = default.inject(EvolutionCampaignHooks)
    host_hooks = host.inject(EvolutionCampaignHooks)

    def registry_with_v2() -> Any:
        registry = default_graph_templates()
        base = registry.get("verify_repair")
        assert base is not None
        registry.add_version(type("V2", (type(base),), {"version": "2"})(), parent_version="1")
        return registry

    passed = EvaluatorResult(evaluator_id="story:final", version="1", held_out=True, passed=True)
    ask = RecipePromotionRequest(recipe="verify_repair", to_version="2")
    blocked_registry = registry_with_v2()
    blocked = promote_recipe(
        blocked_registry,
        host.inject(RecipePromotionPolicy),
        ask.model_copy(update={"final_test": passed}),
        host_hooks,
    )
    ungated_registry = registry_with_v2()
    ungated = promote_recipe(ungated_registry, NoopRecipePromotionPolicy(), ask, host_hooks)
    allowed_registry = registry_with_v2()
    allowed = promote_recipe(
        allowed_registry,
        NoopRecipePromotionPolicy(),
        ask.model_copy(update={"final_test": passed}),
        host_hooks,
    )
    actual = {
        "default_policy_is_noop": isinstance(
            default.inject(RecipePromotionPolicy), NoopRecipePromotionPolicy
        ),
        "default_hooks": [
            default_hooks.select_workloads("verify_repair"),
            default_hooks.experiment_budget("verify_repair"),
        ],
        "host_hooks": [
            host_hooks.select_workloads("verify_repair"),
            host_hooks.experiment_budget("verify_repair"),
        ],
        "host_policy_blocks": [blocked.allowed, blocked.reasons],
        "host_block_keeps_pointer": blocked_registry.active_version("verify_repair"),
        "library_gate_without_final_test": [
            ungated.allowed,
            ungated_registry.active_version("verify_repair"),
        ],
        "promoted_with_gates_passed": [
            allowed.allowed,
            allowed_registry.active_version("verify_repair"),
        ],
        "host_hooks_saw_promotions": getattr(host_hooks, "promotions", None),
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "graph_template_soft_points": _run_graph_template_soft_points,
    "independent_review_template": _run_independent_review_template,
    "node_components": _run_node_components,
    "traversal_contract": _run_traversal_contract,
    "recipe_as_tool": _run_recipe_as_tool,
    "initialize_preflight_template": _run_initialize_preflight_template,
    "environment_repair_recipe": _run_environment_repair_recipe,
    "verify_repair_recipe": _run_verify_repair_recipe,
    "recipe_namespace_tile": _run_recipe_namespace_tile,
    "bounded_retry_recipe": _run_bounded_retry_recipe,
    "recipe_registry_versions": _run_recipe_registry_versions,
    "soft_point_evolution_allowlist": _run_soft_point_evolution_allowlist,
    "registry_only_compose": _run_registry_only_compose,
    "produce_critique_refine_recipe": _run_produce_critique_refine_recipe,
    "recipe_final_test_gate": _run_recipe_final_test_gate,
    "recipe_evolution_candidates": _run_recipe_evolution_candidates,
    "safety_eval_recipe": _run_safety_eval_recipe,
    "recipe_port_search": _run_recipe_port_search,
    "evolution_ownership_split": _run_evolution_ownership_split,
}
