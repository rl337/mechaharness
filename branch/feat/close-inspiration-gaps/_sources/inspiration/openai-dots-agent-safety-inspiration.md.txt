# Inspiration: OpenAI Dots, Scoped Execution and Agent Safety

Status: proposed requirements, no implementation implied.

## Primary sources and provenance

- OpenAI, [Introducing dots](https://openai.com/index/introducing-dots/) (2026-09-29).
- OpenAI, [Getting started with your dot](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot).
- OpenAI, [Dots privacy, security and safety FAQs](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs).
- OpenAI, [GPT-6 Astra system card, Dots appendix](https://deploymentsafety.openai.com/gpt-6-astra/sec:appendix-sol-luna).
- Secondary synthesis: *Always-On Agent Architecture: 6 Layers That Turn a Chatbot Into an Agent That Works While You Sleep*, first-page screenshot attributed to @chooppylug1, supplied by user. This is not an OpenAI paper; original complete PDF not independently located.

The source materials describe a product and evaluations, not a drop-in reference implementation. Numeric evaluation findings below are OpenAI-reported and must be checked against exact methodology before being used as release gates.


## Principle
Persistent context must never imply persistent permission. MechaHarness is responsible for generic enforceable graph execution, independent action review, and resumable authorization. June is responsible for goals, memory, and configuring user-facing policy.

## Proposed requirements
1. **MH-DOTS-01 Capability-scoped execution token.** Every graph invocation carries a principal, goal/run identity, allowed operations/resources, expiry, trust origin and policy revision/authorization epoch. Child graphs receive attenuated authority only. *Test:* unrelated job or subgraph cannot inherit permission for an external send.
2. **MH-DOTS-02 Revalidate before consequential side effects.** Recheck authority at action dispatch, not merely at graph start, approval capture, or checkpoint creation. *Test:* a paused graph resumed after revocation cannot publish, even if the prior plan said approved.
3. **MH-DOTS-03 Separate Observe, Prepare and Execute tool classes.** Read-only observers cannot invoke mutating tools; preparation returns typed proposals; execution gates mutating calls. *Test:* a tool alias cannot bypass an observer restriction.
4. **MH-DOTS-04 Independent action review.** Review proposed action, exact arguments, intended effect, provenance, goal scope and current policy. Return typed allow/deny/request-approval with reason codes. Deterministic hard denials take precedence; model review handles ambiguity and cannot override them. *Test:* unsafe recipient or payload is denied even if plan narrative says safe.
5. **MH-DOTS-05 Denial persistence and equivalent-action detection.** Track denied intent and side-effect class through graph retries and delegated paths. *Test:* a denied send cannot be retried through a second provider or tool without new explicit authorization.
6. **MH-DOTS-06 Checkpoint and replay safety.** Persist authorization epoch, pending reviews, idempotency keys, tool-effect ledger and conflict-resolution checkpoint state. *Test:* crash at each pre/post side-effect boundary does not duplicate an external operation.
7. **MH-DOTS-07 Cross-task context isolation.** Scope task-local evidence, policy, memory references and approval artifacts. Sharing requires explicit typed handoff. *Test:* five- and ten-intervening-task scenarios cannot contaminate the final task's authority.
8. **MH-DOTS-08 Safety evaluation recipes.** Reusable fixtures for prompt injection in tool output, scope bleed, changing authorization, ambiguous consent, warning disregard, and false-denial controls. Report outcome, severity, context and model/recipe version.
9. **MH-DOTS-09 Review observability.** Trace review decision, policy revision, source trust, delegated scope, denial reason, user approval and actual side effects. *Test:* audit reconstructs why a consequential action occurred without relying on model recollection.

## Evidence and caution
- The Dots system-card appendix describes an evaluation with 0 scored successful attacks across 16,600 injected emails in 100 simulated rollouts. This is narrow and not evidence of universal injection immunity.
- OpenAI reports 8.6% vs 19.7% moderate-severity scope violations after five vs ten intervening tasks in one persistent-environment setup; this motivates tests, not a universal drift coefficient.
- OpenAI reports 45/49 changing-authorization alignment passes, including 17/17 explicit permission-change cases; ambiguity remains relevant.
- OpenAI also evaluated reviewer false denials and unwanted persistence. A safety gate must be effective *and* operationally usable.
- The six-layer diagram in the supplied screenshot is a third-party synthesis, not a published OpenAI protocol.

## Architecture alignment
Integrate with existing hard/soft nodes, graph recipes, resumable execution and conflict resolution. A decision becomes checkpoint-eligible only when the required conflict resolution has settled; approval must still be revalidated when the action is actually dispatched. Avoid adding duplicate graph primitives if equivalent contracts exist.

## TODO / open decisions
- [ ] Inventory existing policy, execution context, delegation and checkpoint implementations.
- [ ] Specify authority token/epoch schema, revocation lookup and offline behaviour.
- [ ] Decide how denial equivalence and tool aliases are classified.
- [ ] Specify independent reviewer independence, model routing and cost budgets.
- [ ] Define irreversible effect ledger and crash injection matrix.
- [ ] Build source-faithful multi-task evaluation fixtures with negative and false-positive tests.
- [ ] Define typed contracts with June goal orchestration and user approval UX.

## Incremental plan
Start with scoped authority and action-time revalidation, then review and denial propagation, then crash/replay and cross-task evaluation suites. No runtime changes are proposed in this documentation PR.
