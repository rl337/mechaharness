# HTTP API reference

App: `mechaharness.api.app:app`  
Stability: evolving (v1)

## Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness + version |
| `GET` | `/backends` | Registered inference backends |
| `GET` | `/families` | Registered harness families |
| `POST` | `/v1/run` | Run a prompt through a harness |

## `POST /v1/run`

### Request body

| Field | Type | Notes |
|-------|------|-------|
| `prompt` | string | Required |
| `backend` | string? | Defaults from settings |
| `family` | string? | Defaults from settings |
| `model` | string? | Defaults from settings |
| `api_key` | string? | Optional override |
| `base_url` | string? | Optional override |
| `system_prompt` | string? | Optional |
| `max_turns` | int | Default `8` |
| `temperature` | float? | Optional |

### Response body

| Field | Type | Notes |
|-------|------|-------|
| `final_text` | string? | Model’s final answer |
| `turns` | int | Loop iterations used |
| `messages` | object[] | Full transcript |
| `events` | object[] | Turn / tool observability events |

### Example

```bash
curl -s http://127.0.0.1:8080/v1/run \
  -H 'content-type: application/json' \
  -d '{
    "prompt": "What is 2+2?",
    "backend": "lmstudio",
    "family": "tool_loop",
    "model": "local-model"
  }'
```
