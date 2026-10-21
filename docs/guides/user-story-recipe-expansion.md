# User-story → recipe expansion waves

| Surface | Value |
|---------|-------|
| Status | living plan (post Wave 3 clarification) |
| Litmus | Valid story ⇒ graph/recipe path exists; if missing, **add the recipe**, then instrument |

## Litmus (corrected)

If a persona claim is a valid MechaHarness user story, there must be an
**execution graph** (Agentic Recipe + runners + DI seams) that can carry it,
and a CLI/`user_story` walk that exercises that graph.

- Missing path ⇒ **expand inventory** (`RagRetriever` + `context_pack` was the
  model).
- Do **not** demote a valid story to unit-only because the graph is unfinished.
- Unit/doctest still covers helpers; stories own the product walk.

## Do we re-evaluate Waves 1–3?

**Yes, selectively — not a rewrite of everything.**

| Wave | Keep? | Re-eval? |
|------|-------|----------|
| **Wave 1 A** durable IoC (`start`/`answer`/…) | Keep | Light: already execute graphs |
| **Wave 1 B/C** recipe shape (`instantiate_recipe` / `recipe_plan`) | Keep as interim | **Yes — promote many to execute** when runners exist (verify_repair, bounded_retry, independent_review, …) |
| **Wave 1 D** `run_recipe` / `tool_loop` | Keep | OK where adapters execute |
| **Wave 1 E/F** judge_route / infer | Keep | OK; judge twin already landed |
| **Wave 2 P1** `transactional_resume` | Keep | OK (real crash/resume graph); optional later fold into durable CLI |
| **Wave 2/3 P2** JEV domain | Keep | OK after `judge` + `context_pack` |
| **Wave 2/3 P3** decision-plane substrate | **Reopen** | Wrongly demoted projection/policy/shadow/telemetry — **restore via plane execute runners** |
| **Wave 2/3 P4** lifecycle | Keep interim | Prefer eventual `tool_loop` + Config extensions; `tool_lifecycle` is fine until then |
| **P5–P10** still `probe:` | **Yes** | Group by **recipe to invent**, not by “thin verb then YAML wrap” |

Wave 1/2 mechanical `user_story` migrations stay valid harness shape. What we
re-evaluate is **whether the claim runs a graph** or only inspects shape /
helpers.

## Inventory snapshot (fixture v1)

| Bucket | Count | Notes |
|--------|------:|-------|
| `kind: user_story` | ~73 | Mixed: execute vs shape-only |
| Still `kind: cli` + probe | ~96 | Need recipe/verb expansion |
| Shape-only recipe walks | ~24 | `instantiate_recipe` / `recipe_plan` only |
| Demoted plane stories to restore | **4** | projection, policy, shadow, telemetry |

## Working groups (recipe-first)

Work each group by: name/extend recipe → runners + DI → restore/migrate
stories → regenerate guide → green checks.

### G0 — Decision-plane execute (restore demotions) · **done**

**Landed:** `decision_plane_runner` (`ProjectStateRunner`, `AskBatchRunner`,
`ApplyPolicyRunner`, `EscalateRunner`, `ShadowAskRunner`) +
`DecisionPlaneRecipeAdapter` on `run_recipe`. Fixture answers live on bind
`inputs` (rules backend); live `JudgeProvider` ask is a later deepen.

**Restored / promoted stories:** projection, policy (×3), shadow, telemetry,
recipe, model_policy.

### G1 — Control recipes that already exist (execute, don’t demote)

Catalog already has templates; stories only instantiate. Add runners +
`run_recipe` / durable walks:

| Recipe | Stories | Status |
|--------|---------|--------|
| `verify_repair` | `fangore_verify_repair_recipe` | **done** (batch 1) |
| `bounded_retry` | `fangore_bounded_retry_recipe` | **done** (batch 1) |
| `verify_repair` | `fangore_bounded_repair_loop` | **done** (batch 2; was probe) |
| `independent_review` | `fangore_insp_independent_review`, req-review shape | pending |
| `environment_repair` | `fangore_environment_repair_recipe` | pending |
| `initialize_preflight` | `fangore_insp_initialize_preflight` | pending |
| `produce_critique_refine` | `fangore_insp_produce_critique_refine` | pending |
| `safety_eval` | `taloneth_insp_safety_eval_recipes` | pending |

### G2 — Context / RAG lane (extend G0 pattern)

| Piece | Stories |
|-------|---------|
| Deepen `context_pack` (judge scores inside retrieve) | context_* siblings |
| `ContextProvider` discovery → pack | `fangore_insp_context_provider` + P6 context probes |
| Compaction / layers / compiler | P6 remainder |

### G3 — Access / authority as graph gates

Not a grab-bag of probes: recipes or durable envelopes that **deny/narrow** on
the product path (capability envelope, auth epoch resume, soft vs hard,
approval interrupt). Former P5.

### G4 — Graph executor / budget / resume

Durable + budget recipes; migrate P8 probes onto `start`/`answer` or
`run_recipe` with real budget/effect runners. TDR stays; align crash stories
with the same façade where practical.

### G5 — Eval / research packs

Taloneth P7: prefer eval **recipes** / export graphs over probe bags
(`policy_replay`, shadow compare, eval matrix). Compose with G0 shadow/telemetry.

### G6 — Recipe lifecycle (`recipe_plan`)

Keep `recipe_plan` for evolution/port/compose **if** the claim is registry
lifecycle. When the claim is “run the evolved recipe,” promote to execute
(G1). Do not invent another `*_case` bag.

### G7 — Diagnostics that stay thin verbs

Replay / routing / parity / affinity may remain one-shot verbs (like `infer`)
when they are not subgraph control stories. Still need honest narratives and
cassettes; no probe wrapper.

## Anti-patterns (do not repeat)

1. `*_case` product verbs that dispatch on `case:` with baked answers.
2. Marking a story green for `instantiate_recipe` alone when the inspiration
   claim is an **outcome** of running the recipe.
3. Demoting a persona claim to unit tests because runners are missing.
4. Migrating probe → `user_story` before the graph exists (YAML churn without
   product path).

## Suggested order

1. **G0** — restore four plane stories (blocks honesty of P3).
2. **G1** — verify_repair / bounded_retry execute (high reuse).
3. **G3** or **G4** — whichever unblocks more P5/P8 hosts.
4. **G2** deepen RAG; **G5** eval; **G6** lifecycle plans as needed.

## Related

- [User-story migration batches](./user-story-migration-batches.md) (Wave 1–2 checklist; P5+ superseded by groups above)
- [Instrumentation migration](./user-story-instrumentation-migration.md) (Wave 3 case-bag removal)
- [Agentic Recipes skill](../../.cursor/skills/agentic-recipes/SKILL.md)
