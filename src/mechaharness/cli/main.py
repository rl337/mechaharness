"""Command-line interface."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from mechaharness import __version__
from mechaharness.config import Settings, get_settings
from mechaharness.core.contract import RunRequest
from mechaharness.di import list_harness_families, list_inference_backends
from mechaharness.factory import run as run_harness
from mechaharness.graph_templates.base import GraphTemplateParams
from mechaharness.recipe_runner import (
    describe_recipe,
    list_recipes,
    run_backend_describe_recipe,
    run_recipe,
)

app = typer.Typer(
    name="mechaharness",
    help="Agentic harness CLI — swap inference backends and harness families.",
    no_args_is_help=True,
)
recipes_app = typer.Typer(
    help="Discover and run Agentic Recipes (GraphTemplate catalog).",
    no_args_is_help=True,
)
app.add_typer(recipes_app, name="recipes")
console = Console()


@app.command("version")
def version() -> None:
    """Print package version."""
    console.print(__version__)


@app.command("backends")
def backends() -> None:
    """List configured inference backends."""
    table = Table(title="Inference backends")
    table.add_column("Name")
    for name in list_inference_backends():
        table.add_row(name)
    console.print(table)


@app.command("families")
def families() -> None:
    """List configured harness families."""
    table = Table(title="Harness families")
    table.add_column("Name")
    for name in list_harness_families():
        table.add_row(name)
    console.print(table)


@app.command("run")
def run(
    prompt: str = typer.Argument(..., help="User prompt to send through the harness"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="Inference backend"),
    family: Optional[str] = typer.Option(None, "--family", "-f", help="Harness family"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model id"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="MECHA_API_KEY"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    system_prompt: Optional[str] = typer.Option(None, "--system"),
    max_turns: int = typer.Option(8, "--max-turns"),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Run a single prompt through the harness_run Agentic Recipe."""
    request = RunRequest(
        prompt=prompt,
        backend=backend,
        family=family,
        model=model,
        api_key=api_key,
        base_url=base_url,
        system_prompt=system_prompt,
        max_turns=max_turns,
    )

    async def _run() -> None:
        result = await run_harness(request)
        if json_out:
            console.print_json(data=result.model_dump(mode="json"))
        else:
            console.print(Markdown(result.final_text or ""))
            console.print(
                f"\n[dim]turns={result.turns} family="
                f"{request.family or get_settings().harness_family} "
                f"backend={request.backend or get_settings().inference_backend}[/dim]"
            )

    asyncio.run(_run())


@app.command("serve")
def serve(
    host: Optional[str] = typer.Option(None, "--host"),
    port: Optional[int] = typer.Option(None, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the HTTP API server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mechaharness.api.app:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
    )


@app.command("describe")
def describe_cmd(
    backend: str = typer.Argument(..., help="Backend name to instantiate and describe"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="MECHA_API_KEY"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
) -> None:
    """Show metadata for a configured inference backend (backend_describe recipe)."""
    env = get_settings()
    settings = Settings(
        inference_backend=backend,
        api_key=api_key if api_key is not None else env.api_key,
        base_url=base_url if base_url is not None else env.base_url,
        model=model or env.model,
    )
    meta = asyncio.run(run_backend_describe_recipe(settings))
    console.print(json.dumps(meta, indent=2))


@recipes_app.command("list")
def recipes_list(
    all_status: bool = typer.Option(
        False, "--all", help="Include deprecated / demoted recipes"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """List Agentic Recipes with catalog id and description (summary)."""
    catalog = list_recipes(active_only=not all_status)
    if json_out:
        console.print_json(data=catalog)
        return
    table = Table(title="Agentic Recipes", show_lines=True)
    table.add_column("Name", style="bold", no_wrap=True)
    table.add_column("Version", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Description", overflow="fold")
    for entry in catalog:
        table.add_row(
            str(entry.get("name", "")),
            str(entry.get("version", "")),
            str(entry.get("status", "")),
            str(entry.get("summary") or entry.get("doc") or ""),
        )
    console.print(table)
    console.print(
        "[dim]Use `recipes show NAME` for full pydoc; "
        "`recipes render NAME` for an SVG flowchart + explanations.[/dim]"
    )


@recipes_app.command("show")
def recipes_show(
    name: str = typer.Argument(..., help="Recipe catalog id"),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show one Agentic Recipe: full pydoc (with examples) and soft points."""
    try:
        meta = describe_recipe(name)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_out:
        console.print_json(data=meta)
        return
    console.print(f"[bold]{meta['name']}[/bold] v{meta.get('version', '?')}")
    console.print(f"status={meta.get('status')} category={meta.get('category')}")
    if meta.get("summary"):
        console.print(f"\n[bold]Summary[/bold]\n{meta['summary']}")
    doc = str(meta.get("doc") or "").strip()
    if doc:
        console.print("\n[bold]Documentation[/bold]")
        console.print(Markdown(doc))
    soft = meta.get("soft_points") or []
    if soft:
        table = Table(title="Soft points", show_lines=True)
        table.add_column("Name", no_wrap=True)
        table.add_column("Kind", no_wrap=True)
        table.add_column("Required", no_wrap=True)
        table.add_column("Description", overflow="fold")
        for point in soft:
            table.add_row(
                str(point.get("name", "")),
                str(point.get("kind", "")),
                "yes" if point.get("required") else "no",
                str(point.get("description", "")),
            )
        console.print(table)


@recipes_app.command("render")
def recipes_render(
    name: str = typer.Argument(..., help="Recipe catalog id"),
    soft: Optional[list[str]] = typer.Option(
        None,
        "--soft",
        help="Soft binding KEY=VALUE (repeatable)",
    ),
    input_kv: Optional[list[str]] = typer.Option(
        None,
        "--input",
        help="Input KEY=VALUE (repeatable)",
    ),
    goal: Optional[str] = typer.Option(None, "--goal", help="Graph goal override"),
    tool: Optional[list[str]] = typer.Option(
        None,
        "--tool",
        help="Planned tool name for tool_call components (repeatable)",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Write SVG diagram here (default: NAME.svg in cwd)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Draw a flowchart of recipe nodes and node components.

    Writes an SVG from MechaHarness's layout engine; node/component explanations
    (soft-point and kind prose) are printed below so shapes stay small.
    """
    from mechaharness.recipe_render import format_render_document, render_recipe

    soft_bindings = _parse_kv(soft or [])
    inputs = _parse_kv(input_kv or [])
    try:
        result = render_recipe(
            name,
            soft_bindings=soft_bindings,
            inputs=inputs,
            goal=goal,
            tool_names=tool,
        )
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]render failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_out:
        console.print_json(data=result.model_dump(mode="json"))
        return
    svg_path = out or Path(f"{name}.svg")
    svg_path.write_text(result.svg, encoding="utf-8")
    console.print(f"Wrote [cyan]{svg_path}[/cyan]")
    console.print(Markdown(format_render_document(result, svg_path=str(svg_path))))


@recipes_app.command("run")
def recipes_run(
    name: str = typer.Argument(..., help="Recipe catalog id"),
    soft: Optional[list[str]] = typer.Option(
        None,
        "--soft",
        help="Soft binding KEY=VALUE (repeatable)",
    ),
    input_kv: Optional[list[str]] = typer.Option(
        None,
        "--input",
        help="Input KEY=VALUE (repeatable)",
    ),
    goal: Optional[str] = typer.Option(None, "--goal", help="Graph goal override"),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Instantiate and execute a recipe that has library default runners.

    Recipes that need host-only runners (most control patterns) will fail
    linkage unless you bind runners in a host app. CLI-owned recipes
    ``harness_run`` and ``backend_describe`` ship with default runners.
    """
    from mechaharness.recipe_runner import default_recipe_runners, run_harness_recipe

    soft_bindings = _parse_kv(soft or [])
    inputs = _parse_kv(input_kv or [])

    async def _run() -> None:
        if name == "harness_run":
            prompt = str(
                soft_bindings.get("prompt")
                or inputs.get("prompt")
                or ""
            )
            if not prompt:
                console.print(
                    "[red]harness_run requires --soft prompt=... "
                    "or --input prompt=...[/red]"
                )
                raise typer.Exit(code=1)
            request = RunRequest(
                prompt=prompt,
                backend=soft_bindings.get("backend") or inputs.get("backend"),
                family=soft_bindings.get("family") or inputs.get("family"),
                model=soft_bindings.get("model") or inputs.get("model"),
                api_key=soft_bindings.get("api_key") or inputs.get("api_key"),
                base_url=soft_bindings.get("base_url") or inputs.get("base_url"),
                system_prompt=soft_bindings.get("system_prompt")
                or inputs.get("system_prompt"),
                max_turns=int(
                    soft_bindings.get("max_turns")
                    or inputs.get("max_turns")
                    or 8
                ),
            )
            result = await run_harness_recipe(request)
            if json_out:
                console.print_json(data=result.model_dump(mode="json"))
            else:
                console.print(Markdown(result.final_text or ""))
            return

        if name == "backend_describe":
            backend = soft_bindings.get("backend") or inputs.get("backend")
            if not backend:
                console.print("[red]backend_describe requires --soft backend=...[/red]")
                raise typer.Exit(code=1)
            env = get_settings()
            settings = Settings(
                inference_backend=str(backend),
                api_key=soft_bindings.get("api_key") or env.api_key,
                base_url=soft_bindings.get("base_url") or env.base_url,
                model=soft_bindings.get("model") or env.model,
            )
            meta = await run_backend_describe_recipe(settings)
            if json_out:
                console.print_json(data=meta)
            else:
                console.print(json.dumps(meta, indent=2))
            return

        params = GraphTemplateParams(
            goal=goal or name,
            soft_bindings=soft_bindings,
            inputs=inputs,
        )
        graph_result = await run_recipe(
            name,
            params=params,
            runners=default_recipe_runners(),
        )
        payload = {
            "status": graph_result.status,
            "error": graph_result.error,
            "template_name": graph_result.graph.template_name,
            "nodes": {
                nid: {"kind": n.kind, "status": n.status.value, "payload": n.payload}
                for nid, n in graph_result.graph.nodes.items()
            },
        }
        if json_out:
            console.print_json(data=payload)
        else:
            console.print(
                f"status={graph_result.status} "
                f"template={graph_result.graph.template_name}"
            )
            if graph_result.error:
                console.print(f"[red]{graph_result.error}[/red]")
            for nid, n in graph_result.graph.nodes.items():
                console.print(f"  {nid}: {n.kind} → {n.status.value}")

    asyncio.run(_run())


def _parse_kv(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"expected KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value
    return out


if __name__ == "__main__":
    app()
