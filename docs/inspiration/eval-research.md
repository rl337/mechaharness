# MechaHarness Eval Research Brief

## Provenance and source synthesis

This brief was prompted by **Sër Makarevich's X post**:
https://x.com/sermakarevich/status/2106453816757354947

The post surfaced Anthropic's **“Demystifying evals for AI agents”** (published January 9, 2026):
https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

The Anthropic article is written by **Mikaela Grace, Jeremy Hadfield, Rodrigo Olivares, and Jiri De Jonghe**. Credit the X post as the discovery/provenance source and the Anthropic authors as the authors of the article; do not conflate those roles.

### Article conclusions to carry into the research

- Evals are core development infrastructure, not a test suite added after the agent is built.
- A useful agent eval distinguishes the **task**, repeated **trials**, one or more **graders/assertions**, the execution **transcript/trace**, and the actual environment **outcome**.
- Grade the real outcome whenever possible. An agent saying it succeeded is not evidence that the world reached the intended state.
- Prefer deterministic/code graders where the property is objectively checkable; use model graders for semantic or open-ended dimensions and calibrate them against humans.
- Avoid brittle path grading when several valid execution paths exist. Verify required constraints and outcomes rather than overfitting to one expected trajectory.
- Capability and reliability are different. `pass@k` asks whether success can be found across attempts; `pass^k` asks whether success repeats consistently.
- Capability suites should contain unsolved or partially solved work that provides a hill to climb. Once a capability is reliably solved, graduate it into regression coverage.
- Trials need clean, isolated environments so shared state or infrastructure noise does not masquerade as agent quality.
- Eval suites are living artifacts. Inspect traces, audit surprising failures, add real failures back as cases, watch for saturation, and keep graders resistant to loopholes.
- Held-out verification matters for self-improving agents: the signal used to guide improvement must not be the sole signal used to prove that improvement occurred.

## MechaHarness research lens

For every reference below, the planning agent must record:

1. **Article-derived takeaway:** which conclusion above the reference strengthens, qualifies, or challenges.
2. **Reusable mechanism:** the generic primitive, contract, evidence type, execution guarantee, or aggregation rule MechaHarness should expose.
3. **Research ask:** what the paper must resolve before that mechanism is designed.
4. **Boundary check:** anything application-semantic discovered by the paper must be handed upward to June rather than implemented in MechaHarness.

The intended result is not a generic `evals/` subsystem glued beside the harness. Existing tracing and execution evidence should become the substrate from which evaluators can establish typed claims about graph execution.

## Mission

Design the reusable **evaluation substrate** that higher-level systems
such as June can use without embedding application-specific definitions
of quality into MechaHarness.

The planning agent should treat MechaHarness as the layer that makes
graph executions intrinsically observable, evidence-producing,
repeatable, and evaluable. It should **not** define what a good June
research task, reminder, document update, or other application task
means.

## Questions to answer

1.  What evaluator, evidence, verdict, assertion, and aggregation
    primitives belong in MechaHarness?
2.  Which checks can be deterministic, and how should evaluation
    escalate when deterministic evidence is insufficient?
3.  How should graph/node execution expose evidence without forcing all
    evidence into model context?
4.  How should repeated trials, `pass@k`, `pass^k`, uncertainty, cost,
    and latency be represented?
5.  How should evaluators be versioned, composed, calibrated, and held
    out from the agent being improved?
6.  How should routing, retry, escalation, promotion, and
    self-improvement consume structured verdicts?
7.  What extension points must exist for June to supply task-specific
    graders and failure taxonomies?
8.  What must explicitly remain outside MechaHarness?

## Primary research

### Verification and evaluator architecture

-   **The Verification Horizon: No Silver Bullet for Coding Agent
    Rewards**\
    Permanent paper page: https://arxiv.org/abs/2606.26300\
    Study verification as a moving target, proxy-vs-intent failure,
    reward hacking, and the scalability/faithfulness/robustness
    tradeoff. Translate these into held-out evaluator and
    evaluator-versioning requirements.


    **Article-derived takeaway:** The article's warning about loopholes and grader bypasses becomes a first-class architectural concern: an evaluator can become a proxy target rather than a faithful measure of intent.

    **Research ask:** Determine how verification degrades as agents become more capable, which evaluators must be hidden/held out, and how evaluator versions and independent promotion checks should prevent self-improvement from merely learning the test.
-   **Ask, Don't Judge: Binary Questions for Interpretable LLM
    Evaluation and Self-Improvement (BINEVAL)**\
    Permanent paper page: https://arxiv.org/abs/2606.27226\
    Study atomic binary questions as an alternative to opaque holistic
    scores. Consider whether MechaHarness verdicts should be composable
    collections of typed claims/assertions.


    **Article-derived takeaway:** The article recommends clear, structured grading dimensions rather than one vague holistic judgment. BINEVAL pushes that idea toward atomic, interpretable claims.

    **Research ask:** Determine when a verdict should be represented as independently resolvable binary assertions, how uncertainty/unknown should propagate, and how those assertions compose without collapsing diagnostics into an opaque scalar.
-   **JudgeBench: A Benchmark for Evaluating LLM-Based Judges**\
    Permanent paper page: https://arxiv.org/abs/2410.12784\
    Study failure modes of LLM judges and implications for calibration,
    judge selection, confidence, consensus, and escalation.


    **Article-derived takeaway:** The article explicitly says model graders are non-deterministic and must be calibrated against human judgment. JudgeBench supplies the cautionary evidence for treating judges as fallible instruments.

    **Research ask:** Identify judge failure modes, calibration procedures, confidence/consensus strategies, and escalation conditions that should be represented in the eval design.
-   **MiniCheck: Efficient Fact-Checking of LLMs on Grounding
    Documents**\
    Permanent publication page:
    https://aclanthology.org/2024.emnlp-main.499/\
    Study specialized small evaluators as a middle tier between
    deterministic checks and expensive generative judges.


    **Article-derived takeaway:** The article's deterministic-where-possible rule leaves a useful middle tier between code assertions and full generative judges: narrow, cheap learned verifiers.

    **Research ask:** Determine what evidence contract a specialized grounding checker needs, when it is trustworthy enough to stop escalation, and how its confidence should be recorded.
-   **SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for
    Generative Large Language Models**\
    Permanent publication page:
    https://aclanthology.org/2023.emnlp-main.557/\
    Study sampling/consistency-based evidence and where repeated
    inference can provide a useful evaluation signal without external
    ground truth.


    **Article-derived takeaway:** Repeated sampling can itself produce evidence when external ground truth is weak, but consistency is not the same thing as truth.

    **Research ask:** Determine where self-consistency is a useful auxiliary signal, how many samples are justified, and what safeguards keep agreement among generations from being mistaken for verified correctness.
### Reliability and agent-state verification

-   **τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World
    Domains**\
    Permanent paper page: https://arxiv.org/abs/2406.12045\
    Study end-state verification and `pass^k`. Extract reusable
    requirements for trial isolation, state assertions, repeatability,
    and reliability aggregation.


    **Article-derived takeaway:** The article emphasizes grading actual environment outcomes and uses `pass^k` to distinguish reliable agents from agents that merely succeed sometimes.

    **Research ask:** Extract patterns for isolated trials, end-state assertions, policy constraints, repeatability, and reliability aggregation that apply beyond the benchmark's specific domains.
-   **τ²-bench: Evaluating Conversational Agents in a Dual-Control
    Environment**\
    Permanent paper page: https://arxiv.org/abs/2506.07982\
    Study evaluation where both sides of an interaction can take
    actions, with emphasis on traces, state transitions, and outcome
    verification.


    **Article-derived takeaway:** The article notes that interactive agents cannot be judged only from their final prose because both conversation and state transitions matter.

    **Research ask:** Determine how evaluation should represent two-sided actions, intermediate state, user simulation, valid alternate trajectories, and final outcome evidence.
-   **Evaluating Large Language Models Trained on Code**\
    Permanent paper page: https://arxiv.org/abs/2107.03374\
    Use as the foundational `pass@k` reference. Keep capability
    (`pass@k`) distinct from repeated-run reliability (`pass^k`).


    **Article-derived takeaway:** The article uses `pass@k` to measure capability across attempts and contrasts it with `pass^k` reliability.

    **Research ask:** Pin down the statistical meaning and aggregation requirements of `pass@k`, then specify how it should coexist with reliability metrics without conflating 'can solve' with 'can be trusted'.
### Evaluation-framework design

-   **Holistic Evaluation of Language Models (HELM)**\
    Permanent paper page: https://arxiv.org/abs/2211.09110\
    Study standardized scenarios, multiple metrics, reproducibility, and
    transparent raw execution records. Focus on framework abstractions
    rather than HELM's particular benchmark content.


    **Article-derived takeaway:** The article argues against a single score and recommends suites that expose different dimensions, costs, and failure modes.

    **Research ask:** Identify which scenario/metric/reporting abstractions generalize cleanly to agent graphs and how raw evidence should remain inspectable beneath aggregates.
-   **RAGAS: Automated Evaluation of Retrieval Augmented Generation**\
    Permanent paper page: https://arxiv.org/abs/2309.15217\
    Study decomposed, reference-free evaluation dimensions. Ask what
    generic composition mechanisms MechaHarness needs for independently
    evaluable dimensions.


    **Article-derived takeaway:** The article's research-agent guidance decomposes quality into groundedness, coverage, source quality, and answer quality rather than asking one judge whether the answer is 'good'.

    **Research ask:** Determine which decomposed RAG dimensions transfer to agent evaluation, which require references, and how independent dimensions should be composed and diagnosed.
-   **ARES: An Automated Evaluation Framework for Retrieval-Augmented
    Generation Systems**\
    Permanent publication page:
    https://aclanthology.org/2024.naacl-long.20/\
    Study lightweight specialized judges, human calibration,
    prediction-powered inference, and confidence intervals as
    architectural inspiration.


    **Article-derived takeaway:** The article recommends model graders only with calibration. ARES is relevant because it combines lightweight learned judges, human-labelled calibration, and statistical confidence.

    **Research ask:** Determine how small calibration sets, domain adaptation, confidence intervals, and specialized judges could fit a reusable escalation or application-level grading strategy.
## Benchmark patterns to inspect

-   **SWE-bench: Can Language Models Resolve Real-World GitHub
    Issues?**\
    Permanent paper page: https://arxiv.org/abs/2310.06770\
    Focus on reproducible environments, deterministic outcome tests, and
    separating task execution from grading.


    **Article-derived takeaway:** The article treats coding as the clearest example of grading the produced state with reproducible deterministic tests rather than trusting the agent's narration.

    **Research ask:** Extract benchmark-environment patterns for clean setup, outcome testing, regression protection, and separation between the agent harness and evaluation harness.
-   **Demystifying evals for AI agents**\
    Stable article page:
    https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents\
    Use as a practical synthesis of
    task/trial/grader/transcript/outcome/evaluation-harness concepts.
    Treat its distinction between evaluation harness and agent harness
    as especially relevant to the MechaHarness/June boundary.

## Expected planning output

Produce a MechaHarness implementation plan containing:

-   proposed evaluation-domain types and interfaces;
-   evidence and verdict schemas;
-   deterministic/model/human evaluator composition;
-   confidence and uncertainty representation;
-   repeated-trial and reliability aggregation;
-   evaluator calibration and versioning;
-   execution-visible vs held-out evaluation;
-   trace/state/outcome evidence requirements;
-   hooks for routing, retry, escalation, promotion, and
    self-improvement;
-   explicit June-facing extension points;
-   migration path from existing MechaHarness tracing/observability
    rather than replacing it;
-   an explicit **non-goals** section identifying application semantics
    that belong in June.

## Boundary rule

When research suggests a concrete task rubric, benchmark scenario,
product-specific success criterion, or domain failure taxonomy, do
**not** put it into MechaHarness. Record the generic mechanism needed to
express it and hand the semantic requirement to June.