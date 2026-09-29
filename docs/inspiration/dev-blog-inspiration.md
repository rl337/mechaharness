# Developer Blog Inspiration for MechaHarness / June

> Living design-notes document. External developer material is evidence and inspiration, not specification. Requirements below generalize ideas only where they strengthen MechaHarness and June.

Last reviewed: 2026-09-29

## Purpose

This document tracks useful agent-harness ideas from Claude/Anthropic and Cursor and translates them into testable MechaHarness requirements. It is deliberately provenance-heavy: every inspiration-derived requirement names the source material that motivated it. The goal is not product compatibility. It is to challenge MechaHarness assumptions against production agent systems and retain only patterns that generalize.

## Requirements

### 1. Harness scaffolding must be revisable and retirable

**Sources**
- Claude, **Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence** (2026-04-02): https://claude.com/blog/harnessing-claudes-intelligence
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness
- Cursor, **Improved token efficiency for longer agent runs** (2026-09-23): https://cursor.com/blog/improved-token-efficiency

**Requirements**
- Orchestration policy SHOULD be replaceable configuration rather than permanent intelligence embedded in framework code.
- Every nontrivial intervention SHOULD identify the failure mode it addresses and evidence for its existence.
- Harness experiments SHOULD compare execution with and without an intervention.
- Model/runtime upgrades SHOULD trigger retirement tests for existing scaffolding.
- Policies that no longer improve outcomes SHOULD be removable without changing task semantics.
- Token, latency, compute, memory and coordination overhead SHOULD count against retaining scaffolding.

For June, stronger local models should be allowed to absorb work previously supplied by explicit scaffolding rather than leaving a fossil layer of obsolete prompts and control logic.

### 2. Primitive linkage and runtime graph resolution are distinct

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- Cursor, **What we've learned building cloud agents** (2026-06-02): https://cursor.com/blog/cloud-agent-lessons

**Requirements**
- Primitive validation MUST determine whether an executable has its required injectable dependencies.
- Graph resolution MUST separately determine whether the final runtime-composed graph has satisfiable edges, contracts, permissions, models, tools, environment capabilities and termination paths.
- Runtime-composed graphs MUST support a pre-execution resolution phase after final configuration is known.
- Detectable missing/incompatible linkage MUST fail before substantive execution.
- Diagnostics SHOULD identify the unsatisfied edge/capability and candidate provider rather than surface an arbitrary downstream failure.

This permits template subgraphs to remain intentionally partial until instantiated.

### 3. Dynamic subgraphs are first-class

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code

**Requirements**
- A node MAY instantiate a subordinate graph at runtime.
- Dynamic subgraphs MUST have explicit input/output contracts and execution budgets.
- Fan-out, aggregation, independent review, adversarial/refutation passes and iterative repair SHOULD be reusable graph patterns.
- Runtime-generated graphs MUST undergo the same linkage, capability, security and termination validation as static graphs.
- Dynamic subgraphs SHOULD remain observable as graph executions rather than opaque nested model calls.
- Reusable template subgraphs SHOULD be parameterized rather than cloned into task-specific code.

### 4. Repeating execution requires an explicit stop contract

**Sources**
- Claude, **Loop engineering: Getting started with loops** (2026-06-30): https://claude.com/blog/getting-started-with-loops

**Requirements**
Every repeating graph/subgraph MUST expose a trigger, continuation condition, success/stop condition, failure/abort condition, progress signal, carried state, and applicable iteration/time/token/cost budgets. A loop without a bounded or externally resolvable stop condition SHOULD fail validation unless explicitly declared a persistent service loop.

### 5. Verification is part of execution

**Sources**
- Claude, **Building verification loops in Claude Code with skills** (2026-07-22): https://claude.com/blog/building-verification-loops-in-claude-code-with-skills
- Claude, **How Anthropic runs large-scale code migrations with Claude Code** (2026-07-16): https://claude.com/blog/ai-code-migration
- Claude, **Agentic coding is straining CI. Here's how we scaled test impact analysis at Anthropic** (2026-09-14): https://claude.com/blog/agentic-coding-is-straining-ci-heres-how-we-scaled-test-impact-analysis-at-anthropic

**Requirements**
- Verification SHOULD be an explicit graph phase or injectable policy.
- Deterministic verification SHOULD be preferred when a deterministic oracle exists.
- Evaluator-model verification SHOULD use isolated context where independence matters.
- Verification results MUST be structured enough to route repair.
- Completion MUST be able to depend on verification state; "answer generated" and "task complete" are distinct.
- VerificationPolicy SHOULD support impact-based selection and choose the smallest sufficient verification set when dependency/confidence information permits.
- High-consequence changes MAY force exhaustive verification.
- Verification cost, latency, failures and marginal detection value SHOULD be observable.

