# Local OpenAI-compat backend (`junespark`)

Convenience backend name for a LAN OpenAI-compatible server (same client as
`vllm` / `lmstudio`). Profile load/unload and model inventory stay in the host
app — MechaHarness only issues chat completions.

## Backend

Set the server URL and served model id explicitly (the library does not ship a
private LAN default):

```bash
export MECHA_BASE_URL=http://127.0.0.1:8000/v1   # or your host's OpenAI-compat URL
export MECHA_API_KEY=junespark                   # placeholder is fine for local vLLM
export MECHA_MODEL=<served-model-id>

mechaharness run "Reply with ok." \
  --backend junespark \
  --family pass_through \
  --model "$MECHA_MODEL"
```

Use the **served model id** your server advertises on `/v1/models`, not a
Hugging Face repo id.

Live and offline pytest use the dual-mode **user story** suite (see
[User stories](./user-stories.md)). Offline CI always runs cassettes; live is
the same tests with real HTTP:

```bash
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=openai_compat/qwen3-30b-thinking \
  MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
  pytest -q tests/stories -k nubble_run_cost

# shorthand
MECHA_LIVE_JUNESPARK=1 MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
  pytest -q tests/stories -k nubble_run_cost
```

## Host Config

Discover which profile is loaded, map grants/lane, and attach tools in a host
`MechaHarnessConfig` subclass. Use
`InferenceEnvironment.assert_compatible(require_media=True)`,
`require_lane="judge"`, or required grants to refuse mismatched work.

### Judge lane (`MECHA_JUDGE_*`)

Judge is not OpenAI chat. Connection env binds on `APIConnectionConfig`
(`SimpleHttpConnectionConfig.from_env`), not Settings:

```bash
export MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009
export MECHA_JUDGE_PATH=/v1/systemone   # default; override if needed
export MECHA_JUDGE_MODEL=laya

MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=systemone/laya \
  pytest -q tests/stories -k 'refund_verdict or systemone_cassette'
```

Legacy `MECHA_DECIDE_*` env names still work as aliases. Host apps typically load
`decide-fast` / `decide-api` profiles (filenames), expose judge tools, and map
those profiles to lane `judge`. See [Judge reference](../reference/judge.md).

Reason-only profiles must fail judge tools with a clear load hint.
