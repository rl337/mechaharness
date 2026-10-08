# Jev typed-judgment inspiration for MechaHarness

> Research and candidate user stories, not an implementation specification. External product claims and examples are attributed; Jev is an optional provider, not a dependency.

Reviewed: 2026-10-08. Status: **follow-up backlog, no implementation authorized by this document**.

## Sources and attribution

- Arindam Majumder (@Arindam_1729), September 25, 2026, article **“10 projects worth building with JEV”** (article text supplied in the originating discussion; original article permalink not provided). All ten examples below are attributed to this article; locate and add its canonical permalink before treating this as a complete source bibliography.
- Diogo Almeida (@CompleteSkeptic), September 15, 2026, Jev announcement quoted by Majumder (original post permalink not independently verified).
- TypeSafe, *How to setup Jev: From nothing to a call that returns a decision*, September 2026, page 1 supplied as screenshot. Full paper not verified or reviewed.
- TypeSafe product/API: https://typesafe.ai/ and https://api.typesafe.ai/redoc (API contract and availability require verification at implementation time).
- Related internal documentation: [graph templates](../reference/graph-templates.md), [developer-blog inspiration](./dev-blog-inspiration.md), [inspiration requirements map](./requirements-map.md), [multi-harness RL inspiration](./multi-harness-rl-inspiration.md).

## Thesis

Move frequent narrow semantic judgments out of long-form generation and into **typed, bounded, testable decision calls**. Deterministic harness code owns authorization, thresholds, actions, recovery, and auditing. A judge model is not a security principal, ground-truth oracle, or source of calibrated probabilities by default.

Do not confuse a categorical response with a validated decision. Compare Jev with local small models and larger models using the same tasks and fixtures.

## Existing MechaHarness overlap and ownership

The repository already documents parameterized graph templates, soft bindings, linkage resolution, verify/repair, independent review, model routing inspiration, traces and resumable execution. These are **architectural overlaps**, not proof that typed judgment batching, confidence calibration, or all ten workflows already work. Audit actual code and tests before claiming coverage.

MechaHarness should own generic typed-judgment interfaces, graph skeletons/recipes, replay/evaluation, and execution guarantees. June and other clients own domain state, concrete tools, user permissions, thresholds, and instantiated client-specific graphs. Promote a June-born recipe only after removing domain assumptions.

## Proposed foundation requirements

- **MH-JEV-01 Typed judgment contract:** Provider-neutral request with bounded state, question ID, kind (binary/choice/ordinal score), valid options, explicit abstain/uncertain semantics, provenance, and output schema. Validate provider responses and expose unsupported capabilities. Do not assume Jev's exact API shape matches the conceptual schema.
- **MH-JEV-02 Batch judgments:** Batch independent questions over shared state where supported; preserve per-question identity and failure isolation; provide sequential fallback. Explicitly handle dependencies rather than pretending all judgments are independent.
- **MH-JEV-03 Calibration and abstention:** Separate raw model scores from calibrated probabilities and routing thresholds. Record calibration corpus, task class, policy version, and uncertainty. Evaluate selective risk/coverage and failure costs; confidence alone never grants authorization.
- **MH-JEV-04 Decision provenance/replay:** Persist state fingerprints or protected snapshots, question/schema version, model/provider/version, raw outputs, decision policy, graph/node IDs, chosen action, and outcome. Replay must never repeat side effects; redact sensitive payloads.
- **MH-JEV-05 Hard execution boundary:** Authorization, approval, schema validation, resource limits, and irreversible-action restrictions are deterministic hard gates. Semantic risk classification can only add review or deny, never elevate privileges.
- **MH-JEV-06 Escalation and bounded loops:** Route uncertainty, contradiction, invalid output, repeated failure, or budget exhaustion to a stronger model/human/fallback. Bound retries and retain reasons.
- **MH-JEV-07 Static-data tests:** Use injected providers and static fixtures; test calibration, provider outages, malformed output, ordering, concurrency, checkpoint/restart, and crashes before/after decision persistence and before/after side-effect execution. Require idempotency keys or reconciliation for external effects.
- **MH-JEV-08 Comparative evaluation:** Benchmark Jev, small local models, and stronger models on identical corpora. Measure task accuracy, calibration, abstention, end-to-end latency, total cost, escalation load, and downstream task success; avoid vendor-reported speedup as an acceptance criterion.

## Ten candidate user stories from Majumder's article

Each story is an example of a reusable pattern, not a requirement to integrate a particular SaaS product.

| ID | Story / example | Generic recipe | Suggested priority | Evidence and caution |
|---|---|---|---|---|
| MH-JEV-US01 | Support-ticket team, urgency and escalation routing | classify → score → route | Example | Avoid inferring user sentiment as fact; uncertain routes escalate |
| MH-JEV-US02 | Inbound lead fit and priority | evaluate criteria → score → dispatch | Example | Evaluate fairness, consent, and business-specific policy |
| MH-JEV-US03 | Comment spam/abuse moderation | multi-label judge → policy → review | Medium | False positives and adversarial text require human appeal |
| MH-JEV-US04 | Claim/citation support check | extract claim/source → entailment/contradiction/unknown → verify | **High** | Unavailable sources and partial support must not be treated as verified |
| MH-JEV-US05 | RAG context selection | retrieve → relevance/freshness/trust judgments → deterministic budget assembly | **High** | Untrusted retrieved instructions remain data, not instructions |
| MH-JEV-US06 | Semantic PR review against requirements | diff/requirements → atomic checks → test selection/escalation | **High** | Static tests and human review establish correctness, not judge confidence |
| MH-JEV-US07 | Task-specific model/workflow router | inspect request → choose model/tool/graph/human | **High** | Evaluate quality-adjusted routing, not merely cheapest selection |
| MH-JEV-US08 | Agent action safety firewall | propose action → semantic risk → hard policy → approve/deny | **High** | Never let a judge grant permissions |
| MH-JEV-US09 | Browser agent reflex controller | observe compact state → select bounded action → execute → observe | Experimental | Detect loops, UI drift, unsafe clicks, and planning dead ends |
| MH-JEV-US10 | Game-state action selection | observe → bounded choice → simulate → score | Benchmark | Useful repeatable environment, not proof of real-world agent reliability |

Source for **every row**: Majumder's September 25 article supplied in the conversation, sections 1–10 respectively. Add stable section/post permalinks if recovered.

## High-priority acceptance-story sketches

### MH-JEV-US04: Citation oracle
Given a source snapshot and an atomic claim, when the judge returns supported/contradicted/insufficient/unavailable, then the harness preserves evidence spans and provenance, flags mismatches, and never upgrades unsupported claims to verified. Tests include 12% vs 40% revenue growth, missing source, misleading excerpt, and multi-claim sentences.

### MH-JEV-US05: Context picker
Given 20 retrieved candidates and a strict token budget, when relevance/trust/freshness judgments are returned, then deterministic code assembles a traceable context within budget. Tests include duplicates, stale docs, contradictory docs, malicious prompt injections, and fallback when the judge fails. Compare against simple deterministic ranking.

### MH-JEV-US06: Requirements-aware code review
Given a PR diff and applicable user stories, when atomic checks identify possible requirement/test gaps, then the harness requests focused static tests or deeper review; it does not mark the PR correct merely because a judge approves. Tests include resumable graph side effects and missing crash-location tests.

### MH-JEV-US07: Model router
Given a mixed workload, when the router chooses local small model, frontier model, deterministic tool, or human, then quality and budget policies are respected. Test misroutes, provider unavailability, latency/cost, and escalation; avoid a generic gateway masquerading as task-aware routing.

### MH-JEV-US08: Action safety
Given a proposed delete/send/pay/publish action, when semantic classification disagrees with hard policy, then hard policy always wins. Approval state must persist safely across crash/restart, and execution must be idempotent or reconciled.

## Experimental stories

- **MH-JEV-EXP01:** Paired benchmark across Jev and local 500M–1B (and larger) judgment-capable models on identical typed tasks; record quality, calibration, latency, batching gain, and cost.
- **MH-JEV-EXP02:** Compare one broad generative prompt vs decomposed atomic questions, holding data and task constant; measure downstream success and total overhead.
- **MH-JEV-EXP03:** Browser/game reflex loop with a stronger strategic planner; measure progress, loop detection, recovery, and escalation frequency.
- **MH-JEV-EXP04:** Counterfactual replay of model and threshold changes using persisted decisions with all side effects disabled.
- **MH-JEV-EXP05:** Crash injection at every boundary: before inference, after response, before decision commit, after commit, before action, during action, after action, before checkpoint. Verify exactly-once *effect* where external systems support idempotency; otherwise explicitly reconcile ambiguous outcomes.

## Follow-up checklist

1. Recover Majumder's canonical article permalink and original Jev announcement; obtain full setup PDF if available.
2. Audit code and tests against MH-JEV-01..08; mark each as implemented/partial/gap with file and test links. Do not assume absence or completion from this inspiration note.
3. Choose first thin vertical slice: citation checking or RAG context selection.
4. Define provider-neutral schema, calibration corpus, and injected static test provider before any Jev-specific adapter.
5. Draft concrete MechaHarness user stories and acceptance fixtures; keep application-specific realizations in June.
6. Review security, sensitive-data retention, licensing, and provider availability before external API experiments.

No dependencies, executable behavior, credentials, or scheduled workflows should be introduced by this documentation-only PR.
