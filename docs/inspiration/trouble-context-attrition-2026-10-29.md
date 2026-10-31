# Trouble inspiration: evidence attrition across inference boundaries

Status: **research and candidate user-story extensions**, not a new normative API or implementation.
Discovery date: 2026-10-29. Capability ID: **TR-20261029-CONTEXT-ATTRITION**.
Owner: **MechaHarness** (generic context compilation, compaction, inference envelopes, observability and acceptance).

## Source map and claims

- Curated Trouble entry: https://rl337.org/trouble/posts/2115618251023536321.html ; archived source JSON: https://github.com/rl337/trouble/blob/main/posts/2026/10/29/2115618251023536321.json ; original post: https://x.com/ComputerPapers/status/2115618251023536321
- Sehgal, Panahandeh and Ezzati-Jivan, *Context Is a Pipeline, Not a Window: Information Attrition in LLM Agent Harnesses*, submitted 2026-10-26, arXiv v1: https://arxiv.org/html/2610.36114v1 ; abstract: https://arxiv.org/abs/2610.36114 ; replication package: https://doi.org/10.5281/zenodo.23614755 .
- Relevant original sections: §II pipeline model; §III-B replay and row-aware cutter; §III-C framework survey; §IV controlled experiment; §VI validity limits; §VII model-free CI tests.

**What the paper actually shows:** 720 field runs generated 11,189 tool results; 3,827 were truncated by fixed-position JSON text slicing, and all cut results were malformed. One late-position field reached the model in 4.7% of 742 calls versus 99.3% for an adjacent early field. Maximum per-call prompt occupancy was 5.75% of a 400k window, so the defect was *upstream delivery*, not a full model context. A deterministic replay of 864 results showed all oversized prefix-sliced payloads broke, while row-aware cuts preserved valid payloads. One 33,370-character production listing lost all 128 late-list records under a 6,000-character cap. In a controlled spawned-fault experiment, reversed-order truncation increased median calls from 53 to 76 (+43%) and computations from 18 to 36, while finding yield fell from 0.61 to 0.31. Accuracy stayed similar when another evidence route existed. A smaller quiet-fault replay favored repaired delivery (3/6 correct versus 0/5), but authors explicitly do **not** claim the original field-wide accuracy split is causally established. These are source findings, not measured MechaHarness outcomes.

**Mechanism:** Treat context as five boundaries: S1 produced tool result -> delivered model representation; S2 delivered -> agent action/turn budget; S3 action -> retained history; S4 retained -> transferred finding/handoff; S5 transferred -> persisted next-run state. Different boundaries lose different things. A fixed-character prefix slice is especially dangerous for serialized maps/lists: it can cut in the middle of JSON and systematically erase late keys. Safer candidate policies include row-aware reduction, schema-aware projection, explicit omitted-field manifests, and paging via durable observation references. No single algorithm is mandated.

## Repository reality (main inspected 2026-10-29)

- Existing canonical story: https://github.com/rl337/mechaharness/blob/main/tests/fixtures/models/static/fixture/v1/suites/fangore_context_memory/stages/010_fangore_context_compiler_deficit.yaml . Story **fangore_context_compiler_deficit** requires a deficit report when mandatory sources exceed a prompt budget; the fixture checks unresolved gaps, blockers and no silent omission.
- Existing context compaction story **fangore_insp_context_compaction**: https://github.com/rl337/mechaharness/blob/main/tests/fixtures/models/static/fixture/v1/suites/fangore_context_memory/stages/040_fangore_insp_context_compaction.yaml .
- Implementation: https://github.com/rl337/mechaharness/blob/main/src/mechaharness/context_compaction.py defines CompactionInput, CompactionResult, DefaultStagedCompaction and discarded_classes. Its distill stage truncates **any string content over 200 characters** by taking its first 200 characters plus an ellipsis; it does not parse a tool-result schema or record which fields disappeared. This is an observed code property, not proof that all inference routes use this compactor.
- Product surface: https://github.com/rl337/mechaharness/blob/main/src/mechaharness/context_surface.py exposes context_compiler_deficit and context_compaction_staged, but the staged probe returns only discarded_classes. https://github.com/rl337/mechaharness/blob/main/tests/test_context_compaction.py currently checks adjacent deduplication; it does not exercise oversized structured tool payloads or field-level survival.
- Context layering and provider seams already exist: src/mechaharness/context_layers.py, context_provider.py and context_experiments.py. Open PR https://github.com/rl337/mechaharness/pull/36 adds ContextSpec bag-to-inference continuity and must be reviewed before modifying inference-envelope paths. **Do not duplicate** its graph-state propagation contract.

**Coverage decision: C (partially specified), with an observable test gap.** Existing stories protect mandatory *source selection* and record coarse discarded classes. They do not currently prove schema-valid *structured tool delivery* at S1, or an evidence-survival metric at S4. Do not replace existing stories with a new context subsystem.

## Candidate extension MH-CTX-ATTR-01: preserve or explicitly reject structured tool evidence

**Persona / why:** As a graph author debugging a tool-using agent, I want the compiled model-visible representation of a structured tool result to remain parseable and to disclose every omitted required field, so that a low token budget cannot silently erase the evidence needed for a decision.

**Existing story relationship:** Extend **fangore_context_compiler_deficit** and **fangore_insp_context_compaction**, rather than inventing a parallel story family. A new fixture may be warranted if the acceptance runner cannot express tool-output delivery under those scenarios.

**Setup:** Use a deterministic synthetic tool result with early and late arrays, a required late record identifying a culprit, 6,000-character-equivalent budget, and explicit field obligations. Also include a small payload, a long plain-text payload, and a maliciously malformed JSON string. Test original and reversed field order, and both full and tight budgets. The fixture should expose the produced payload and the exact representation handed to inference (not merely the durable bag).

**Action:** Compile/compact, then inspect the final model-facing message and omission manifest. Run with inference mocked; no model is needed to prove S1.

**Required observables / acceptance:**
1. Any output declared to be structured JSON is valid JSON at delivery, or the compiler rejects/marks it incomplete before inference. A literal prefix-sliced JSON fragment is never silently presented as a complete result.
2. Required fields and their source IDs are either present with intact values or explicitly named in a deficit that prevents a false success outcome. Optional-field omission is recorded with field path, policy, budget and reason.
3. Reordering keys or moving the decisive record to the tail cannot change *whether loss is disclosed*. When policy promises required-field preservation, both orders preserve the field.
4. A large payload can be reduced by a declared structural policy or exposed through a bounded reference/page operation. A budget overflow cannot masquerade as a valid empty result.
5. The original produced tool payload remains available through its authoritative observation reference, subject to access controls; no fabricated reconstruction.
6. A resumed graph preserves the source-to-delivery evidence link and any unresolved deficit; no promotion of a truncated summary into authoritative state.

**Negative cases:** required field absent from the original payload; malformed upstream JSON; oversized nested arrays; tool returning a non-JSON string; no available paging provider; a permission-restricted field. These must have distinct, testable outcomes.

**Implementation investigation:** Trace all call sites of DefaultStagedCompaction and ContextCompiler through the current model adapter and PR #36; establish whether the 200-character truncation is applied to actual tool-role messages. Decide how to represent typed field obligations and structured reduction without breaking existing callers. Compare (a) schema-aware projection, (b) whole-record sampling with coverage metadata, (c) durable observation handles and paging, (d) fail-closed delivery for required evidence. A generic formatter is not enough unless it validates the exact delivered bytes.

## Candidate extension MH-CTX-ATTR-02: measure evidence survival at graph boundaries

**Persona / why:** As a harness evaluator, I want to distinguish work the tools produced from evidence the model received and findings the downstream decision actually consumed, so that success and token cost are not the only signals of harness quality.

**Existing story relationship:** Extend context-observation and trace/telemetry acceptance rather than introducing an independent monitoring stack.

**Setup/action:** Execute a deterministic fan-out graph where two workers compute identifiable findings; one finding is transferred, one intentionally omitted. Repeat with a truncated tool result, a turn-limit stop, and a resumed graph. Attach stable observation IDs to source, compiled view, and transferred finding.

**Acceptance:** Per-boundary counts distinguish produced, delivered, retained, transferred and persisted records; a lost finding cannot be reported as transferred; absence is not interpreted as a negative finding; the report includes structured-payload validity and required-field survival; the evaluator can calculate a narrowly defined transfer yield (findings recorded / computations performed) without claiming it measures relevance; duplicate retries do not inflate unique evidence counts. Deterministic fixture assertions should work without a live model. A live-agent evaluation may compare tool calls, total tokens and task accuracy as secondary metrics.

**Unknowns:** What constitutes a stable finding ID? Which graph event currently records produced-vs-delivered? What is the right aggregation scope across nested graphs and resume? How to avoid storing sensitive raw payloads in telemetry?

## Ready-for-implementation acceptance plan

1. Extend the existing Fangore story fixture(s) using the native YAML and real product CLI verbs; do not add a fake passing probe.
2. Add unit tests for ordered/reversed maps, nested arrays, long tool-role messages, malformed input and paging references.
3. Add an integration acceptance walk that compares tool-produced, context-compiled and model-visible representations at a real inference boundary.
4. Add restart/replay tests using the existing durable graph machinery; verify stable evidence IDs and no duplicate transfer counts.
5. Use the paper's public replication data only if license and fixture compatibility permit; synthetic minimal examples are sufficient for the mechanical regression.

## Other related Trouble signals (deferred, not new requirements here)

- Duplicate-write safety: https://rl337.org/trouble/posts/2115685301678907769.html . MechaHarness already has external-effect and transactional-resume requirements; inspect existing DR-10 fixtures before proposing another idempotency story.
- Approval-gate bypass: https://rl337.org/trouble/posts/2115315131152556136.html and https://github.com/otsoa-dubief/airlock/security/advisories/GHSA-mgf8-gh7g-q4rg . MechaHarness already has AuthorityGate, approval interrupts and authorization-epoch resume. Advisory details and bypass reproduction remain to be verified before asserting a gap.
- Independent coverage/disproof recipe: https://rl337.org/trouble/posts/2115641269406093385.html and https://github.com/cloudflare/security-audit-skill . Its six phases and typed findings are worth comparing to existing generic verify/repair and independent-review recipes, but this pass did not establish a missing reusable primitive.

## Cross-repository trace

Discovery ledger is proposed in rl337/trouble at state/inspiration-watch-ledger.json, capability TR-20261029-CONTEXT-ATTRITION. This dossier is non-normative until accepted into the repository's canonical user stories and tests. No runtime implementation is included.

Cross-repository discovery ledger draft PR: https://github.com/rl337/trouble/pull/38 . Other resulting draft PRs: https://github.com/rl337/mechaharness/pull/37 , https://github.com/rl337/project-template/pull/1 , https://github.com/rl337/june/pull/26 .
