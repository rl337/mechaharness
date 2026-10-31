# Local OpenAI-compat backend (`openai_local`)

Convenience backend name for a LAN OpenAI-compatible server (same client as
`vllm` / `lmstudio` / `openai_compat`). Profile load/unload and model inventory
stay in the host app — MechaHarness only issues chat completions.

Unlike `vllm` / `lmstudio`, this profile does **not** ship a default
`base_url`. Set `MECHA_BASE_URL` explicitly for your server.

## Backend

Current lab hosts (OpenAI-compat `/v1`):

| Host | URL | Served id (`MECHA_MODEL`) | Backend |
|------|-----|---------------------------|---------|
| Laptop LM Studio | `http://127.0.0.1:1234/v1` | `qwen/qwen3.6-35b-a3b` (load in LM Studio) | `lmstudio` |
| LAN Nemotron Super VL | `http://192.168.1.21:8000/v1` | `nemotron-3.5-super-vl` | `openai_local` / `openai_compat` |

```bash
# LAN Nemotron
export MECHA_BASE_URL=http://192.168.1.21:8000/v1
export MECHA_API_KEY=local
export MECHA_MODEL=nemotron-3.5-super-vl

# or laptop LM Studio (defaults also work with --backend lmstudio):
# export MECHA_BASE_URL=http://127.0.0.1:1234/v1
# export MECHA_API_KEY=lm-studio
# export MECHA_MODEL=qwen/qwen3.6-35b-a3b

mechaharness run "Reply with ok." \
  --backend openai_local \
  --family pass_through \
  --model "$MECHA_MODEL"
```

Use the **served model id** your server advertises on `/v1/models`, not a
Hugging Face repo id. Nemotron emits reasoning tokens before `content`; prefer
`MECHA_MAX_TOKENS` ≥ 2048 so short replies are not truncated to empty content.

Live and offline pytest use the dual-mode **user story** suite (see
[User stories](./user-stories.md)). Offline CI always runs cassettes; live hits
real HTTP for cassette twins **and** static `infer` / `judge` /
`judge_route` walks (`tests/stories/live_capability.py`). Behavioral expects
stay hard; cassette-exact token counts are soft.

```bash
# Full model-using live suite against LAN Nemotron
MECHA_STORY_BACKEND=live \
  MECHA_BASE_URL=http://192.168.1.21:8000/v1 \
  MECHA_MODEL=nemotron-3.5-super-vl \
  MECHA_MAX_TOKENS=2048 \
  pytest -q tests/stories

# Same against laptop LM Studio (+ optional judge)
MECHA_STORY_BACKEND=live \
  MECHA_BASE_URL=http://127.0.0.1:1234/v1 \
  MECHA_MODEL=qwen/qwen3.6-35b-a3b \
  MECHA_JUDGE_BASE_URL=http://127.0.0.1:8009 \
  MECHA_JUDGE_MODEL=laya \
  MECHA_MAX_TOKENS=1024 \
  pytest -q tests/stories

# Reason-lane filter only (cassette path filter ≠ served id)
MECHA_STORY_BACKEND=live MECHA_STORY_MODEL=openai_compat/qwen-qwen3.6-35b-a3b \
  MECHA_BASE_URL=http://127.0.0.1:1234/v1 \
  MECHA_MODEL=qwen/qwen3.6-35b-a3b \
  pytest -q tests/stories -k nubble_run_cost

# shorthand (legacy alias still points at the Qwen cassette path)
MECHA_LIVE_QWEN=1 MECHA_BASE_URL=http://127.0.0.1:1234/v1 \
  MECHA_MODEL=qwen/qwen3.6-35b-a3b \
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
