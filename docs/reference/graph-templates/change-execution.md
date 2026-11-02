# Template: change_execution

Apply one approved `ChangePlan` slice with scoped file revisions and an explicit
write grant, then publish a typed `ChangeExecution` (diff + hashes).

| Item | Value |
|------|-------|
| Name | `change_execution` |
| Module | `mechaharness.graph_templates.change_execution` |
| Class | `ChangeExecutionTemplate` |
| Version | `1` |

## When to use

- After `change_decomposition` publishes a `ChangePlan`
- When applying exactly one approved slice before verification
- When scope escape must be refused and write grant must be explicit

## Topology

```text
seed → constrain (execution_constrain)
  → propose (infer / propose_payload)
  → materialize (execution_materialize)
  → apply (execution_apply)
  → publish (execution_publish) → validate (execution_validate)
```

Host-seeded `in.file_revisions` win over Completer proposals when non-empty.
Completer propose enables live arm-B style execute without pre-seeding revisions.
Default propose `user_preamble` starts with `/no_think` so thinking Completers
(e.g. Qwen 3) put JSON in answer content; empty content still falls back to
`reasoning_content` in `CliInferRunner`.

## Soft points

| Name | Kind | Notes |
|------|------|-------|
| `propose_payload` | task_state | Completer ContextSpec for scoped `{path, content}` revisions |
| `apply_payload` | task_state | Optional apply parameters / inline revisions |

## Node components

| Graph node | Components |
|------------|------------|
| `propose` | `soft_point` (`propose_payload`) |
| `apply` | `soft_point` (`apply_payload`) |

## Stories

Suite `fangore_change_execution` (`005` shape, `010` apply, `015` Completer propose).
