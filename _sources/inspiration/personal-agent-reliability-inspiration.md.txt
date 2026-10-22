# Inspiration: Reliable Personal Agent Execution Patterns

Status: proposal; not implemented by this document.
Source: Hamza Khalid (@humzaakhalid), "100 Tips & Tricks for Building Your Personal AI Agent", X post, July 25 (as presented by the author). https://x.com/humzaakhalid/status/2080954210456334798?s=46
Source scope: numbered recommendations 1–85 plus the concluding fifteen priority recommendations, as supplied in the source text. These are experience reports, not independently verified benchmarks.

## Motivation
An always-on agent must make the *execution system*, rather than a language-model prompt, responsible for invariants. MechaHarness owns reusable graph primitives and recipes, not June's personal identity, memory content, or scheduling policy.

## Proposed requirements and acceptance scenarios
- **MH-PA-01: Typed provenance and freshness** (tips 6, 7, 65; priority 7–8). Tool results can carry source, observed_at, fetched_at, expiry/freshness policy, and degraded/stale status. A graph can reject stale evidence before an external decision. Test: eight-day-old CRM cache cannot be silently presented as current.
- **MH-PA-02: Authority policy gate** (tips 39–42, 69–71, 73; priority 1–2, 11–14). Hard rules are enforced outside model text. Gate actions by capability, reversibility, impact, source trust, and explicit approval. Test: untrusted mobile/forwarded content cannot authorize an external send; a reversible but high-impact trade still requires the configured authority.
- **MH-PA-03: Recipe contracts** (tips 17–21, 27–30). Register reusable subgraphs with typed inputs/outputs, applicability and exclusion predicates, budgets, score/plateau termination, and traceable outcomes. Initial recipes: produce-critique-refine; adversarial review; three-round council with recorded dissent. Council is optional, not default.
- **MH-PA-04: Delegation and handoff** (tips 23–26, 31–32). Delegated nodes receive goals, relevant evidence, exclusions, risks, expected verdict schema, and provenance. Catch-all routing is logged for coverage audits. Test: handoff contains sufficient state for independent resumption.
- **MH-PA-05: Checkpoint-compatible execution** (tips 33–34, 76–77). Persist recipe progress at stable checkpoints, including conflict resolution outcomes, idempotency markers, pending approvals, and error counts. Test crash recovery at each transition without replaying irreversible effects.
- **MH-PA-06: Deterministic alert/error rules** (tips 37, 47, 76). Rule evaluation and escalation are deterministic; models may propose actions but do not decide whether a threshold fired. Test once/log, repeated/surface, persistent/propose repair.
- **MH-PA-07: Correction-to-test feedback** (tips 38, 74, 77–79; priority 15). Capture corrections as structured candidate specification debt, link to failing scenarios, and require review before changing policies. Regression tests verify changes.
- **MH-PA-08: Observability and audit** (tips 19, 78–79). Record recipe selection, model/tool usage, latency/cost, freshness, policy decisions, retries, and failure classifications. Make quarterly audit possible without reading entire transcripts.

## Architecture boundaries
June supplies principal preferences, identity, domain memory, scheduling, and proactive prioritization. MechaHarness exposes execution interfaces and generic recipes. home_network hosts supporting state/backup/health infrastructure. Do not make Markdown the only persistence substrate; keep human-readable specifications in git and transactional state in suitable stores. Do not indiscriminately load all memory into model context.

## Open questions / TODO
- [ ] Align authority gate with current graph hard/soft node resolution and precedence.
- [ ] Define provenance/freshness schema and per-source policy resolution.
- [ ] Define graph recipe registry, activation and NOT-FOR predicates, and versioning.
- [ ] Choose durable checkpoint schema and replay/idempotency guarantees.
- [ ] Define earned-autonomy evidence contract, keeping promotion approval outside the model.
- [ ] Map requirements to existing implementations and avoid duplicate primitives.

## Suggested order
1. Inspect current code and tests for overlap.
2. Introduce provenance and policy contracts with negative tests.
3. Implement one refinement recipe and structured handoff.
4. Add checkpoint/recovery tests and deterministic alert evaluation.
5. Add correction capture and audit reporting.

Attribution: Concepts adapted from Hamza Khalid's post above; architecture choices and acceptance criteria are project-specific interpretations.
