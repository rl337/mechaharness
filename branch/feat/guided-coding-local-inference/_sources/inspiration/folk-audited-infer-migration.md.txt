# FOLK → MechaHarness: audited infer-accept migration

Non-normative host migration notes. Normative recipe:
[Audited infer-accept](../reference/graph-templates/audited-infer-accept.md).

## Catalog mapping

| FOLK catalog id (today) | MechaHarness catalog id |
|-------------------------|-------------------------|
| `ideation.infer.accept` | `audited_infer_accept` |
| `ideation.infer.accept.text` | `audited_infer_accept` + `modality=text` |
| `ideation.infer.accept.image` | `audited_infer_accept` + `modality=image` |
| `ideation.stage.verify` (deprecated) | same spine via `audited_infer_accept` |

Domain types move from `folk.domain.audited_decision` to
`mechaharness.audited_decision` (`STAGES`, `criteria_hash`,
`assert_principals_distinct`, `repair_target`, `AuditedDecisionSpec`).

Graph expand helper: FOLK `append_infer_accept` → library
`append_audited_infer_accept` (`mechaharness.graph_templates.audited_infer_accept`).

## What stays in FOLK

- `folk.infer.*` / comic / setting / media **runners**
- Comfy client, typed Comfy graph recipes, `MECHA_COMFY_BASE_URL`
- `hop_accept` leaf catalog and verify fns
- CMS / c23s / VD pipeline / print geometry
- `FolkRunServices.complete` / LM Studio bridge / FakeCompleter matrix

On migrate, soft-bind library kinds to FOLK runners, e.g.
`decide_kind=folk.infer.text.decide`, `qa_kind=folk.infer.text.qa`, or register
those kinds as the defaults in FOLK’s Config while using the library template.

## What not to do

- Do **not** replace FOLK’s comic spine with library `verify_repair` alone —
  that loses freeze-criteria, distinct QA principal, and gate ≠ publish.
- Do **not** expect MechaHarness to ship Comfy or hop_accept catalogs.

## Suggested FOLK PR steps (follow-up repo)

1. Depend on MechaHarness version that exports `audited_infer_accept`.
2. Alias `ideation.infer.accept*` → library template in `IdeationConfig`.
3. Re-export or delete duplicated `folk.domain.audited_decision` (thin shim OK).
4. Point `append_infer_accept` call sites at `append_audited_infer_accept` (or
   keep a FOLK wrapper that sets `folk.infer.*` kind overrides).
5. Keep integration tests on FakeCompleter / FakeComfy unchanged.
