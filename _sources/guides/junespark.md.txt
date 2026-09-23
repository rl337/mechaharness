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

Live pytest (skipped in CI):

```bash
MECHA_LIVE_JUNESPARK=1 \
  MECHA_BASE_URL=http://127.0.0.1:8000/v1 \
  MECHA_MODEL=<served-model-id> \
  pytest -q tests/test_live_junespark.py
```

## Host Config

Discover which profile is loaded, map grants, and attach media tools in a host
`MechaHarnessConfig` subclass. Use
`InferenceEnvironment.assert_compatible(require_media=True)` (or required
grants) to refuse media work while a reason-only profile is active.
