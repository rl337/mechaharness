# Install & quick start

Get a local environment running and issue a first harness run.

## Prerequisites

- Python 3.9+
- A reachable inference backend (cloud API key or local OpenAI-compatible server)

## Steps

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Install pulls **pyiv** from GitHub SSH (`git@github.com:rl337/pyiv.git`, pinned in
`pyproject.toml`). You need SSH access to GitHub. If CI cannot use SSH, clone
pyiv over HTTPS locally and install that checkout — keep a single URL in
`pyproject.toml`.

List what is registered:

```bash
mechaharness backends
mechaharness families
```

### Local LM Studio

```bash
mechaharness run "What is 2+2?" \
  --backend lmstudio \
  --family tool_loop \
  --model local-model
```

### OpenAI

```bash
export MECHA_API_KEY=sk-...
mechaharness run "Hello" --backend openai --model gpt-4o-mini
```

### HTTP API

```bash
mechaharness serve --port 8080
curl -s http://127.0.0.1:8080/health
```

## Verify

- `mechaharness version` prints `0.1.0` (or current)
- `./run_checks.sh` passes from the repo root
- `/health` returns `{"status":"ok",...}`

## Next

- [Architecture](../architecture.md)
- [CLI reference](../reference/cli.md)
- [HTTP API reference](../reference/api.md)
