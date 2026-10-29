# Video production project → MechaHarness: audited infer-accept migration

Non-normative host migration notes for a **video production** host that previously
owned an audited infer-accept control spine. Normative recipe:
[Audited infer-accept](../reference/graph-templates/audited-infer-accept.md).

Do not link private host repositories from this tree; keep migration notes
descriptive only.

## Catalog mapping

| Host catalog id (typical prior) | MechaHarness catalog id |
|---------------------------------|-------------------------|
| `ideation.infer.accept` | `audited_infer_accept` |
| `ideation.infer.accept.text` | `audited_infer_accept` + `modality=text` |
| `ideation.infer.accept.image` | `audited_infer_accept` + `modality=image` |
| `ideation.stage.verify` (deprecated) | same spine via `audited_infer_accept` |

Domain types move from a host `audited_decision` module into
`mechaharness.audited_decision` (`STAGES`, `criteria_hash`,
`assert_principals_distinct`, `repair_target`, `AuditedDecisionSpec`).

Graph expand helper: host `append_infer_accept` → library
`append_audited_infer_accept` (`mechaharness.graph_templates.audited_infer_accept`).

## What stays in the host

- Host `*.infer.*` / comic / setting / media **runners**
- Comfy client, typed Comfy graph recipes, host media base URL
- `hop_accept` leaf catalog and verify fns
- CMS / pipeline / print geometry and other product surfaces
- Host run services, local Completer bridges, FakeCompleter matrices

On migrate, soft-bind library kinds to host runners, e.g.
`decide_kind=host.infer.text.decide`, `qa_kind=host.infer.text.qa`, or register
those kinds as the defaults in the host Config while using the library template.

## What not to do

- Do **not** replace the host comic / media spine with library `verify_repair`
  alone — that loses freeze-criteria, distinct QA principal, and gate ≠ publish.
- Do **not** expect MechaHarness to ship Comfy or hop_accept catalogs.

## Suggested host follow-up steps

1. Depend on a MechaHarness version that exports `audited_infer_accept`.
2. Alias prior `ideation.infer.accept*` catalog ids → library template in host Config.
3. Re-export or delete duplicated host `audited_decision` (thin shim OK).
4. Point `append_infer_accept` call sites at `append_audited_infer_accept` (or
   keep a host wrapper that sets `host.infer.*` kind overrides).
5. Keep integration tests on FakeCompleter / FakeComfy unchanged.
