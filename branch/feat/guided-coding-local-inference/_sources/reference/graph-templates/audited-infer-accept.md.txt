# Audited infer-accept (`audited_infer_accept`)

**Agentic Recipe.** RDG-aligned generate → QA → gate spine. Modality
(`text` | `image`) only swaps decide/QA node kinds. Hosts bind runners;
MechaHarness owns topology, criteria freeze, distinct principals, and repair
routing.

| Surface | Value |
|---------|-------|
| Catalog id | `audited_infer_accept` |
| Module | `mechaharness.graph_templates.audited_infer_accept` |
| Domain | `mechaharness.audited_decision` |
| Substrate | `GraphTemplate` |
| Owning stories | `fangore_audited_infer_accept` |
| FOLK prior id | `ideation.infer.accept` (host alias on migrate) |

## Stages

```text
[precheck?] → collect → freeze_criteria → decide → independent_qa
  → deterministic → gate
```

Repair targets (defect → stage): `collect` | `freeze_criteria` | `decide`
(`mechaharness.audited_decision.repair_target`).

## Soft points

| Name | Kind | Role |
|------|------|------|
| `modality` | policy | `text` \| `image` decide/QA kinds |
| `acceptance_criteria` | policy | Frozen before decide |
| `decide_principal` / `qa_principal` | policy | Must differ (RDG-05) |
| `max_retries` | budget | Host leaf retry bound |
| `produce_kind` | runner_kind | Image/custom produce under decide |
| `decide_kind` / `qa_kind` / … | runner_kind | Override library `audited.*` kinds |
| `hop` / `task_id` | task_state | Audit identity |
| `simple_ids` | policy | Demo/test short node ids |

Default kinds: `audited.collect`, `audited.freeze_criteria`,
`audited.{modality}.decide`, `audited.{modality}.qa`, `audited.deterministic`,
`audited.gate`. FOLK soft-binds `folk.infer.*`.

## Node components

| Parent graph node | Components |
|-------------------|------------|
| Each spine stage | `soft_point` (criteria / principals / modality as bound) |
| `decide` / `independent_qa` | modality-selected runner kinds |

See [Node components](../node-components.md).

## FOLK migration

See [FOLK audited-infer migration](../../inspiration/folk-audited-infer-migration.md).

## Related

- [Guided coding](./guided-coding.md) — tiles this recipe as `audit_tile` (after `plan_tile`)
- [Instruction todo plan](./instruction-todo-plan.md) — oneshot / list control before audit
- [Verify repair](./verify-repair.md) — deterministic oracle loop (different pattern; both remain)
- Domain: `mechaharness.audited_decision`
