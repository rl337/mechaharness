# Judge / decide (`judge()`)

Provider-neutral decision inference distinct from chat completions. Models
evaluate supplied `state` against typed questions and return a **Judgement**
(calibrated **signals**). Authority stays in `JudgementPolicy` — models never
grant permission. Tool grants stay on `AccessPolicy`.

## Inference outcomes

| Kind | Type | Module |
|------|------|--------|
| Generative chat / tools | `Completion` (= `CompletionResponse`) | `mechaharness.core.outcomes` |
| Decide / System One | `Judgement` | `mechaharness.inference.judge` |
| Media / artifacts | `Generation` | `mechaharness.core.outcomes` |

## Types

| Kind | Question | Signal |
|------|----------|--------|
| `noul` | yes/no with true/false criteria | `p_true` ∈ [0, 1] |
| `choice` | options with descriptions | `selected` + `probabilities` |
| `score` | min/max + anchors | bounded `value` (+ optional distribution) |

A `Judgement` carries validated `answers`, per-question `errors` (missing ≠ zero
risk), provenance, and usage (`latencyMs`, `physicalCalls`). (`JudgeResult` is a
deprecated alias of `Judgement`.)

## API

```python
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    FixtureJudgeProvider,
    JudgeRequest,
    hash_state,
    judge,
)
from mechaharness.policy import JudgementFacts, JudgementPolicy, JudgementThreshold, decide

state = {"ticket": "double charge"}
judgement = await judge(
    JudgeRequest(
        state=state,
        stateHash=hash_state(state),
        questions=[
            ChoiceQuestion(
                id="route",
                instructions="Which team?",
                options=[
                    ChoiceOption(id="billing", description="Payments"),
                    ChoiceOption(id="other", description="Else"),
                ],
            )
        ],
        questionSetVersion="gate-v1",
    ),
    provider=FixtureJudgeProvider(
        {"route": {"selected": "billing", "probabilities": {"billing": 1.0, "other": 0.0}}}
    ),
)
verdict = decide(
    JudgementFacts(action="route"),
    judgement,
    JudgementPolicy(
        version="gate-v1",
        thresholds=[JudgementThreshold(signal_id="route", allow_choices=["billing", "other"])],
    ),
)
```

## System One adapter

`SystemOneJudgeProvider` posts to `{MECHA_DECIDE_BASE_URL}/v1/systemone`.
Settings (no LAN defaults in the library):

| Setting / env | Purpose |
|---------------|---------|
| `MECHA_DECIDE_BASE_URL` / `Settings.decide_base_url` | Decide server root (no `/v1`) |
| `MECHA_DECIDE_MODEL` / `Settings.decide_model` | Served model id (`laya`, `kev-0.5b`, …) |

```bash
MECHA_LIVE_DECIDE=1 pytest -q tests/test_judge.py -k live_systemone
```

Offline contract coverage uses `FixtureJudgeProvider` and mocked HTTP in
`tests/test_judge.py`. Versioned story cassettes are a follow-on testing layer.

## JudgementPolicy

`mechaharness.policy.decide(facts, judgement, policy) -> Verdict` is pure and
fail-closed (unknown signals deny). Persist with `mechaharness.decisions.DecisionLog`
(`core:decision` + optional `decisions.jsonl`) and replay offline via
`replay_verdict` without tool execution.

## Lanes

Hosts expose `InferenceEnvironment.active_lane()` (`reason` / `decide` /
`media`). Call `assert_compatible(require_lane="decide")` before judge tools;
wrong lane raises `InferenceEnvironmentError` naming `infer load decide-fast`.
