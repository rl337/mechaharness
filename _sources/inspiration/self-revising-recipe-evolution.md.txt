# Inspiration: Evaluation-driven evolution of composed recipes

Status: **inspiration / proposal, not an accepted requirement**  
Recorded: 2026-10-17  
Source confidence: **unverified screenshot and social-media account**

## Attribution and provenance

Inspired by a screenshot circulated by **@slash1sol** in [this X post](https://x.com/slash1sol/status/2111452863649944061/video/1?s=46), depicting a purported manuscript titled *The End of Harness Engineering: Self-Revising Execution Programs and the Disappearance of the Agent Framework*, attributed on the image to **Haoran Wei, Siyu Zhang, and Mingze Luo**, **Qianhe Agent Systems Laboratory**, dated **2026-09-19**.

**Important:** The manuscript, author affiliations, reported experiment, and publication status have **not been independently authenticated**. The screenshot may depict an unpublished or fictional paper. Accordingly, cite it as a **social-media screenshot depicting a purported paper**, not as a peer-reviewed publication or verified research. Do not imply endorsement, originality, or validated performance. Preserve the post URL and date accessed, and update attribution if a genuine primary source is discovered.

The screenshot *claims* a frozen solver, a 4B edit proposer, eight edits per round, 300 concurrent Kimi K3 workers, 41 rounds, 37 accepted revisions, and a held-out score change from 0.31 to 0.64. **These are unverified claims, not MechaHarness benchmarks.**

## Useful idea independent of the source's authenticity

Treat the agent execution policy as a **versioned, testable, replaceable artifact**. Separate (1) workload execution and failure traces, (2) generation of candidates, (3) hidden candidate-selection evaluations, and (4) a final untouched test set. Promote changes only on measured improvements, with cost and safety constraints.

The dramatic assertion that framework engineering is obsolete is **not** adopted. Evaluation design, trusted execution semantics, access controls, reproducibility, and rollback remain engineering responsibilities.

## MechaHarness-specific architectural boundary

**Graphs must be composed dynamically from registered recipes, not synthesized from arbitrary nodes or handwritten free-form graphs.** A recipe may itself compose other recipes. A successful composition may be proposed as a reusable recipe, but must pass registration, versioning, validation, and promotion controls before reuse.

- **Hard nodes / primitives:** trusted contracts and deterministic graph-execution invariants; never silently rewritten by an optimizer.
- **Soft nodes / recipe parameters:** eligible for controlled optimization (prompt templates, model/lane selection, bounded retries, ordering, thresholds, permitted connections).
- **Recipe compositions:** eligible for candidate search using only registered, compatible recipes and typed ports; no arbitrary executable code generation in the production path.
- **New recipe versions:** immutable artifacts with provenance, lineage, test results, and a reversible promotion pointer.
- **Hard-node implementation changes:** separate, explicitly reviewed engineering changes with stricter tests; not automatically promoted by the recipe optimizer.

## Candidate evolution loop (proposed recipe)

1. Select an existing registered recipe or composition and an explicit objective.
2. Collect immutable execution traces, errors, latency, token usage, costs, and task outcomes.
3. Propose a bounded set of **recipe configurations or recipe compositions** using only allowlisted building blocks.
4. Reject invalid candidates before execution: typed connectivity, DI bindings, permission scope, graph invariants, budget limits, and recursion/loop rules.
5. Execute candidates in isolated environments on a development/evaluation split. Keep selection questions and answers inaccessible to the proposer; prevent evaluation leakage through traces.
6. Compare task success, regressions, runtime cost, latency, tool reliability, and recovery performance. Apply a predeclared selection policy, not just raw accuracy.
7. Evaluate the leading candidate against a separate untouched final test set at the designated release gate; do not reuse that set as a continuous tuning signal.
8. Promote only after passing safety and performance gates; checkpoint the approved version and retain a rollback target.
9. If a successful composition is generalizable, **propose** registration as a nested reusable recipe, with review and provenance.

## Compatibility with existing graph-resolution decisions

- Conflict resolution should revisit neighbors of the recently resolved/locked node.
- Track nodes visited during conflict resolution and prevent cycles.
- After a decision has no remaining conflicts, record a **checkpoint** with recoverable state.
- Continue until all unresolved nodes are resolved and no conflicts remain.
- Candidate evaluation must never bypass these rules, resumability, or crash recovery.

## Ownership split

- **MechaHarness:** recipe registry and typed composition, validation, deterministic execution, evaluation recipe, versioning/checkpoints, rollback hooks, observability, safety gates.
- **the AI assistant host:** workload selection, orchestration, scheduling, experiment budgets, evaluation campaigns, and promotion policy.
- **home_network:** sandboxed workers, persistent experiment stores, telemetry, and service deployment on constrained hosts.
- **JuneSpark:** inference for candidate proposals and evaluations where resource budgets permit; avoid assuming the screenshot's 4B model or concurrency claims fit local hardware.

## Open questions / TODO

- [ ] Define canonical recipe schema, typed interfaces, compatibility rules, and nested recipe version pinning.
- [ ] Decide whether the AI assistant host may auto-register successful compositions or only submit them for review.
- [ ] Specify exactly which soft-node fields can evolve and how permission changes are prohibited.
- [ ] Define evaluator data splits, contamination checks, statistical confidence, regression corpus, and final-test release policy.
- [ ] Define multi-objective scoring and hard safety/cost budgets.
- [ ] Design candidate sandboxing, concurrency limits, resource-aware scheduling, and trace redaction.
- [ ] Test checkpoints, graph conflict resolution, crash recovery, rollback, and provenance across candidate runs.
- [ ] Locate and authenticate the purported paper or code, if they exist; update attribution without retroactively treating screenshot claims as facts.

## Suggested experiments

Start with a fixed suite of known MechaHarness recipes. Compare a hand-selected baseline against automatically chosen **compositions of existing recipes**, under equal inference budgets and untouched evaluation data. Track correctness, costs, latency, tool policy violations, and checkpoint recovery. Only then consider optimizing individual recipe parameters or recursively registering winning compositions.

## Related inspirations

- [Durable graph generators (IoC)](./durable-graph-generators-inversion-of-control.md) — host-facing driven runs with ordered guidance yields; recipe evolution selects *which* registered recipe is active, while the generator drives *how* that run advances across drivers and process boundaries.
