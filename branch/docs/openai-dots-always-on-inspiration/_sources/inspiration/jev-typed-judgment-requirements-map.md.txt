# Jev typed-judgment requirements map

Maps backlog items from
[jev-typed-judgment-inspiration.md](./jev-typed-judgment-inspiration.md)
(`MH-JEV-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises the path; *surface* means
types exist with unit/doctest coverage; *partial* / *gap* mean incomplete.

Foundation rows are largely **story** on existing DP/JDG infrastructure.
High-priority domain packs have dedicated stories even when they reuse that
infrastructure.

| ID | Topic | Modules | Library | Story |
|----|-------|---------|---------|-------|
| MH-JEV-01 | Typed judgment contract | `inference/judge.py`, `decision_surfaces.py` | story | `fangore_refund_verdict`, `fangore_decision_plane_recipe` |
| MH-JEV-02 | Batch judgments | `decision_plane_runtime.py`, `JudgeRequest` | story | `fangore_decision_plane_policy`, `taloneth_fixture_judge_batch` |
| MH-JEV-03 | Calibration / abstention | `judgement_policy.py`, DP confidence floor | partial | `fangore_decision_plane_policy` (thresholds); deeper calibration corpus still open |
| MH-JEV-04 | Provenance / replay | `decision_log.py`, DP telemetry | story | `taloneth_policy_replay`, `fangore_decision_plane_telemetry` |
| MH-JEV-05 | Hard execution boundary | `core/access.py`, `consequence.py`, DP envelopes | story | `fangore_tool_gating`, `fangore_jev_action_safety` |
| MH-JEV-06 | Escalation / bounded loops | `decision_plane`, `verify_repair`, `bounded_retry` | story | `fangore_decision_plane_policy`, `fangore_verify_repair_recipe` |
| MH-JEV-07 | Static-data tests | `FixtureJudgeProvider`, story fixtures | story | `taloneth_fixture_judge_batch`, JEV domain stories below |
| MH-JEV-08 | Comparative evaluation | `compare_shadow_decision`, eval matrix | story | `fangore_decision_plane_shadow`, `taloneth_decision_plane_shadow_compare` |
| MH-JEV-US04 | Citation support check | `decision_plane_runtime.py` | story | `fangore_jev_citation_check` |
| MH-JEV-US05 | RAG context picker | `assemble_context_within_budget`, DP batch | story | `fangore_jev_context_picker` |
| MH-JEV-US06 | Requirements-aware review | `decision_plane`, `independent_review` | story | `fangore_jev_requirements_review` |
| MH-JEV-US07 | Task-specific router | `decision_plane`, `routing.py` | story | `fangore_jev_task_router` |
| MH-JEV-US08 | Action safety firewall | `AccessControl` + DP semantic risk | story | `fangore_jev_action_safety` |
| MH-JEV-US01–03 | Triage / lead / moderation packs | host bindings on `decision_plane` | surface | US01 pattern covered by decision-plane policy stories |
| MH-JEV-US09–10 | Browser / game reflex | — | gap | Experimental; not library-owned yet |

## Ownership

**MechaHarness owns:** typed judgment contracts, `decision_plane` recipe/runtime,
code-owned policy helpers, hard access gates, fixture/shadow evaluation,
provenance fields.

**June (or another client) owns:** domain corpora (citations, RAG indexes, PR
requirements), concrete thresholds, permission catalogs, and product-specific
graph realizations.

## Attribution

Follow-on work must keep Majumder / TypeSafe / Jev permalinks in story footnotes
(see each `story.json`), not only a link to this aggregate inspiration document.
Do not treat Jev SaaS availability as an acceptance criterion for library stories.
