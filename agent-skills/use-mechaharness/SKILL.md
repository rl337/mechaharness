---
name: use-mechaharness
description: >-
  Builds and refactors host apps on MechaHarness: MechaHarnessConfig DI,
  host_apis / host_kit, Agentic Recipes, authority/denial, and promote_recipe.
  Use when writing or changing code that imports mechaharness, subclasses
  Config, tiles graph templates, or wires GraphExecutor.
---

# Use MechaHarness

MechaHarness is a Python **agent harness library**. Hosts subclass Config and
compose — they do not fork this repo or patch closed enums.

Install: `pip install mechaharness`. Docs:
https://rl337.org/mechaharness/

## Prefer blessed host imports

Featured host surfaces are re-exported from `mechaharness.host_apis`:

```python
from mechaharness.host_apis import (
    AuthorityGate,
    CapabilityEnvelope,
    promote_recipe,
    host_graph_executor,
)
```

Leaf modules remain valid; prefer `host_apis` when discovering the surface.
Do not grow imports from root `mechaharness` for inspiration-era helpers.

## Wire with Config

```python
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.host_apis import AuthorityGate, DenialStore

class HostConfig(MechaHarnessConfig):
    def get_authority_gate(self) -> AuthorityGate:
        return AuthorityGate(...)  # or rely on configure() defaults

    def get_denial_store(self) -> DenialStore:
        return super().get_denial_store()  # override for durable storage

injector = get_injector(HostConfig())
```

- Bind via Config hooks (`get_inference_class`, `get_harness_class`,
  `get_authority_gate`, `get_denial_store`, `get_tool_result_freshness_policy`,
  `get_recipe_promotion_policy`, `get_evolution_campaign_hooks`).
- Do **not** stuff lane/provider knobs into `Settings`.
- Prefer `host_kit.host_graph_executor(...)` for readable GraphExecutor wiring.

## Agentic Recipes

- Catalog ids are stable leaf names (`verify_repair`, `decision_plane`,
  `produce_critique_refine`, `safety_eval`, …).
- Soft points describe the human decision being bound; do not invent viz-only
  node component kinds.
- Distinct recipes stay distinct — do not merge control stories.

### Promotion (product hosts)

| Intent | API |
|--------|-----|
| Policy + held-out gate + campaign hooks | `promote_recipe(registry, policy, request, hooks=...)` |
| Held-out gate only | `registry.promote_with_final_test(...)` |
| Ungated pointer (migration) | `registry.promote(...)` |

Prefer `promote_recipe`. Pass Config-bound `EvolutionCampaignHooks` so
`on_promotion` fires after a successful pointer move.

## Open identity

- Host types are classes / namespaced strings (`acme:widget`), not closed
  `Enum` patches in this library.
- Unknown namespaced event/grant values must round-trip.

## Do

1. Subclass `MechaHarnessConfig`; inject; compose.
2. Import safety/recipe helpers from `mechaharness.host_apis`.
3. Keep durable denial / warehouse / campaign storage in the host.
4. Stamp graphs with recipe id/version when tiling from a template.

## Don't

1. Hand-construct harness families or grow string registries.
2. Call ungated `registry.promote` in product paths that need held-out gates.
3. Put secrets or unbounded transcripts into event payloads.
4. Fork MechaHarness to add a host type — extend via Config / subclassing.

## See also

- Observability / warehouse joins: companion skill `mechaharness-observability`
- DI guide: https://rl337.org/mechaharness/guides/dependency-injection.html
- Inspiration primitives: `docs/reference/inspiration-primitives.md`
- Host integration requirements: `docs/requirements/host-integration.md`
