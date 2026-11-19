# Release refactor priorities

This review covers the tracked source on the Trouble acceptance branch. It
identifies work to sequence around a release; it does not claim that the
proposed integrations already exist.

## First: make release identity deterministic

Both `.github/workflows/version-bump.yml` and `release.yml` run after main CI.
The bump workflow checks out the live branch, calculates a bump using the CI
commit's merge type, and pushes a version commit with `[skip ci]`. The release
workflow independently checks out the CI-tested SHA and packages its version.
There is no dependency ordering. A later branch head can differ from the tested
commit, and the newly bumped version is not validated by that CI run.

Before the next automated release, establish one sequence: choose a version,
commit it, validate that immutable commit, then package and tag that same SHA.
A version PR validated before merge is a straightforward option. A single
orchestrated pipeline is another. Keep version selection separate from changes
that might publish immediately. Cover concurrent runs, advancing main, reruns,
existing tags, and failed validation before changing workflow triggers.

## Separate demonstrations from operational CLI handlers

`cli_surface_verbs.surface_cli_verb_classes` registers the handlers in
`context_surface`, `evaluation_surface`, and `pure_api_surface` as product
verbs. Some handlers still implement canned demonstrations:

- `run_repo_topology` indexes two fixed files and ignores the request.
- `run_cache_layout_experiment` compiles fixed policy/context/query strings.
- `run_evaluator_compose_run` evaluates a fixed `exists` claim with a story
  evaluator identity.
- `run_atk_research_reject` constructs a passing held-out final result when
  promoting a candidate. That synthetic result is not a real held-out test.

First inventory which registered verbs hosts consume. Move fixture composition
to the test harness, and keep real product handlers thin, typed, and responsive
to supplied inputs and injected collaborators. Preserve invocation compatibility
where consumers depend on it; a compatibility wrapper must disclose synthetic
or unsupported behavior rather than imply real validation. In particular,
synthetic held-out success must not become evidence for actual promotion.

Retain genuine domain helpers. Moving everything into one universal diagnostic
module would hide the ownership problem rather than solve it. Acceptance tests
should vary inputs and check the product result, then exercise refused and
unknown paths. A coverage percentage alone does not establish integration.

## Reuse evidence types where their meanings agree

`Claim`, `Evidence`, and `EvaluationOutcome` already represent unknown findings,
evidence references, and non-task failures. The newer `layered_verdict` and
`authority_admission` reports instead use dictionaries and caller assertions.

Use existing types for actual evaluated findings. Keep authorization decisions
separate from evaluation claims. Treat caller assertions and synthetic fixtures
as distinct from observed evidence. Source-bound admission belongs with
`HandoffRecord`, `CapabilityEnvelope`, and `AuthorityGate`, with validation at
admission and again at effect time. Do not add another parallel grant store or
infer causal support from a boolean. Preserve current experimental helper
semantics until a reviewed migration and acceptance tests establish stronger
contracts. See [Trouble implementation gaps](../inspiration/trouble-release-status.md).

## Normalize provider requests at the actual adapter boundary

`request_prefix` hashes selected fields and omits descriptions and provider
extensions. `OpenAICompatStrategy._build_body` separately filters extras and
maps token-limit fields, partly by model name and endpoint text.

Define provider capabilities and a normalized wire representation before
promoting experimental fingerprints into cache identity. Derive request
fingerprints from the actual serialized request, retain omission metadata, and
keep provider counters separate from inferred change categories. Cover local
compatibility servers, cloud model capabilities, explicit extras, and absent
telemetry. Do not use substring matching or selected hashes as proof of cache
correctness or savings.

## Give injected state one lifecycle owner

`MechaHarnessConfig.get_denial_store` caches `_denial_store` on Config using
`getattr`. That differs from the documented constructor-injection ownership
pattern. Removing the cache without a lifecycle design could accidentally split
shared denial memory, so it is not a mechanical cleanup.

Bind denial memory at the intended injector scope. Prove identity within one
container, isolation across independent containers, and shared visibility to the
authority gate before changing the hook. Keep host overrides compatible.

## Extract executor responsibilities after invariant coverage

`graph_executor` combines nested-frame control, checkpoints, budgets, authority,
external effects, and event correlation. `cli_policy_verbs`, recipe adapters,
and coding local work also accumulate several ownership domains.

Extract by responsibility only after mapping those boundaries. Preserve shared
nested-frame budgets, authority propagation, committed child returns, effect
ownership, cancellation, and failure cleanup. Add acceptance coverage where an
invariant is missing before moving code. File size alone is not a reason to
rewrite a working executor before a release.

## Tracked-file sweep and prevention

The snapshot sweep found no tracked env scripts, bytecode, local plans/ADRs,
build output, runtime state, recognizable credential/private-key signatures,
personal home paths, or private endpoints. The intentional `.env.example`,
MCP example, maintainer rules/skills, generated suite catalogs, and story guide
remain tracked. No cleanup deletion was justified.

The additional historical query found no OpenAI project-key, GitHub PAT, or
private-key-header matches in locally available revisions. Neither query is a
complete secret audit. The hygiene guard in `scripts/repository_hygiene.py`
checks current tracked paths and text only, emits redacted locations, and avoids
reading untracked files and symlink targets. It now runs in local/CI checks.
