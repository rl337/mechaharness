# CLI reference

Entrypoint: `mechaharness` (`mechaharness.cli.main:app`)

## Commands

| Command | Purpose |
|---------|---------|
| `version` | Print package version |
| `backends` | List registered inference backends |
| `families` | List registered harness families |
| `run` | Run one prompt through a harness |
| `serve` | Start the FastAPI server |
| `describe` | Show metadata for a configured backend |

## `run`

| Flag | Env / default | Description |
|------|---------------|-------------|
| `PROMPT` (arg) | — | User prompt |
| `--backend` / `-b` | `MECHA_INFERENCE_BACKEND` (`openai`) | Inference backend name |
| `--family` / `-f` | `MECHA_HARNESS_FAMILY` (`tool_loop`) | Harness family |
| `--model` / `-m` | `MECHA_MODEL` | Model id |
| `--api-key` | `MECHA_API_KEY` | Provider API key |
| `--base-url` | `MECHA_BASE_URL` | Override endpoint |
| `--system` | `MECHA_SYSTEM_PROMPT` | System prompt |
| `--max-turns` | `8` | Agent loop limit |
| `--json` | off | Machine-readable result |

## `serve`

| Flag | Env / default | Description |
|------|---------------|-------------|
| `--host` | `MECHA_HOST` (`127.0.0.1`) | Bind host |
| `--port` | `MECHA_PORT` (`8080`) | Bind port |
| `--reload` | off | Uvicorn auto-reload |

## `describe`

```bash
mechaharness describe lmstudio
```

Prints JSON from `InferenceStrategy.describe()` (name, base_url, model, auth).
