# Self-revising recipe evolution requirements map

Maps themes from
[self-revising-recipe-evolution.md](./self-revising-recipe-evolution.md)
to stable backlog IDs (`MH-SR-*`), modules, and user stories.

**Coverage:** *story* means a persona story exercises an integrated library path;
*partial* means helpers/schemas ship but auto-wiring or host integration remains
open (see Gaps); *gap* means the product contract is not shipped. Inspiration
status: **proposal** (source screenshot unverified); not an accepted
requirement. Do not treat screenshot performance claims as benchmarks.

**Ownership:** MechaHarness owns recipe registry, typed composition, validation,
deterministic execution, evaluation substrate, versioning/checkpoints, rollback
hooks, observability, and safety gates. The AI assistant host owns workload selection,
orchestration, scheduling, experiment budgets, evaluation campaigns, and
promotion policy. home_network owns sandboxed workers and experiment stores.
JuneSpark may supply inference for proposals/evals within local budgets.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| MH-SR-01 | Versioned replaceable recipe artifacts | `graph_templates/base.py`, `GraphTemplateRegistry`, `recipe_runner.py` | story | `fangore_insp_template_incubation`, `fangore_insp_recipe_version_pointer` | — |
| MH-SR-02 | Registry-only dynamic composition | `graph_templates/`, `GraphTemplateRegistry.composition_violations`, nest / tile / `embed_recipe_as_tool` | story | `fangore_recipe_namespace_tile`, `fangore_recipe_as_tool`, `fangore_insp_registry_only_compose` | Hosts opt in to the gate; the executor does not force registry-only graphs |
| MH-SR-03 | Soft optimizable vs hard immutable | `SoftPoint.evolvable`, `GraphTemplate.assert_evolution_allowed`, grants soft-vs-hard, node components | story | `fangore_graph_template_soft_points`, `fangore_insp_soft_vs_hard`, `fangore_insp_soft_evolution_allowlist` | — |
| MH-SR-04 | Typed-port composition search | `recipe_lifecycle/recipe_port_search.py`, `GraphTemplateRegistry.search_compatible`, `isolation/isolation_contract.py` (`TemplateIOContract`), `GraphTemplate.io_contract` | story | `fangore_insp_recipe_port_search` | Only recipes that declare `io_contract` are searchable (`safety_eval`, `independent_review`, `produce_critique_refine`, `verify_repair`, `fan_out_aggregate`); search returns catalog ids and never synthesizes graphs |
| MH-SR-05 | Immutable lineage + promote/rollback | `GraphTemplateRegistry` versions / lineage / evaluations / promote / rollback; `ResearchLab.promote`/`rollback` | story | `fangore_insp_recipe_lineage_promote` | Soft→hard instruction promotion is MH-PA-07 / WalkingLabs (`taloneth_insp_rule_promotion`), not recipe lineage |
| MH-SR-06 | Candidate evolution loop | `recipe_lifecycle/recipe_evolution.py`, `research.ResearchLab`, `harness_experiment`, `evaluator`, `objective_policy` | partial | `taloneth_atk_research_reject`, `taloneth_insp_recipe_evolution_loop` | Pure propose / validate / select helpers; isolated evaluation and the campaign loop are host-driven (no executor ships by design) |
| MH-SR-07 | Held-out final-test release gate | `evaluator.py` (`require_held_out_final_test`), `research.ResearchLab.promote`, `GraphTemplateRegistry.promote_with_final_test`, decision-export anti-leakage | partial | `taloneth_insp_evaluator_compose`, `taloneth_insp_recipe_final_test_gate` | Plain `GraphTemplateRegistry.promote` remains an ungated pointer move for hosts with their own gate |
| MH-SR-08 | Conflict neighbors / cycle / checkpoint | `decision_conflict_checkpoint.py`, `ExecutionGraph.concurrent_write_conflicts`, `StopContract`, `CheckpointStore`, decision-plane | partial | `fangore_tdr_crash_after_accept_before_record`, `fangore_decision_plane_policy`, `fangore_insp_decision_conflict_checkpoint` | Pure helpers; the graph executor does not call them, so hosts drive the revisit loop and checkpoint |
| MH-SR-09 | the AI assistant host↔MH evolution ownership | `recipe_lifecycle/recipe_promotion_policy.py`, `recipe_lifecycle/evolution_campaign_hooks.py`, `host_apis.py`, `di.py` (`get_recipe_promotion_policy`, `get_evolution_campaign_hooks`), recipes-and-decision-plane.md | partial | `fangore_insp_evolution_ownership_split` | Hooks are injectables with no-op defaults; `promote_recipe(..., hooks)` calls `on_promotion` after a successful pointer move. Workload selection, budgets, and `on_proposal` stay host-driven |

## Related inspirations

- [Personal agent reliability](./personal-agent-reliability-inspiration.md) — recipe contracts, correction feedback
- [OpenAI Dots agent safety](./openai-dots-agent-safety-inspiration.md) — safety evaluation recipes
- [Durable graph generators (IoC)](./durable-graph-generators-inversion-of-control.md) — how an active recipe run is driven across yields and drivers (orthogonal to offline recipe evolution)
