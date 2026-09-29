# Inspiration requirements map

Maps each requirement in
[dev-blog-inspiration.md](./dev-blog-inspiration.md) to the MechaHarness
module that owns it, current gap status, and whether June (orchestrator
client) or MechaHarness implements the surface.

**Ownership reminder:** MechaHarness owns protocols, DI hooks, and
parameterized **graph templates**. June owns scheduler, task runner,
document manager, knowledge graph, and issue tracker — it instantiates
templates and implements providers; it does not own template definitions.

| Req | Topic | Primary module(s) | Status | Owner |
|-----|-------|-------------------|--------|-------|
| 1 | Revisable scaffolding | `harness_experiment.py`, `research.py` | Library experiment surface + retirement hooks | MH; June proposes changes |
| 2 | Linkage vs DI | `linkage_resolver.py`, `operation_registry.py`, `di.py` | Pre-exec graph resolve distinct from injector | MH |
| 3 | Dynamic subgraphs | `graph_template.py`, `graph.py`, `graph_executor.py` | Nested graphs + library templates | MH owns templates |
| 4 | Stop contracts | `stop_contract.py`, `convergence.py` | Required on repeating nodes at linkage | MH |
| 5 | Verification | `verification_policy.py`, `graph.py` oracles | Selection policy + completion gate | MH |
| 6 | Scoped context | `context_provider.py`, `context_experiments.py` | Provider protocol; lazy index | MH protocol; June KG/docs implement |
| 7 | Delegation / envelopes | `capability_envelope.py`, `delegation_policy.py` | Child envelopes; inline vs child policy | MH |
| 8 | Skills / gotchas | `instruction_component.py` | Trigger metrics; promotion via eval | MH metrics; June proposes |
| 9 | Soft vs hard | grants, stop, linkage vs prompts | Documented + mechanically enforced | MH |
| 10 | Independent review | `graph_template.py` review template | Isolated context template | MH |
| 11 | Fix the process | EventLog + failure attribution | Structured attribution on traces | MH; June mines traces |
| 12 | Durable resume | `graph.py` GraphStore, fingerprint | Version fingerprint refuse | MH |
| 13 | Model routing | `routing.py`, envelopes, Completer keys | Node capability needs | MH |
| 14 | Harness hypotheses | `harness_experiment.py`, `research.py` | With/without + version on traces | MH |
| 15 | Risk-scaled autonomy | `consequence.py`, access grants | Consequence class on actions | MH; June product policy |
| 16 | Environment linkage | `core/environment.py`, `linkage_resolver.py` | Env in resolve; repair template | MH |
| 17 | Persistent goals | — | Out of library | **June only** |
| 18 | Advisor | `advisor.py`, `advisor_policy.py` | Non-binding; distinct from escalate | MH |

## June task-runner shape

1. Load persistent goal (June).
2. Pick a MechaHarness `GraphTemplate` and bind host tools / providers / envelope.
3. `LinkageResolver.resolve` → fail closed on missing edges.
4. `GraphExecutor.run` (checkpointed).
5. On wake: re-resolve environment/linkage, then resume if fingerprint matches.

## Soft vs hard (req 9)

| Mechanism | Role |
|-----------|------|
| Advisory context / skills / prompts | Soft guidance |
| Grants, envelopes, stop contracts, linkage, env assert | Hard enforcement |
| Judge signals → `JudgementPolicy.decide` | Hard verdict path (model never grants) |
