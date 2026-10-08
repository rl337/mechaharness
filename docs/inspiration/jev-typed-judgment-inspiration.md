# Jev typed-judgment inspiration for MechaHarness

> Research and candidate user stories. External product claims are attributed;
> Jev is an optional provider, not a dependency. Foundation patterns are
> **implementable on MechaHarness today** via judge types, `JudgementPolicy`,
> and the `decision_plane` Agentic Recipe — not a parallel judgment stack.

Reviewed: 2026-10-08. Status: **inspiration + story backlog**; promote only
novel domain packs and calibration depth beyond existing DP/JDG coverage.

Companion map:
[jev-typed-judgment-requirements-map.md](./jev-typed-judgment-requirements-map.md).

## Sources and attribution

- Arindam Majumder (@Arindam_1729), September 25, 2026, article **“10 projects
  worth building with JEV”** (article text supplied in the originating
  discussion; original article permalink not provided). All ten examples below
  are attributed to this article; locate and add its canonical permalink before
  treating this as a complete source bibliography.
- Diogo Almeida (@CompleteSkeptic), September 15, 2026, Jev announcement quoted
  by Majumder (original post permalink not independently verified).
- TypeSafe, *How to setup Jev: From nothing to a call that returns a decision*,
  September 2026, page 1 supplied as screenshot. Full paper not verified or
  reviewed.
- TypeSafe product/API: https://typesafe.ai/ and
  https://api.typesafe.ai/redoc (API contract and availability require
  verification at implementation time).
- Related internal documentation: [graph templates](../reference/graph-templates.md),
  [typed decision plane](../reference/graph-templates/decision-plane.md),
  [recipes and decision plane requirements](../requirements/recipes-and-decision-plane.md),
  [developer-blog inspiration](./dev-blog-inspiration.md),
  [inspiration requirements map](./requirements-map.md),
  [multi-harness RL inspiration](./multi-harness-rl-inspiration.md).

## Thesis

Move frequent narrow semantic judgments out of long-form generation and into
**typed, bounded, testable decision calls**. Deterministic harness code owns
authorization, thresholds, actions, recovery, and auditing. A judge model is
not a security principal, ground-truth oracle, or source of calibrated
probabilities by default.

Do not confuse a categorical response with a validated decision. Compare Jev
with local small models and larger models using the same tasks and fixtures.

## Existing MechaHarness ownership (implementable now)

| Concern | MechaHarness surface |
|---------|----------------------|
| Typed questions / signals | `mechaharness.inference.judge` (`Choice` / `Noul` / `Score`) |
| Batch judgments | `evaluate_decision_batch` / multi-question `JudgeRequest` |
| Code-owned policy + abstain | `JudgementPolicy`, `apply_decision_plane_policy` |
| Provenance / replay | `decision_log`, decision-plane telemetry |
| Hard gates | `AccessControl`, consequence / approval policies |
| Escalation + bounded loops | `decision_plane` escalate exit; `verify_repair` / `bounded_retry` |
| Static fixtures | `FixtureJudgeProvider`, story soft expects |
| Shadow / compare | `compare_shadow_decision` |

MechaHarness owns generic typed-judgment interfaces, graph skeletons/recipes,
replay/evaluation, and execution guarantees. June and other clients own domain
state, concrete tools, user permissions, thresholds, and instantiated
client-specific graphs. Promote a June-born recipe only after removing domain
assumptions.

## Proposed foundation requirements

These map onto shipped DP/JDG/POL surfaces; see the companion requirements map
for story links and residual gaps (calibration depth, domain packs).

- **MH-JEV-01 Typed judgment contract:** Provider-neutral request with bounded
  state, question ID, kind (binary/choice/ordinal score), valid options,
  explicit abstain/uncertain semantics, provenance, and output schema. Validate
  provider responses and expose unsupported capabilities. Do not assume Jev's
  exact API shape matches the conceptual schema.
- **MH-JEV-02 Batch judgments:** Batch independent questions over shared state
  where supported; preserve per-question identity and failure isolation;
  provide sequential fallback. Explicitly handle dependencies rather than
  pretending all judgments are independent.
- **MH-JEV-03 Calibration and abstention:** Separate raw model scores from
  calibrated probabilities and routing thresholds. Record calibration corpus,
  task class, policy version, and uncertainty. Evaluate selective risk/coverage
  and failure costs; confidence alone never grants authorization.
- **MH-JEV-04 Decision provenance/replay:** Persist state fingerprints or
  protected snapshots, question/schema version, model/provider/version, raw
  outputs, decision policy, graph/node IDs, chosen action, and outcome. Replay
  must never repeat side effects; redact sensitive payloads.
- **MH-JEV-05 Hard execution boundary:** Authorization, approval, schema
  validation, resource limits, and irreversible-action restrictions are
  deterministic hard gates. Semantic risk classification can only add review or
  deny, never elevate privileges.
- **MH-JEV-06 Escalation and bounded loops:** Route uncertainty, contradiction,
  invalid output, repeated failure, or budget exhaustion to a stronger
  model/human/fallback. Bound retries and retain reasons.
- **MH-JEV-07 Static-data tests:** Use injected providers and static fixtures;
  test calibration, provider outages, malformed output, ordering, concurrency,
  checkpoint/restart, and crashes before/after decision persistence and
  before/after side-effect execution. Require idempotency keys or reconciliation
  for external effects.
- **MH-JEV-08 Comparative evaluation:** Benchmark Jev, small local models, and
  stronger models on identical corpora. Measure task accuracy, calibration,
  abstention, end-to-end latency, total cost, escalation load, and downstream
  task success; avoid vendor-reported speedup as an acceptance criterion.

## Ten candidate user stories from Majumder's article

Each story is an example of a reusable pattern, not a requirement to integrate
a particular SaaS product. High-priority rows have owning MechaHarness persona
stories that exercise existing `decision_plane` / access infrastructure.

| ID | Story / example | Generic recipe | Priority | Owning story |
|---|---|---|---|---|
| MH-JEV-US01 | Support-ticket team, urgency and escalation routing | classify → score → route | Example | Covered by `fangore_decision_plane_policy` / `fangore_refund_verdict` |
| MH-JEV-US02 | Inbound lead fit and priority | evaluate criteria → score → dispatch | Example | Same triage pattern as US01 |
| MH-JEV-US03 | Comment spam/abuse moderation | multi-label judge → policy → review | Medium | Future host pack |
| MH-JEV-US04 | Claim/citation support check | extract claim/source → entailment → verify | **High** | `fangore_jev_citation_check` |
| MH-JEV-US05 | RAG context selection | retrieve → relevance/trust/freshness → budget assembly | **High** | `fangore_jev_context_picker` |
| MH-JEV-US06 | Semantic PR review against requirements | diff/requirements → atomic checks → escalate | **High** | `fangore_jev_requirements_review` |
| MH-JEV-US07 | Task-specific model/workflow router | inspect request → choose model/tool/graph/human | **High** | `fangore_jev_task_router` |
| MH-JEV-US08 | Agent action safety firewall | propose action → semantic risk → hard policy | **High** | `fangore_jev_action_safety` |
| MH-JEV-US09 | Browser agent reflex controller | observe → bounded action → execute | Experimental | Future |
| MH-JEV-US10 | Game-state action selection | observe → bounded choice → simulate | Benchmark | Future |

Source for **every row**: Majumder's September 25 article supplied in the
conversation, sections 1–10 respectively. Add stable section/post permalinks if
recovered.

## High-priority acceptance-story sketches

### MH-JEV-US04: Citation oracle (`fangore_jev_citation_check`)

Given a source snapshot and an atomic claim, when the judge returns
supported/contradicted/insufficient/unavailable, then the harness preserves
evidence spans and provenance, flags mismatches, and never upgrades unsupported
claims to verified. Tests include 12% vs 40% revenue growth, missing source,
misleading excerpt, and multi-claim sentences.

### MH-JEV-US05: Context picker (`fangore_jev_context_picker`)

Given retrieved candidates and a strict token budget, when
relevance/trust/freshness judgments are returned, then deterministic code
assembles a traceable context within budget. Tests include duplicates, stale
docs, contradictory docs, malicious prompt injections, and fallback when the
judge fails.

### MH-JEV-US06: Requirements-aware code review (`fangore_jev_requirements_review`)

Given a PR diff and applicable user stories, when atomic checks identify
possible requirement/test gaps, then the harness requests focused static tests
or deeper review; it does not mark the PR correct merely because a judge
approves.

### MH-JEV-US07: Model router (`fangore_jev_task_router`)

Given a mixed workload, when the router chooses local small model, frontier
model, deterministic tool, or human, then quality and budget policies are
respected. Test misroutes, provider unavailability, and escalation.

### MH-JEV-US08: Action safety (`fangore_jev_action_safety`)

Given a proposed delete/send/pay/publish action, when semantic classification
disagrees with hard policy, then hard policy always wins. Semantic risk may only
add review or deny — never elevate privileges.

## Experimental stories

- **MH-JEV-EXP01:** Paired benchmark across Jev and local judgment-capable
  models on identical typed tasks.
- **MH-JEV-EXP02:** One broad generative prompt vs decomposed atomic questions.
- **MH-JEV-EXP03:** Browser/game reflex loop with a stronger strategic planner.
- **MH-JEV-EXP04:** Counterfactual replay with side effects disabled.
- **MH-JEV-EXP05:** Crash injection at decision/action boundaries (compose with
  durable-resume requirements).

## Follow-up checklist

1. Recover Majumder's canonical article permalink and original Jev announcement.
2. Keep the requirements map honest as calibration / domain packs deepen.
3. Prefer host soft-point bindings on `decision_plane` before new catalog recipes.
4. Define any Jev-specific adapter only after provider-neutral fixtures exist.
5. Review security, sensitive-data retention, licensing, and provider
   availability before external API experiments.

No credentials or scheduled workflows should be introduced by this
documentation track alone.
