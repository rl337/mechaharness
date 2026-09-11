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

Install pulls **pyiv** from PyPI (`pyiv>=0.3.0`).

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
- `./containers/run-ci.sh` passes in an Ubuntu 24.04 + Python 3.12 image (same as GitHub Actions)
- `/health` returns `{"status":"ok",...}`

## CI-like container

`containers/` holds an Ubuntu 24.04 + Python 3.12 image that matches
`.github/workflows/ci.yml`. It installs the checkout (`pip install -e ".[dev]"`,
including **pyiv** from PyPI) and runs `./run_checks.sh`.

```bash
./containers/run-ci.sh
```

Pass extra arguments to run a command in that environment after install
(`./containers/run-ci.sh pytest -q tests/test_di.py`).

## Next

- [Architecture](../architecture.md)
- [CLI reference](../reference/cli.md)
- [HTTP API reference](../reference/api.md)
