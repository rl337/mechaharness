# Job lanes and JobLaneBroker (JL-*)

Normative product direction for **lane-scoped run data**, observability, and
cross-lane authorization. Replaces the interim “cross-task isolation guard”
framing (MH-DOTS-07) with an intrinsic broker: isolation is not a special
CLI verb — every cross-run / cross-lane read goes through the broker.

**Status:** implemented (types, Config DI, CLI verbs, JL story matrix). Inspiration
map MH-DOTS-07 remains the provenance link.

## Vocabulary

| Term | Meaning |
|------|---------|
| **JobLane** | Named pipeline identity (`assets.generate`, `billing.settle`). Not a schedule — cron, commit hook, and manual triggers all append to the same lane. |
| **Run sequence** | Ordered history of runs for one lane. |
| **Run** | One execution: `run_id`, timestamps, optional trigger metadata, WalkBag. |
| **JobLaneBroker** | Config DI injectable that owns per-lane sequences, bags, exposure policy, inter-lane grants, and `observe`. |
| **Exposure policy** | Per-lane rules for `meta` and bag keys: `open`, `deny_all`, or `allow_lanes{…}`. |
| **Lane grant** | Standing permission for caller lane(s) to observe named keys/meta. |
| **Handoff** | Narrow one-shot share (`HandoffRecord`) of named refs — complements standing grants. |

Same-lane lineage is shared by default (later runs may observe earlier runs in
that lane). Cross-lane observe is deny-by-default unless exposure + grant (or
handoff) allow it.

## Requirements

| ID | Requirement |
|----|-------------|
| JL-01 | `JobLane` is a concrete type (id + exposure policy for meta and keys). |
| JL-02 | `JobLaneBroker` is bound via Config (like `AccessControl`); hosts inject it — no global singleton. |
| JL-03 | Each run has a WalkBag held by the broker under `(lane_id, run_id)`. |
| JL-04 | Run sequence supports selectors: exact `run_id`, `latest`, `before(t)` / `at_or_before(t)`. |
| JL-05 | `observe(caller_lane, target_lane, selector, key\|meta)` is the only cross-run read path; deny is hard failure / typed deny outcome. |
| JL-06 | Publisher lane policy and caller grants are both checked (meta vs key separately). |
| JL-07 | Same-lane observe of own sequence is allowed by default. |
| JL-08 | `FileArtifact` (path\|url) values may be published under exposed keys (e.g. `asset_urls`). |
| JL-09 | Deprecate `CrossTaskIsolationGuard` via thin re-export shim; migrate call sites to `JobLaneBroker`. |
| JL-10 | User-story YAML declares lanes in `environment` and optional per-step `lane` / `run_id`; no dedicated `cross_task_isolation` verb. |

## User-story YAML surface

```yaml
kind: user_story
environment:
  family: pass_through
  backend: mock
  job_lanes:
    assets.generate:
      meta: { mode: allow_lanes, lanes: [billing.settle] }
      keys:
        asset_urls: { mode: allow_lanes, lanes: [billing.settle] }
    billing.settle:
      meta: { mode: open }
      keys: {}
  lane_grants: []   # optional standing grants beyond lane exposure
steps:
- do:
    run_recipe: { name: verify_repair, … }   # any product graph walk
  lane: assets.generate
  run_id: gen-2026-10-21T15
  # publishes asset_urls onto the run bag via normal nodes / out register
- do:
    lane_observe:
      target_lane: assets.generate
      selector: { latest: true }             # or run_id / before
      key: asset_urls
  lane: billing.settle                       # caller identity
  expect:
  - kind: equals
    key: status
    value: ok                                # or denied
complete:
  expect: […]
cleanup: []
```

Notes:

- `environment.job_lanes` configures the broker catalog for the story Config.
- Step-level `lane` + optional `run_id` set the **caller / writer** identity for
  that verb (graph run appends to that lane’s sequence).
- `lane_observe` (name TBD; may be a thin product verb or graph node) always
  goes through the broker — this is how stories assert grant vs deny without an
  isolation-only façade.
- Multiple steps with different `lane:` values are how we prove cross-lane
  deny and same-lane lineage allow.

## Planned story matrix (distinct claims)

Retire the single intervening-task bleed probe as the sole MH-DOTS-07 proof.
Prefer focused stories (ids provisional):

| Id | Claim |
|----|--------|
| `fangore_job_lane_same_lane_lineage` | Later run in lane A observes earlier run’s exposed key |
| `fangore_job_lane_cross_deny` | Lane B observe of A’s key denies without grant |
| `fangore_job_lane_meta_allowlist` | Meta open only to listed lanes |
| `fangore_job_lane_key_expose_artifacts` | `FileArtifact` / URL key observe after exposure + grant |
| `fangore_job_lane_observe_before` | `before(t)` selector returns last eligible run |
| `fangore_job_lane_handoff_oneshot` | `HandoffRecord` unlocks named refs once |
| `fangore_insp_cross_task_isolation` | Retargeted narrative → JobLaneBroker + matrix above |

Keep related stories distinct:

- `fangore_insp_isolation_io` — subgraph `IsolationContract` / `TemplateIOContract` (nest I/O), not lane broker.
- `fangore_insp_handoff_record` — schema of handoff payloads; broker *consumes* it for one-shot share.
- `nubble_insp_workspace_isolation` — host workspace provider seam (worktree/container), not lane bags.

## Related

- [Job lanes reference](../reference/job-lanes.md)
- [Access control](../reference/access.md) (grant analogy)
- [WalkBag](../reference/job-lanes.md#walkbag) (per-run registers)
- [OpenAI Dots map MH-DOTS-07](../inspiration/openai-dots-agent-safety-requirements-map.md)
