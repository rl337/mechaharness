# CLI reference

Entrypoint: `mechaharness` (`mechaharness.cli.main:app`)

## Commands

| Command | Purpose |
|---------|---------|
| `version` | Print package version |
| `backends` | List configured inference backends |
| `families` | List configured harness families |
| `run` | Run one prompt via Agentic Recipe `harness_run` |
| `serve` | Start the FastAPI server |
| `describe` | Backend metadata via Agentic Recipe `backend_describe` |
| `recipes list` | Catalog ids **and descriptions** (summaries) |
| `recipes show` | Full pydoc (module + class, including examples) + soft points |
| `recipes render` | SVG flowchart (own layout engine) + explanations below |
| `recipes run` | Execute a recipe (`harness_run` / `backend_describe` ship runners) |

## `run`

| Flag | Env / default | Description |
|------|---------------|-------------|
| `PROMPT` (arg) | — | User prompt |
| `--backend` / `-b` | `MECHA_INFERENCE_BACKEND` (`openai`) | Inference backend name |
| `--family` / `-f` | `MECHA_HARNESS_FAMILY` (`tool_loop`) | Harness family (`pass_through`, `tool_loop`, …) |
| `--model` / `-m` | `MECHA_MODEL` | Model id |
| `--api-key` | `MECHA_API_KEY` | Provider API key |
| `--base-url` | `MECHA_BASE_URL` | Override endpoint |
| `--system` | `MECHA_SYSTEM_PROMPT` | System prompt |
| `--max-turns` | `8` | Agent loop limit |
| `--json` | off | Machine-readable result |

## `recipes`

```bash
mechaharness recipes list
mechaharness recipes show harness_run
mechaharness recipes render harness_run
mechaharness recipes render harness_run -o /tmp/harness_run.svg --tool lookup
mechaharness recipes run harness_run --soft prompt="hello" --soft backend=mock
```

`list` prints each catalog id with its human **summary** (what the recipe does).
`show` prints that summary plus the full template **pydoc** (module + class
docstrings, including `Example:` blocks) and the soft-point table. `--json`
includes a `doc` field from `GraphTemplate.describe()`.

`render` instantiates the recipe (with safe defaults / `--soft` / `--input`),
derives [node components](./node-components.md), and writes an **SVG** from
MechaHarness's layout engine (`recipe_diagram` — no Mermaid/Graphviz). Default
output path is `NAME.svg` in the cwd (`--out` / `-o` to override). Outer edges
are recipe execution (`prepare` → `harness_loop` → `render`), attaching to the
**container box** whose **title is the graph node name** (e.g. `harness_loop`).
Interiors use flowchart **start/end circles** and sequential `then` edges, laid
out about **three steps per row**. Parallel fan-out / fan-in siblings collapse
into one **stack band** with a single outer arrow (no lines crossing sibling
boxes). Configuration soft points are **ER-style tables** (`name | type |
value`) on leaf nodes. Concrete steps stay **square**. Explanations follow
**below**. Use `--tool NAME` to preview planned tool steps.

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

Runs Agentic Recipe `backend_describe` (Strategy `describe()` metadata).
