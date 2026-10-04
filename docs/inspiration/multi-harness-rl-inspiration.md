# Multi-Harness RL Inspiration for MechaHarness

> Evidence-backed design notes derived from Hugging Face / FineEnvs, **“The ultimate guide to multi-harness RL”** (2026-10-01). External material is inspiration and evidence, not specification.

Last reviewed: 2026-10-04

## Purpose

FineEnvs demonstrates that the harness is part of effective model behavior: context construction, tools, retries, compaction, control flow, and termination all affect outcomes. This review asks what those findings imply for MechaHarness, without turning MechaHarness into an RL trainer.

Compared against MechaHarness main at `087640b3433344ee76fb274e52a71db75e325f0f`, especially `docs/architecture.md`, `docs/inspiration/dev-blog-inspiration.md`, `docs/inspiration/requirements-map.md`, graph execution, EventLog, linkage, context, routing, judge provenance, harness experiments, and durable checkpoints.

Canonical source:
https://huggingface.co/spaces/FineEnvs/multi-harness-rl

Canonical interactive rendering:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system

## 1. Harness identity is part of an evaluation result

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#benchmark-scores-now-come-with-a-harness-attached

FineEnvs shows that changing only the harness can materially change model performance.

**MechaHarness today:** Partially covered. Inspiration requirement 14 already calls for harness versions and experiment assignments in traces, but the requirements map still lists “Harness version always on traces” as a gap.

**MH-MHRL-01:** Evaluation provenance MUST identify the effective harness configuration: model revision, harness family/version, graph/template/config fingerprint, routing/context/tool surface, evaluator, environment, and task/corpus identity. Evaluation results MUST NOT be represented as properties of a model alone when harness provenance is known.

## 2. Harness variation should be an explicit experimental dimension

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-models-overfit-to-a-single-harness
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#frontier-labs-now-train-across-harnesses-on-purpose

FineEnvs identifies action format, context structure, and control flow as major harness-overfitting axes.

**MechaHarness today:** Strong conceptual fit through parameterized graph templates, soft points, injectable policies, harness families, routing, context providers, lifecycle extensions, and capability envelopes. The experiment layer does not yet model a systematic harness-configuration distribution.

**MH-MHRL-02:** Harness experiments SHOULD declare which dimensions are fixed and which vary, and every variant SHOULD retain a reproducible configuration fingerprint.

## 3. Intended execution and observed execution are different graphs

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#from-calls-to-training-sequences

FineEnvs reconstructs model-call topology: retries become siblings, subagents can become roots, and compaction can create another root.

**MechaHarness today:** `ExecutionGraph` models intended structure and EventLog records execution, but observed runtime topology is not itself a typed graph.

**MH-MHRL-03:** MechaHarness SHOULD expose a `RolloutGraph` representing what actually happened, including roots, parent/child calls, retries, dynamic subgraphs, delegated agents, model/tool calls, context transformations, escalation, cancellation, and terminal outcomes. It MUST link back to intended `ExecutionGraph` nodes where possible.

## 4. Model-boundary capture can preserve irrecoverable training information

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-rewards-are-not-enough
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#what-gets-recorded

FineEnvs argues that on-policy RL may require exact sampled token IDs and generation-time log probabilities rather than re-tokenized text. The article also notes that this position is not universal.

**MechaHarness today:** Ordinary inference telemetry exists, but training-grade token/logprob capture is not a core contract, appropriately.

**MH-MHRL-04:** Inference backends MAY expose a training-grade capture capability covering engine token IDs, behavior-policy logprobs, sampling parameters, model revision, and request/response linkage. Unsupported fields MUST be explicit and MUST NOT silently masquerade as trainable data.

## 5. Capture capability should be probed, not assumed

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#what-gets-recorded

FineEnvs probes endpoints because a provider may serve normal completions while omitting training-grade capture fields.

**MechaHarness today:** This maps naturally onto `InferenceEnvironment`, linkage preflight, and environment capability discovery.

**MH-MHRL-05:** Optional inference-capture capabilities SHOULD participate in linkage. A workflow requiring exact capture SHOULD fail preflight before expensive work when the active backend cannot satisfy it.

## 6. Infrastructure failure is not task failure

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#serving-harbor-through-openenv
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#rewards

FineEnvs keeps verifier/infrastructure failures distinct from negative task reward. A dead sandbox is not evidence that the model answered incorrectly.

**MechaHarness today:** Structured graph/environment/judge failures exist, but a universal evaluation-evidence taxonomy is not explicit.

**MH-MHRL-06:** Evaluation MUST distinguish success, task failure, execution failure, invalid trace, unscorable evidence, and cancellation/supersession where relevant. Infrastructure or trace-integrity failures MUST NOT automatically become negative task labels.

## 7. Multiple evaluator signals must not be silently collapsed

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#rewards

FineEnvs refuses to invent a weighted combination of several verifier scores. It also describes reward hacking caused by an apparently harmless submission bonus.

**MechaHarness today:** Strong foundation through typed judge signals and separation between model signals and policy authority.

**MH-MHRL-07:** Evaluator aggregation MUST be explicit and provenance-bearing. Any scalar objective SHOULD identify component signals, formula/policy, policy version, bounds/gates, and conditional prerequisites.

## 8. Efficiency rewards should be subordinate to correctness

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#what-we-rewarded

FineEnvs’ successful setup applies an efficiency bonus only to correct answers.

**MechaHarness today:** Cost, budgets, latency, token use, and tool churn are already modeled.

**MH-MHRL-08:** Evaluation policy SHOULD support gated or lexicographic objectives, making “satisfy correctness/safety first, then optimize efficiency” straightforward.

## 9. Independent trace reconciliation catches hidden failures

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#rewards

FineEnvs compares proxy capture against Harbor’s independently written ATIF trajectory and rejects mismatches. This caught executions whose proxy trace looked valid while the harness had actually been cut short.

**MechaHarness today:** EventLog, checkpoints, and failure attribution mostly originate from the same execution system.

**MH-MHRL-09:** MechaHarness SHOULD support reconciliation across independent observation surfaces such as executor events, model-gateway capture, tool/runtime audit logs, sandbox logs, and client task transitions. Training/self-improvement consumers MAY require successful reconciliation.

## 10. Task, harness, environment, and trainer are orthogonal choices

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#harbor

Harbor keeps task, harness, sandbox, and trainer independent.

**MechaHarness today:** Strongly aligned through graph templates, client realization, inference strategies, environments, envelopes, and policies.

**MH-MHRL-10:** Evaluation/training integration MUST preserve these dependency axes. Task semantics SHOULD remain portable across compatible harnesses, providers, environments, and evaluators.

## 11. Trainers should not reproduce harness control flow

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#white-box-vs-black-box-rl-environments
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#conclusions

The black-box harness owns retries, tools, compaction, subagents, and termination; the trainer observes model interactions.

**MechaHarness today:** This fits the existing MechaHarness/June boundary.

**MH-MHRL-11:** Training consumers SHOULD consume real MechaHarness execution artifacts rather than implementing a second training-only approximation of graph semantics.

## 12. Training/evaluation behavior-shaping constraints should match

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-the-two-harbor-runs-declined
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#what-changed-for-lfm

FineEnvs found a train/eval output-token mismatch that taught behavior evaluation later truncated.

**MechaHarness today:** Budgets and graph/config fingerprints exist, but train/eval parity is not explicit.

**MH-MHRL-12:** Comparable runs SHOULD record and validate parity for output caps, tool budgets, timeouts, context limits, retry/stop policy, tool availability, and sampling configuration. Material mismatches SHOULD be surfaced.

## 13. Resume correctness is also experimental integrity

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-the-two-harbor-runs-declined

A resume bug replayed already-seen tasks and contaminated the later training distribution.

**MechaHarness today:** Durable graph resume and fingerprints are strong.

**MH-MHRL-13:** Experiment resume SHOULD preserve sampling lineage: consumed cases, ordering/sampler state where relevant, experiment assignment, checkpoint identity, and duplicate evidence detection.

## 14. Equal rollout counts do not imply equal exposure

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#how-much-each-run-saw
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#other-things-the-qwen-runs-showed

Different harnesses can produce very different numbers of model calls, rows, and tokens from the same number of rollouts.

**MH-MHRL-14:** Harness experiments SHOULD report exposure across tasks/rollouts, model calls, generated tokens, input/context tokens, tool calls, wall time, cost/compute, and accepted training targets where applicable.

## 15. “No learning signal” is useful telemetry

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#other-things-the-qwen-runs-showed
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#what-we-rewarded

Many groups had no reward contrast because every rollout was right or every rollout was wrong.

**MH-MHRL-15:** Experiment tooling SHOULD report discriminative value: all-success ties, all-failure ties, evaluator ties, and cases where secondary metrics provide the only distinction. This can guide corpus evolution.

## 16. Successful trajectories are reusable beyond RL

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#sft-vs-rl

FineEnvs uses captured successful trajectories for SFT as well as RL.

**MechaHarness today:** Event logs/traces already suit offline analysis; June is the natural owner of corpus/training policy.

**MH-MHRL-16:** Exportable execution traces SHOULD retain sufficient provenance for downstream learning consumers, while MechaHarness avoids owning SFT/RL recipes or dataset curation.

## 17. Cross-harness evaluation is a compatibility matrix

Sources:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#setup
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#accuracy

FineEnvs evaluates checkpoints under all harnesses and retains the per-harness matrix.

**MH-MHRL-17:** Experiment APIs SHOULD support `model × harness/config × task family` matrix evaluation. Aggregation MUST retain drill-down to individual cells so averages cannot hide catastrophic compatibility failures.

## 18. Interface failure differs from lower task accuracy

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#when-a-model-leaves-the-harness-it-was-trained-in

A model moved outside its native harness may stop producing usable tool calls, which is different from merely solving fewer tasks.

**MH-MHRL-18:** Cross-harness evaluation SHOULD classify semantic task failure separately from invalid tool names, invalid arguments/schema, malformed protocol output, termination failure, context/control-flow dependence, and unsupported capabilities.

## 19. Tool-call count is useful, but efficiency is broader

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#tool-calls-and-tokens

FineEnvs uses tool-call count as a simple efficiency signal and observes associated token reductions.

**MechaHarness today:** Already broader, including tokens, latency, memory, compute, money, and coordination overhead.

**MH-MHRL-19:** Efficiency SHOULD remain multidimensional. Tool calls MAY be a proxy, but underlying dimensions SHOULD remain observable.

## 20. Black-box capture suggests a clean MechaHarness seam

Source:
https://fineenvs-multi-harness-rl.hf.space/?__theme=system#the-capture-proxy

FineEnvs captures unmodified harnesses at the model API boundary.

**MechaHarness today:** Because MechaHarness owns/injects `InferenceStrategy`, native executions have a cleaner seam than a network proxy.

**MH-MHRL-20:** Training-grade capture SHOULD use the narrowest provider-neutral inference seam available. Native MechaHarness executions SHOULD NOT require a network proxy; external black-box harness capture MAY be an integration.

# Recommended architecture additions

The FineEnvs material does not justify replacing MechaHarness architecture. It suggests seven compact additions:

1. `HarnessFingerprint` / richer evaluation provenance.
2. `RolloutGraph` for observed execution topology.
3. Optional `InferenceCapture` capability with explicit capture level.
4. `EvaluationOutcome` evidence taxonomy.
5. Explicit `ObjectivePolicy` / evaluator aggregation provenance.
6. `TraceReconciliation` across independent observations.
7. Harness/config matrix experiments with exposure and compatibility reporting.

These should extend current harness experiment, research, EventLog, graph, inference, linkage, and failure-attribution surfaces rather than creating a parallel subsystem.

# Ownership boundary: MechaHarness vs June

**MechaHarness should own:** reproducible harness/config identity; execution/rollout representations; inference-capture contracts; trace/evaluation provenance; evidence-validity semantics; explicit evaluator aggregation; experiment variation/matrix mechanisms; downstream export surfaces; reusable graph/template mechanisms.

**June should own:** trace retention/privacy policy; nightly/offline mining; training corpus selection; LoRA/SFT/RL recipe choice; checkpoint lifecycle; promotion policy; June-specific graph realizations and soft-point bindings.

In short: **MechaHarness makes execution observable, comparable, reproducible, and optionally training-ready. June decides what to learn.**

# Priority

**P0:** MH-MHRL-01, 06, 07, 12, 13. These close evaluation-correctness holes even without RL.

**P1:** MH-MHRL-03, 09, 17, 18. These improve observed execution and self-improvement.

**P2:** MH-MHRL-04, 05, 16, 20. Optional training readiness.

**P3:** MH-MHRL-02, 08, 14, 15, 19. Experimental sophistication.

# Acceptance-direction sketch

A future implementation pass should turn accepted requirements into MechaHarness user stories/tests rather than implementing directly from this inspiration document. Useful stories include:

- compare the same model/task under two graph configurations and prove which harness/config produced each result;
- reconstruct a retry and dynamically spawned reviewer as distinct RolloutGraph branches;
- reject a training-required graph at linkage when the backend is evaluation-only;
- represent a dead sandbox as execution-failure/unscorable rather than reward zero;
- require explicit objective policy before collapsing evaluator metrics;
- invalidate a rollout when independent gateway capture and EventLog disagree;
- detect repeated task sampling after experiment resume;
- reveal semantic success but invalid tool protocol under another harness;
- report unequal token/call exposure despite equal rollout counts.

# Attribution

Primary inspiration: Adithya S Kolavi, Joel Niklaus, Sergio Paniego Blanco, Leonie Monigatti, Amine Dirhoussi, Ben Burtenshaw, Lewis Tunstall, and Leandro von Werra (2026), **“The ultimate guide to multi-harness RL.”**

This document summarizes and interprets their work for MechaHarness architecture. Proposed requirements are MechaHarness-specific deductions, not claims made by the article authors.
