# Self-revising recipe evolution requirements map

Maps themes from
[self-revising-recipe-evolution.md](./self-revising-recipe-evolution.md)
to stable backlog IDs (`MH-SR-*`), modules, and user stories.

**Coverage:** *story* means a persona story exercises the native path; *partial*
means important acceptance remains open; *gap* means the product contract is
not shipped. Inspiration status: **proposal** (source screenshot unverified);
not an accepted requirement. Do not treat screenshot performance claims as
benchmarks.

**Ownership:** MechaHarness owns recipe registry, typed composition, validation,
deterministic execution, evaluation substrate, versioning/checkpoints, rollback
hooks, observability, and safety gates. June owns workload selection,
orchestration, scheduling, experiment budgets, evaluation campaigns, and
promotion policy. home_network owns sandboxed workers and experiment stores.
JuneSpark may supply inference for proposals/evals within local budgets.

| ID | Topic | Modules | Library | Story | Gaps |
|----|-------|---------|---------|-------|------|
| MH-SR-01 | Versioned replaceable recipe artifacts | `graph_templates/base.py`, `GraphTemplateRegistry`, `recipe_runner.py` | partial | `fangore_insp_template_incubation`, `fangore_insp_recipe_version_pointer` | Immutable version artifacts with active promotion pointer |
| MH-SR-02 | Registry-only dynamic composition | `graph_templates/`, nest / tile / `embed_recipe_as_tool` | partial | `fangore_recipe_namespace_tile`, `fangore_recipe_as_tool`, `fangore_insp_registry_only_compose` | Production graphs may still be free-form `ExecutionGraph` |
| MH-SR-03 | Soft optimizable vs hard immutable | `SoftPoint`, grants soft-vs-hard, node components | partial | `fangore_graph_template_soft_points`, `fangore_insp_soft_vs_hard`, `fangore_insp_soft_evolution_allowlist` | Declared evolution allowlist for soft fields |
| MH-SR-04 | Typed-port composition search | `isolation_contract.py`, `TemplateIOContract` | gap | `fangore_insp_recipe_port_search` | Automated composition candidate search over catalog ports |
| MH-SR-05 | Immutable lineage + promote/rollback | stamp provenance; `ResearchLab.promote`/`rollback`; `rule_promotion` | partial | `taloneth_insp_rule_promotion`, `fangore_insp_recipe_lineage_promote` | Recipe catalog immutable versions, lineage DAG, pointer rollback |
| MH-SR-06 | Candidate evolution loop | `research.ResearchLab`, `harness_experiment`, `evaluator`, `objective_policy` | partial | `taloneth_atk_research_reject`, `taloneth_insp_recipe_evolution_loop` | Traces → registry-bounded recipe candidates → isolated eval → promote |
| MH-SR-07 | Held-out final-test release gate | `Evaluator.held_out`, decision-export anti-leakage | partial | `taloneth_insp_evaluator_compose`, `taloneth_insp_recipe_final_test_gate` | Mandatory untouched final-test gate for recipe promotion |
| MH-SR-08 | Conflict neighbors / cycle / checkpoint | write/merge conflicts, `StopContract`, `CheckpointStore`, decision-plane | partial | `fangore_transactional_durable_resume`, `fangore_decision_plane_policy`, `fangore_insp_decision_conflict_checkpoint` | Inspiration neighbor-revisit CR loop ≠ current write-scope merge conflicts |
| MH-SR-09 | June↔MH evolution ownership | recipes-and-decision-plane.md, FineEnvs/June maps, DI registry | partial | `fangore_insp_evolution_ownership_split` | Named hooks for June-owned evolution campaigns / promotion policy |

## Related inspirations

- [Personal agent reliability](./personal-agent-reliability-inspiration.md) — recipe contracts, correction feedback
- [OpenAI Dots agent safety](./openai-dots-agent-safety-inspiration.md) — safety evaluation recipes
