# FineEnvs multi-harness RL requirements map

Maps backlog items from
[multi-harness-rl-inspiration.md](./multi-harness-rl-inspiration.md)
(`MH-MHRL-*`) to modules and user stories.

**Coverage:** *story* means a persona story exercises the path; *surface* means
types exist with unit/doctest coverage; *partial* / *gap* mean incomplete.

| ID | Topic | Modules | Library | Story |
|----|-------|---------|---------|-------|
| MH-MHRL-01 | Harness/config evaluation provenance | `harness_fingerprint.py` | gap | — |
| MH-MHRL-02 | Experiment fixed vs varying dimensions | `experiment_dimensions.py` | gap | — |
| MH-MHRL-03 | Observed `RolloutGraph` | `rollout_graph.py` | gap | — |
| MH-MHRL-04 | Training-grade inference capture | `inference_capture.py` | gap | — |
| MH-MHRL-05 | Capture capability linkage preflight | `inference_capture.py`, `linkage_resolver.py` | partial | — |
| MH-MHRL-06 | Evaluation outcome taxonomy | `evaluation_outcome.py` | gap | — |
| MH-MHRL-07 | Explicit objective / aggregation policy | `objective_policy.py` | gap | — |
| MH-MHRL-08 | Gated / lexicographic objectives | `objective_policy.py`, `harness_experiment.py` | gap | — |
| MH-MHRL-09 | Independent trace reconciliation | `trace_reconciliation.py` | gap | — |
| MH-MHRL-10 | Orthogonal task/harness/env/trainer axes | (architecture constraint) | surface | — |
| MH-MHRL-11 | Trainers consume real MH artifacts | (ownership boundary) | surface | — |
| MH-MHRL-12 | Train/eval constraint parity | `run_parity.py` | gap | — |
| MH-MHRL-13 | Experiment resume sampling lineage | `experiment_lineage.py` | gap | — |
| MH-MHRL-14 | Exposure accounting | `exposure_accounting.py` | gap | — |
| MH-MHRL-15 | Discriminative-value telemetry | `discriminative_value.py` | gap | — |
| MH-MHRL-16 | Exportable learning trajectories | `learning_export.py` | gap | — |
| MH-MHRL-17 | Model × harness × task matrix | `eval_matrix.py` | gap | — |
| MH-MHRL-18 | Cross-harness failure taxonomy | `cross_harness_failure.py` | gap | — |
| MH-MHRL-19 | Multidimensional efficiency | `efficiency_scorecard.py` | gap | — |
| MH-MHRL-20 | Native inference capture seam | `inference_capture.py` | gap | — |

## Ownership

**MechaHarness owns:** harness/config identity, rollout/execution representations,
inference-capture contracts, evaluation provenance, evidence validity, objective
aggregation, experiment matrix/exposure surfaces, export packs.

**June (or another client) owns:** corpus selection, training recipes, checkpoint
promotion, retention/privacy policy.

## Attribution

Follow-on work must keep FineEnvs / Hugging Face permalinks in story footnotes
(see each `story.json`), not only a link to the aggregate inspiration document.
