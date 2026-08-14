"""Command-line interface."""

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from mechaharness import __version__
from mechaharness.config import get_settings
from mechaharness.factory import build_harness, build_inference
from mechaharness.harness.registry import list_harness_families
from mechaharness.inference.registry import list_inference_backends
from mechaharness.tools.base import ToolRegistry

app = typer.Typer(
    name="mechaharness",
    help="Agentic harness CLI — swap inference backends and harness families.",
    no_args_is_help=True,
)
console = Console()


def _default_tools() -> ToolRegistry:
    tools = ToolRegistry()

    @tools.tool(
        description="Echo text back. Useful as a smoke-test tool.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def echo(text: str) -> str:
        return text

    @tools.tool(
        description="Add two numbers.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    )
    def add(a: float, b: float) -> str:
        return str(a + b)

    return tools


@app.command("version")
def version() -> None:
    """Print package version."""
    console.print(__version__)


@app.command("backends")
def backends() -> None:
    """List registered inference backends."""
    table = Table(title="Inference backends")
    table.add_column("Name")
    for name in list_inference_backends():
        table.add_row(name)
    console.print(table)


@app.command("families")
def families() -> None:
    """List registered harness families."""
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
    """Run a single prompt through the configured harness."""
    settings = get_settings()
    backend_name = backend or settings.inference_backend
    family_name = family or settings.harness_family
    model_name = model or settings.model
    key = api_key if api_key is not None else settings.api_key
    url = base_url if base_url is not None else settings.base_url
    sys_prompt = system_prompt if system_prompt is not None else settings.system_prompt

    inference_kwargs: dict = {}
    if key is not None:
        inference_kwargs["api_key"] = key
    if url is not None:
        inference_kwargs["base_url"] = url

    async def _run() -> None:
        inference = build_inference(backend_name, model=model_name, **inference_kwargs)
        try:
            harness = build_harness(
                family_name,
                inference=inference,
                model=model_name,
                tools=_default_tools(),
                system_prompt=sys_prompt,
                max_turns=max_turns,
            )
            result = await harness.run(prompt)
        finally:
            await inference.aclose()

        if json_out:
            console.print_json(data=result.model_dump())
        else:
            console.print(Markdown(result.final_text or ""))
            console.print(
                f"\n[dim]turns={result.turns} family={family_name} backend={backend_name}[/dim]"
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
def describe(
    backend: str = typer.Argument(..., help="Backend name to instantiate and describe"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="MECHA_API_KEY"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
) -> None:
    """Show metadata for a configured inference backend."""
    kwargs: dict = {}
    if api_key is not None:
        kwargs["api_key"] = api_key
    if base_url is not None:
        kwargs["base_url"] = base_url
    if model is not None:
        kwargs["model"] = model
    strategy = build_inference(backend, **kwargs)
    console.print(json.dumps(strategy.describe(), indent=2))


if __name__ == "__main__":
    app()
