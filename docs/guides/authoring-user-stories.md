# Write an acceptance story

A story should let a reader follow a persona's task through the product:
what they need, how they start the host, what they do, and which artifact or
event proves completion. Nubble handles operations, Fangore builds applications,
and Taloneth evaluates models and harness behavior.

## Edit the source, then generate the catalog

Write one YAML file per distinct walk under
`tests/fixtures/models/static/fixture/v1/suites/<suite>/stages/`.
`kind: user_story` wraps product CLI verbs in this order:
`environment` → optional `graph` → `steps` → `complete` → `cleanup`.

Each stage contains `id`, `suite`, `persona`, `title`, `narrative`,
`implementation`, `validation`, and `footnotes`. Use `footnotes: []` when there
is no source to attribute. Name the implementation modules and the actual stage
or test proving the claim. Attribute source-derived requirements next to their
claim, through an inspiration note where relevant. Do not describe recorded or
caller-supplied evidence as an independently observed result.

```yaml
id: fangore_example
suite: example_suite
persona: fangore
title: Inspect a tool-use request without calling the provider
narrative: >
  Fangore starts pass_through with mock and asks inspect_openai_request to
  normalize a request. He checks that the report says no cache was observed.
implementation: InspectOpenAIRequestVerb uses the injected OpenAIRequestPolicy.
validation: This stage checks the diagnostic through the product CLI.
footnotes: []
kind: user_story
environment:
  family: pass_through
  backend: mock
  filesystem: {type: temp}
steps:
- do:
    inspect_openai_request:
      endpoint: https://api.openai.com/v1
      request: {model: gpt-6-luna, messages: []}
complete:
  expect:
  - {kind: equals, key: provider_cache_observed, value: false}
cleanup: []
```

Use an existing suite when the task belongs to that arc. Stage filenames
(`010_`, `020_`, …) define ordering. Independent walks can run in parallel;
sequential coding arcs share a suite workspace and fail fast. Suite metadata
belongs in `suite.yaml`, persona biographies in `personas.json`.

```bash
python -m tests.stories.commands sync-suites
python -m tests.stories.commands sync-guide
python -m tests.stories.commands sync-suites --check
python -m tests.stories.commands sync-guide --check
MECHA_STORY_BACKEND=static pytest -q tests/stories/test_story_schema.py
```

`sync-suites` owns generated `suite.json`; `sync-guide` owns
[user-stories.md](./user-stories.md). Never edit generated prose by hand.
The former separate `story.json` and migration-wave checklists are retired.

## Exercise product behavior

Call the product verb or recipe with meaningful inputs. Put canned examples in
the YAML, not production handlers. Prefer a positive walk plus refusal/unknown
cases, with hard assertions on actual outputs, events, or artifacts. Vary inputs
to catch handlers that ignore them. A helper's unit-test success or a graph's
node shape alone does not establish an end-to-end acceptance claim.

Use Agentic Recipes when the behavior is a reusable control pattern. Bind and
expand the catalog recipe rather than duplicating its graph. A missing product
path is implementation work: do not substitute a test-only probe and mark the
feature complete. Narrow policy/shape diagnostics remain useful when their
story explicitly states that limited scope.

For coding, `environment.local_work: project_coding` selects real host local
work; use `environment.filesystem.type: suite` for shared arcs. Keep every
previous stage's acceptance checks and inspect the on-disk result. See
[coding suites](./coding-delegate-suites.md) and
[CLI universe](../reference/cli-universe.md).

## Static and live validation

Static is the default and uses mocks/cassettes. HTTP model twins live under
`tests/fixtures/models/<family>/<model>/<version>/stories/…/scenarios/`;
keep their prose identical to the canonical static story where both exist.
Fixture-specific token counts may be relaxed in live mode; behavioral results
remain hard requirements.

Use `MECHA_STORY_BACKEND=static` for repeatable offline checks even when your
shell has live aliases set. For explicit cloud/local live testing, use
[OpenAI setup](./openai-local.md). Judge stories need a separate judge endpoint.
Record live provider/model/settings and results separately; a static pass does
not claim live success.
