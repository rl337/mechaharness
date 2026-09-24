# User stories

MechaHarness acceptance paths are told as **user stories**: short prose scenes
centered on software-engineer dragons. The same narratives live in fixture
`story.json` files and run as dual-mode data-driven tests under `tests/stories/`.

See the Cursor skill `.cursor/skills/user-stories/SKILL.md` when adding features:
touched functionality must be exercised by a story, and story bodies stay
readable prose (not As-a checklists).

## Personas

### Nubble — operations / DevOps

Nubble keeps the Spark lit and the pages quiet. He cares about lanes and
profiles, CI that does not depend on LAN, and EventLog cost signals he can
forward to billing or Grafana.

### Fangore — application developer

Fangore builds host apps on MechaHarness Config. He cares about deny-by-default
grants, `CompoundPolicy` composition, DI wiring, and product rules that stay in
`JudgementPolicy` — never in the model’s mouth.

### Taloneth — ML engineer

Taloneth owns judge contracts and adapter drift. He cares about offline fixture
batches, versioned System One cassettes, and flipping the same story to live
when the forge is warm.

## Running the suite

Default CI runs **every** story offline (static fixture + cassettes) — no skips.

```bash
# CI / offline — all stories, zero skips
pytest -q tests/stories

# Full suite (unit + stories)
pytest -q

# Live OpenAI-compat (junespark) — same tests, real HTTP
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=openai_compat/qwen3-30b-thinking \
  MECHA_BASE_URL=http://127.0.0.1:8000/v1 pytest -q tests/stories -k nubble_run_cost

# Live System One
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=systemone/laya \
  MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009 pytest -q tests/stories -k refund_verdict

# Shorthand aliases (still dual-mode stories, not separate skipif modules)
MECHA_LIVE_JUNESPARK=1 MECHA_BASE_URL=… pytest -q tests/stories -k nubble_run_cost
MECHA_LIVE_QWEN=1 MECHA_BASE_URL=… pytest -q tests/stories -k nubble_run_cost
MECHA_LIVE_JUDGE=1 pytest -q tests/stories -k 'refund_verdict or systemone_cassette'
```

| `MECHA_STORY_BACKEND` | Behavior |
|-----------------------|----------|
| `static` (default) | In-process fixture + HTTP cassettes |
| `live` | Real servers; soft expects only |

## Models

| Path | Role |
|------|------|
| `static/fixture/v1` | Generic in-process model; model-agnostic paths |
| `openai_compat/<served-id>/v1` | Captured OpenAI-compat chat |
| `systemone/<served-id>/v1` | Captured System One judge wire |

## Nubble’s stories

### `nubble_lane_load_hint` — The wrong torch on the wall

Nubble is mid-shift when a paging alert fires: the refund-routing job is failing
on the Spark. He SSH’s in, expects a judge profile, and finds someone left the
**reason** torch lit from an earlier experiment. The harness should not shrug
with a generic failure — it should tell him, in operator language, that this
work needs the judge lane and which load command to run. When the error names
`infer load decide-fast` (or the host’s judge hint), Nubble flips the profile
and the page clears. He relates to this story whenever a lane mismatch wastes
minutes of incident time.

### `nubble_run_cost_events` — Counting the sparks

Finance asked Nubble for a boring truth: can they see that a harness run
actually burned units? He kicks a one-shot pass-through (“say hello”) and opens
the EventLog. He needs `core:inference` and `core:cost` sitting there with
non-zero units — the same signals he would forward to billing or a Grafana
panel. If those events are missing, ops is flying blind; if they’re present, he
trusts the ledger enough to put an alert on it.

### `nubble_ci_static_smoke` — Merge night without the mountain

It is late; the DGX Spark is offline for maintenance, and a PR still needs
green CI. Nubble refuses to block merges on LAN reachability. He wants the
OpenAI-compat path proven from a **cassette** — a recorded reply replayed
through the real HTTP client — so the pipeline stays honest about wire shape
without waking the mountain. When static CI is green, he sleeps; when someone
breaks the adapter, CI fails before production.

## Fangore’s stories

### `fangore_compound_grants` — The locked scroll, then the keyring

Fangore is building a host app that must not let agents scribble the filesystem
by default. He starts with a read-only grant set — the write tool is refused,
and he can show product that deny-by-default works. Later he composes that
policy with a write layer via `CompoundPolicy` (one keyring, not a rewritten
list) and the same tool succeeds. He relates to this whenever an app needs
reusable permission packs instead of copy-pasted grant arrays.

### `fangore_refund_verdict` — Billing owns the double-charge

A customer was charged twice. Fangore’s product rule is simple: only the billing
team may own that ticket — the model may *suggest*, but it must not grant
permission. He runs the judge over the ticket text, then `JudgementPolicy`
decides ALLOW only when the route signal is billing. If the model picks
technical, policy denies. He relates to this whenever business authority must
stay in code, not in prompt vibes.

### `fangore_config_access_policy` — Wiring the nest with DI

Fangore subclasses `MechaHarnessConfig` for his host. He does not want a
service-locator bag of grants — he overrides `get_access_policy()` to return
his `CompoundPolicy`, configures once, and injects `AccessControl`. When the
injector hands back a control that already honors his layers, he knows the app
is wired the MechaHarness way. He relates to this whenever a host must stay
DI-first instead of sprinkling grants into constructors by hand.

## Taloneth’s stories

### `taloneth_fixture_judge_batch` — Lab bench without the forge

Taloneth is iterating on question sets — noul, choice, and score in one batch —
and cannot wait on a GPU forge for every tweak. He drives `FixtureJudgeProvider`
with known answers and checks that validation accepts clean signals and reports
errors when answers are missing. The lab bench is offline, deterministic, and
fast; he relates to this whenever contract tests must not depend on a served
model.

### `taloneth_systemone_cassette` — Pinning Laya’s handwriting

A new Laya build changes confidence fields in the System One JSON. Taloneth
keeps a **versioned cassette** of the wire response under `systemone/laya/v1`
and replays it through `SystemOneJudgeProvider`. If mapping breaks, the story
fails before silent drift ships. He relates to this whenever adapter code must
stay pinned to a known model handwriting.

### `taloneth_live_parity` — Same scroll, live ink

When the forge is warm, Taloneth flips `MECHA_STORY_BACKEND=live` and runs the
**same** request and expect scrolls against the real endpoint. He is not
rewriting tests — he is asking whether live ink still satisfies the soft
acceptance he already trusts from cassettes. Drift shows up as a failed story,
not a new skipif module. He relates to this whenever “does production still
match the lab?” must be one command away.

Live parity is a **mode** of the cassette-backed stories above (for example
`nubble_run_cost_events`, `fangore_refund_verdict`,
`taloneth_systemone_cassette`), not a separate empty fixture.
