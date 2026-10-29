# Local OpenAI-compat backend (`openai_local`)

Convenience backend name for a LAN OpenAI-compatible server (same client as
`vllm` / `lmstudio` / `openai_compat`). Profile load/unload and model inventory
stay in the host app — MechaHarness only issues chat completions.

Unlike `vllm` / `lmstudio`, this profile does **not** ship a default
`base_url`. Set `MECHA_BASE_URL` explicitly for your server.

## Backend

```bash
export MECHA_BASE_URL=http://127.0.0.1:8000/v1   # or your host's OpenAI-compat URL
export MECHA_API_KEY=local                       # placeholder is fine for local vLLM
export MECHA_MODEL=<served-model-id>

mechaharness run "Reply with ok." \
  --backend openai_local \
  --family pass_through \
  --model "$MECHA_MODEL"
```

Use the **served model id** your server advertises on `/v1/models`, not a
Hugging Face repo id.

Live and offline pytest use the dual-mode **user story** suite (see
[User stories](./user-stories.md)). Offline CI always runs cassettes; live hits
real HTTP for cassette twins **and** static `infer` / `judge` /
`judge_route` walks (`tests/stories/live_capability.py`). Behavioral expects
stay hard; cassette-exact token counts are soft.

```bash
# Full model-using live suite (reason + judge)
MECHA_STORY_BACKEND=live \
  MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
  MECHA_MODEL=qwen3-30b-thinking \
  MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009 \
  MECHA_JUDGE_MODEL=laya \
  MECHA_MAX_TOKENS=1024 \
  pytest -q tests/stories

# Reason-lane filter only
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=openai_compat/qwen3-30b-thinking \
  MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
  pytest -q tests/stories -k nubble_run_cost

# shorthand
MECHA_LIVE_OPENAI_COMPAT=1 MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
  pytest -q tests/stories -k nubble_run_cost
```

## Cursor MCP (guided coding)

For Agentic Recipe `guided_coding`, put the same `MECHA_*` endpoint knobs on the
MCP server `env` in `.cursor/mcp.json` and set `MECHA_MCP_HOST=project_coding`.
That loads `ProjectCodingConfig` (workspace tools + local-work burst). See
[Durable graph generators](../reference/durable-graph-generators.md) and
[guided coding](../reference/graph-templates/guided-coding.md).

A project `.env` is optional and mainly for CLI/`mechaharness run` — hosts need
not create one for MCP.

## Host Config

Discover which profile is loaded, map grants/lane, and attach tools in a host
`MechaHarnessConfig` subclass. Use
`InferenceEnvironment.assert_compatible(require_media=True)`,
`require_lane="judge"`, or required grants to refuse mismatched work.
Prefer `ProjectCodingConfig` when the host is the project workspace itself.

### Judge lane (`MECHA_JUDGE_*`)

Judge is not OpenAI chat. Connection env binds on `APIConnectionConfig`
(`SimpleHttpConnectionConfig.from_env`), not Settings:

```bash
export MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009
export MECHA_JUDGE_PATH=/v1/systemone   # default; override if needed
export MECHA_JUDGE_MODEL=laya

# Judge filter (System One twins) or omit MECHA_STORY_MODEL for all live-eligible
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=systemone/laya \
  MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009 \
  pytest -q tests/stories -k 'refund_verdict or systemone_cassette'
```

Legacy `MECHA_DECIDE_*` env names still work as aliases. Host apps typically load
`decide-fast` / `decide-api` profiles (filenames), expose judge tools, and map
those profiles to lane `judge`. See [Judge reference](../reference/judge.md).

Reason-only profiles must fail judge tools with a clear load hint.
