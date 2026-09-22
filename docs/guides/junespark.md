# Local OpenAI-compat backend (`junespark`)

Convenience backend name for a LAN OpenAI-compatible server (same client as
`vllm` / `lmstudio`). Profile load/unload and model inventory stay in the host
app — MechaHarness only issues chat completions.

## Backend

```bash
mechaharness run "Reply with ok." \
  --backend junespark \
  --family pass_through \
  --model <served-model-id>
```

Default base URL is `http://192.168.1.21:8000/v1` with a placeholder API key.
Override with `MECHA_BASE_URL` / `MECHA_MODEL` / `MECHA_API_KEY` as needed.
Use the **served model id** your server advertises on `/v1/models`, not a
Hugging Face repo id.

Live pytest (skipped in CI):

```bash
MECHA_LIVE_JUNESPARK=1 MECHA_MODEL=<served-model-id> \
  pytest -q tests/test_live_junespark.py
```

## Host Config

Discover which profile is loaded, map grants, and attach media tools in a host
`MechaHarnessConfig` subclass. Use
`InferenceEnvironment.assert_compatible(require_media=True)` (or required
grants) to refuse media work while a reason-only profile is active.
