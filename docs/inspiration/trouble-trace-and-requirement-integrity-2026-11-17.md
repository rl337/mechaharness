# Trouble inspiration: evidence-layered harness evaluation and requirement-integrity handoffs

> Research and **candidate** acceptance extensions only. This document is not a claim that source benchmarks have been reproduced.
>
> Accepted walks: `taloneth_layered_eval` (MH-TRACE-01) and the requirement-admission half of `fangore_admit_authority` (MH-REQ-01).
>
> Reviewed: 2026-11-17. Local baseline: [MechaHarness main @ 2420dfe](https://github.com/rl337/mechaharness/tree/2420dfe01febbc11b18fd42cf0d7d18bcc7f43e3).

## Source map and capability identity

**TR-20261117-TRACETRIAL** (verification/evaluation/self-improvement; test/evaluation)
- Trouble: https://rl337.org/trouble/posts/2122354299191660973.html (2026-11-16); originating post https://x.com/traceliteai/status/2122354299191660973
- Primary code: [TraceTrial-Bench @ 98a3813](https://github.com/TraceLite-AI/TraceTrial-Bench/tree/98a381307184fa4212db3466b21b4c92a031940b), especially [README](https://github.com/TraceLite-AI/TraceTrial-Bench/blob/98a381307184fa4212db3466b21b4c92a031940b/README.md), [harness_tracer](https://github.com/TraceLite-AI/TraceTrial-Bench/tree/98a381307184fa4212db3466b21b4c92a031940b/harness_tracer), [verifier](https://github.com/TraceLite-AI/TraceTrial-Bench/tree/98a381307184fa4212db3466b21b4c92a031940b/verifier), [Task](https://github.com/TraceLite-AI/TraceTrial-Bench/tree/98a381307184fa4212db3466b21b4c92a031940b/Task); paper https://arxiv.org/abs/2610.32285; report https://tracelite.ai/trial-by-trace.html.
- Upstream claims: 95 mechanism-focused tasks, seven harness-reliability dimensions (context, execution, governance, lifecycle, observability, tools, verification), 4 harnesses × 9 models × 95 selected runs. 31.1% of selected runs succeeded on agent deliverables despite at least one harness-criterion failure; 8.4% passed both layers completely. These are **source-reported**, model/harness-specific, one retained run per cell, not local measurements.
- Mechanism: trace native behaviour without modifying the harness, normalize observations, collect independent runtime/context/harness evidence, score **Agent** task outcomes separately from **Harness** contract fidelity, and attribute failures using explicit event chains. A model may work around a harness defect; a correctly functioning harness may deliver an unsuccessful model task. Correlation or a plausible attribution path alone does not prove causality.

**TR-20261117-SIGNED-REQ** (context/memory/knowledge and agent orchestration; acceptance/security)
- Trouble: https://rl337.org/trouble/posts/2120138872872956039.html (2026-11-10); original https://x.com/andriibbarabash/status/2120138872872956039
- Primary preprint: [Signed but Not Safe: Requirement Integrity in Multi-Agent LLM Handoffs](https://arxiv.org/abs/2611.07483), Chen et al., 2026-11-05. Code/task banks reportedly available from authors on request, **not independently inspected**.
- Mechanism: author extracts each source requirement as a verbatim quote and checkable predicate, signs a structured manifest using HMAC-SHA256, verifies later handoff integrity and deterministic merge decisions. In the paper's synthetic preregistered experiment with Qwen3-8B, unsafe commits decreased from 69.4% for a plain handoff to 9.0% for signed manifests. Crucial caveat: a pre-sign injection raised the signed system's violations from 14.6% to 37.5%; a signature preserves an already corrupted extraction. These numbers are attributed research claims, **not a reason to prescribe HMAC as the only valid design**.

## Repository coverage audit (read-only)

| Existing surface | Verified behaviour in inspected source | Specific missing/partial guarantee |
|---|---|---|
| [trace_reconciliation.py](https://github.com/rl337/mechaharness/blob/2420dfe01febbc11b18fd42cf0d7d18bcc7f43e3/src/mechaharness/trace_reconciliation.py) | Reconciles event identifiers and hashes from independent observation surfaces, reporting agree/missing/conflict | Does not itself declare paired task/harness acceptance scores or evidence-backed attribution |
| [eval_evidence.py](https://github.com/rl337/mechaharness/blob/2420dfe01febbc11b18fd42cf0d7d18bcc7f43e3/src/mechaharness/eval_evidence.py) | Evidence refs and atomic claims with pass/fail/unknown | No inspected typed outcome linking a failed harness obligation to an observed, independently verified user outcome |
| [eval_matrix.py](https://github.com/rl337/mechaharness/blob/2420dfe01febbc11b18fd42cf0d7d18bcc7f43e3/src/mechaharness/eval_matrix.py) | Preserves model × harness × task-family cells and task success; prevents average-only collapse (MH-MHRL-17) | Cell aggregates currently reflect task-trial success, not explicitly two independently evaluated layers |
| [evaluation_outcome.py](https://github.com/rl337/mechaharness/blob/main/src/mechaharness/evaluation_outcome.py), [cross_harness_failure.py](https://github.com/rl337/mechaharness/blob/main/src/mechaharness/cross_harness_failure.py), [trace_envelope.py](https://github.com/rl337/mechaharness/blob/main/src/mechaharness/trace_envelope.py) | Already distinguish evaluator/infrastructure failures and hold failure/trace records | Reuse these primitives; confirm full story-fixture coverage before implementation |
| [handoff_record.py](https://github.com/rl337/mechaharness/blob/2420dfe01febbc11b18fd42cf0d7d18bcc7f43e3/src/mechaharness/handoff_record.py) | Goals, exclusions, rationale, evidence refs, verdict and progress preserved in typed record | Inspected model has no explicit *quoted-origin requirement + checkable predicate + source-authority* extraction record |
| [stepped-graph-execution.md](https://github.com/rl337/mechaharness/blob/main/docs/requirements/stepped-graph-execution.md) | Pauses and resumes with authority revalidation (SG-01..10) | Supports tests of altered requirements between steps; do not duplicate its resume contract |
| [user stories guide](https://github.com/rl337/mechaharness/blob/main/docs/guides/user-stories.md) | Generated from suites and stages under tests/fixtures/models; Fangore, Taloneth, Nubble personas | Candidate stories below require acceptance fixture selection and specification refinement before normative promotion |

This is **partial specification / test coverage**, not an allegation that MechaHarness has no tracing, evaluation or handoff machinery. Existing open draft [PR #58](https://github.com/rl337/mechaharness/pull/58) covers resource-scoped grants and memory authority; [PR #59](https://github.com/rl337/mechaharness/pull/59) covers prompt-cache attribution. Neither is replaced here.

## Candidate MH-TRACE-01: separate harness fidelity from agent/task success

**Persona / outcome.** As Taloneth, an ML engineer comparing models and graph recipes, I need each evaluation to report both whether the requested task succeeded and whether the harness faithfully executed its obligations, so that a lucky task result does not hide a transport, context, governance or lifecycle defect.

**Scope.** Extend existing eval-matrix, atomic-evidence, trace-reconciliation and evaluation-outcome acceptance. A new generic evaluator is not required if the existing types can be composed. Preserve the independent evidence stream used for every verdict and record missing/contested observations as unknown.

**Offline acceptance specification (fixtures planned, not created):**
1. **Task passes, harness fails:** simulated tool API discards an error but worker produces a correct file through a fallback. Independent oracle verifies file; harness obligation fails; both results survive in reports and the combined result is not clean.
2. **Task fails, harness passes:** valid tool delivery and policy enforcement but wrong output; score agent fail/harness pass. Do not blame infrastructure.
3. **Both fail:** executor drops required context and final output is wrong; each judgement backed by distinct refs. Mark causal attribution *hypothesis* unless trace sequence plus mechanism-specific evidence supports it.
4. **Insufficient observation:** missing runtime audit or unreconciled hash prevents a hard harness-pass; no empty trace is interpreted as compliant. Infrastructure/evaluator failure remains unscored rather than task failure.
5. **Restart/retry:** one run with two attempts retains attempt IDs; repeated events and escaped errors are not counted twice. Claim evidence points to the exact attempt/observation surface.
6. **Cross model/recipe:** compare identical frozen tasks and criteria across two harness fingerprints; report model and harness metrics independently, per-cell coverage, unknown rates and missing evidence, not one opaque rank.
7. **Negative controls:** tamper one event digest and omit one required event; require conflict/missing state with inspectable evidence, without changing the user outcome oracle.

**Proposed tests:** use Taloneth's static fixture suite in tests/fixtures/models; add compositional unit tests to existing eval/trace tests; require a pinned task manifest and verifier-only fixtures. For live comparisons keep matched budgets, models, task sources and judge versions, and label non-equivalent runs. No benchmark results are asserted until executed.

**Design questions:** Should a paired result be a view derived from Claim refs, or a new typed record? Is failure attribution a separately reviewed record? Which runtime effects can be independently verified by hosts without vendor-specific adapters? Preserve the current evaluation_outcome failure taxonomy, do not collapse unknown to fail.

## Candidate MH-REQ-01: preserve source-authoritative requirements across handoffs

**Persona / outcome.** As Fangore, an app developer delegating graph work to agents, I need a transferred or compacted requirement to remain linked to the actual trusted request and retain its testable constraints, so that a reviewer cannot be persuaded by a perfectly valid signature on a false requirement.

**Coverage classification.** Partially covered by HandoffRecord goals/exclusions, provenance, source-authority and MH-DOTS approval invariants. The gap is *admission of requirements before they enter a signed/checkable manifest*, not generic provenance or another signing library.

**Offline acceptance specification:**
1. The user supplies a requirement and exclusion. The extraction stage records a source ID, exact supporting span/quote, trust class, checkable predicate and explicit uncertainty for each requirement. The handoff presents both a concise summary and these anchored assertions.
2. Retrieved research contains an instruction to remove a user exclusion. Such text is evidence, never promoted into the authoritative requirement list, even if later signed.
3. An attacker changes a requirement **after** manifest creation. Integrity verification rejects the mutated handoff; benign reserialization that preserves canonical semantics remains valid.
4. A malformed or ambiguous source instruction causes an unresolved/ask-human outcome; do not manufacture a predicate or silently weaken it.
5. A downstream reviewer receives a syntactically valid but source-mismatched manifest. Source fidelity check rejects it before the reviewer can approve an effect.
6. Restart/compaction preserves anchors and original authority; revoked or changed instructions trigger new validation rather than reusing prior approval.
7. Positive control: legitimate user-authorized requirement update proceeds, preserves version history and does not trigger permanent false veto.

**Design alternatives:** structured source-bound claims plus deterministic verifier; content hashes of immutable original user request; signed manifests for transport integrity; authority-typed envelopes. **Signing is optional** if trusted storage and integrity checks provide equivalent guarantees. Risk is specifically extraction contamination prior to any transport-signature check.

**Implementation investigation:** map current HandoffRecord and context authority envelopes to source anchors; find nearest Fangore story fixture and existing tests for authorization epoch and source provenance; distinguish one-shot handoff from June's durable application state. Do not add HMAC key lifecycle to MH without an explicit host need.

## Adoption / boundaries

Stories are **candidate requirements**. Existing canonical MechaHarness user stories are YAML suite stages under tests/fixtures/models and generated docs/guides/user-stories.md. An implementation agent should inspect actual fixture IDs, refine one relevant Fangore and one Taloneth acceptance stage, run the story guide sync commands and offline suite, then separately evaluate live adapters; do not hand-edit the generated guide. This PR does not add untested YAML stages or alter production code.

No external benchmarks, Docker tasks, signed-manifest attacks or media generators were run. Reassess repo state and upstream releases before adopting.