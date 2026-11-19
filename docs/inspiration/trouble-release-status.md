# Trouble inspiration: implemented reports and remaining work

The Trouble walks provide offline acceptance for individual report helpers.
An accepted walk means its fixture passes; it does not mean every requirement
in its source research note has been implemented.

## What downstream hosts can use

- `fangore_admit_authority` checks claim labels and resource/operation pairs
  against a supplied ledger. Import `review_admission` from
  `mechaharness.authority_admission`. The host must validate source labels and
  enforce the actual effect through its authority gate.
- `taloneth_layered_eval` combines supplied task and harness verdicts. Import
  `score_layers` from `mechaharness.layered_verdict`. The caller supplies the
  evaluation results and any assertion of causal evidence.
- `taloneth_request_prefix` compares hashes of selected tool, policy, and dynamic
  fields. Import `prefix_snapshot` and `classify_prefix_change` from
  `mechaharness.request_prefix`. Its labels describe an offline comparison;
  they do not measure provider cache misses or savings.

See the [API contracts and executable examples](../api/research_helpers.rst).
These helpers are experimental and have no automatic runtime integration.

## Remaining acceptance gaps

The [resource and memory note](./trouble-realm-resource-scope-and-memory-safety-2026-11-03.md)
(MH-REALM-01 / MH-EAL-01) still calls for resource identity resolution,
effect-time scope revalidation, and repeated-task memory attack evaluation.
The current fixture compares a ledger and does not invoke an effect dispatcher.

The [trace and requirement note](./trouble-trace-and-requirement-integrity-2026-11-17.md)
(MH-TRACE-01 / MH-REQ-01) still calls for trace-backed fidelity evaluation,
attempt-scoped retries, verified source quotes/spans, mutation detection, and
restart-safe requirement manifests. A caller-supplied source label or causal
flag is not independently verified by the report helpers.

The [prefix-cache note](./trouble-prefixwise-cache-regression-2026-11-10.md)
(MH-CACHE-01) still calls for complete wire-request fingerprints at the adapter,
provider hit/token counters, eviction versus request-shape attribution, and
matched task-success experiments. Current tool fingerprints omit descriptions
and provider-specific fields. Policy changes without a version bump are labeled
`volatile_system` heuristically, even when the edit is intentional.

The [context-attrition note](./trouble-context-attrition-2026-10-29.md)
(MH-CTX-ATTR-01/02) has Fangore probes that disclose S1/S4 evidence-loss gaps.
Schema-aware reduction and stronger handoff evidence preservation remain open.

These are follow-up implementation tasks. A release containing the report
helpers must retain these limits in its API documentation and release notes.
