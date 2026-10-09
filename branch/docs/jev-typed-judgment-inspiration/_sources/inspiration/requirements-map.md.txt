# Inspiration requirements map

Maps each requirement in
[dev-blog-inspiration.md](./dev-blog-inspiration.md) to MechaHarness modules,
library readiness, and the user-story id that acceptance-tests it (when any).

**Coverage honesty:** a row marked *surface* means types/hooks exist and unit
tests cover them; *story* means a persona story exercises the path; *partial*
means important MUSTs remain open (see Gaps). Req 17 is client-owned.

**Ownership:** MechaHarness owns protocols, DI hooks, parameterized
`GraphTemplate` definitions, and **Agentic Recipes** (concrete catalog
patterns on that substrate). Clients own scheduling, goals, documents,
knowledge graphs, issue trackers, domain recipes, and concrete graph
realizations. See
[Recipes and decision plane](../requirements/recipes-and-decision-plane.md).

| Req | Topic | Modules | Library | Story | Gaps |
|-----|-------|---------|---------|-------|------|
| 1 | Revisable scaffolding | `harness_experiment.py`, `research.py` | story | `taloneth_insp_scaffolding_retire` | Online telemetry / automatic retirement suite |
| 2 | Linkage vs DI | `linkage_resolver.py`, `di.py` | story | `fangore_insp_linkage_preflight` | Operation bind depth; candidate-provider UX polish |
| 3 | Dynamic subgraphs / recipes | `graph_templates/` (Agentic Recipes), `graph_executor.py` | story | `fangore_insp_dynamic_subgraph` | I/O contracts + child budget share; recipe tiling readability |
| 4 | Stop contracts | `stop_contract.py`, `convergence.py` | story | `fangore_insp_stop_contract` | Full stop-field validation matrix |
| 5 | Verification | `verification_policy.py`, `graph.py` | story | `fangore_insp_verification_gate` | Impact-based selection observability |
| 6 | Scoped context | `context_provider.py`, `context_experiments.py` | story | `fangore_insp_context_provider` | Default harness path always uses providers |
| 7 | Delegation / envelopes | `capability_envelope.py`, `delegation_policy.py` | story | `fangore_insp_capability_envelope` | Cancel/supersede; coordination cost telemetry |
| 8 | Skills / gotchas | `instruction_component.py` | story | `fangore_insp_instruction_gotchas` | Eval promotion path depth |
| 9 | Soft vs hard | grants, stop, linkage | story | `fangore_insp_soft_vs_hard` | — |
| 10 | Independent review | `graph_templates/independent_review.py` | story | `fangore_insp_independent_review` | Multi-reviewer aggregation runners |
| 11 | Fix the process | `failure_attribution.py`, EventLog | story | `fangore_insp_failure_attribution` | Cross-run mining beyond unit helpers |
| 12 | Durable resume | `graph.py`, `checkpoint_store.py`, `sqlite_checkpoint_store.py`, `external_effect.py`, fingerprint | story | `fangore_insp_durable_resume`, `fangore_transactional_durable_resume` | — |
| 13 | Model routing | `routing.py` | story | `nubble_insp_model_routing` | Cache-transfer / energy frontier |
| 14 | Harness hypotheses | `harness_experiment.py`, `research.py` | story | `taloneth_insp_harness_hypothesis` | Harness version always on traces |
| 15 | Risk-scaled autonomy | `consequence.py` | story | `fangore_insp_risk_autonomy` | Wired into AccessControl path |
| 16 | Environment linkage | `environment.py`, linkage, env template | story | `nubble_insp_environment_linkage` | Secrets/binaries structured failures |
| 17 | Persistent goals | resume / linkage hooks | partial | `fangore_insp_wake_reresolve` | Goal store remains client-owned |
| 18 | Advisor | `advisor.py` | story | `fangore_insp_sparse_advisor` | Linkage participation; follow/reject on traces |
| 19 | Template / recipe incubation | `graph_templates/` SoftPoint + stamp; Agentic Recipe catalog | story | `fangore_insp_template_incubation` | Promote/demote evidence; story names catalog id |
| 20 | Lifecycle interception | `lifecycle_extension.py`, harness/graph seams | story | `fangore_insp_lifecycle_observe`, `…_rewrite`, `…_block`, `…_replace`, `…_graph_observe` | Wrap mode; scaffolding migration into extensions |

## Soft vs hard (req 9)

| Mechanism | Role |
|-----------|------|
| Advisory context / skills / prompts | Soft guidance |
| Grants, envelopes, stop contracts, linkage, env assert | Hard enforcement |
| Judge signals → `JudgementPolicy.decide` | Hard verdict path (model never grants) |
