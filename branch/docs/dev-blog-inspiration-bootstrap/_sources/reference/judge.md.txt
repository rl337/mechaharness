# Judge (`judge()`)

Provider-neutral decision inference distinct from chat completions. Models
evaluate supplied `state` against typed questions and return a **Judgement**
(calibrated **signals**). Authority stays in `JudgementPolicy` — models never
grant permission. Tool grants stay on `AccessPolicy`.

## Inference outcomes

| Kind | Type | Module |
|------|------|--------|
| Generative chat / tools | `Completion` (= `CompletionResponse`) | `mechaharness.core.outcomes` |
| Judge / System One | `Judgement` | `mechaharness.inference.judge` |
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

## Connection (`APIConnectionConfig`)

Judge HTTP reachability is an injectable `APIConnectionConfig` (default:
`SimpleHttpConnectionConfig`). Env knobs bind on the connection via
`from_env()` / `for_judge()` — **not** on `Settings`.

| Env | Purpose |
|-----|---------|
| `MECHA_JUDGE_BASE_URL` | Origin only (e.g. `http://host:8009`) |
| `MECHA_JUDGE_PATH` | Path joined to base (default `/v1/systemone`) |
| `MECHA_JUDGE_URL` | Full endpoint override (ignores base+path) |
| `MECHA_JUDGE_MODEL` | Model id in JSON body |
| `MECHA_JUDGE_API_KEY` | Optional Bearer token |
| `MECHA_JUDGE_TIMEOUT_SECONDS` | HTTP timeout |

Legacy `MECHA_DECIDE_BASE_URL` / `MECHA_DECIDE_MODEL` still apply when the
`MECHA_JUDGE_*` values are unset. Hosts override
`MechaHarnessConfig.get_judge_connection()` for OAuth or other schemes later.
Providers (`JudgeProvider`, `InferenceStrategy`, …) are Config DI injectables —
never fields on `Settings`.

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
from mechaharness.judgement_policy import JudgementFacts, JudgementPolicy, JudgementThreshold, decide

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

```bash
export MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009
export MECHA_JUDGE_MODEL=laya
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=systemone/laya \
  pytest -q tests/stories -k 'refund_verdict or systemone_cassette'
```

Offline CI replays the System One cassette for the same stories (no skip).
See [User stories](../guides/user-stories.md).

## JudgementPolicy

`mechaharness.judgement_policy.decide(facts, judgement, policy) -> Verdict` is pure and
fail-closed (unknown signals deny). Persist with `mechaharness.decision_log.DecisionLog`
and replay offline via `replay_verdict` without tool execution.

## Lanes

Hosts expose `InferenceEnvironment.active_lane()` (`reason` / `judge` /
`media`). Call `assert_compatible(require_lane="judge")` before judge tools;
wrong lane raises `InferenceEnvironmentError` naming the host load hint
(e.g. `infer load decide-fast` while profile filenames catch up).
