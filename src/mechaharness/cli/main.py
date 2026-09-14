"""Command-line interface."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from mechaharness import __version__
from mechaharness.config import Settings, get_settings
from mechaharness.core.contract import RunRequest
from mechaharness.di import list_harness_families, list_inference_backends
from mechaharness.factory import describe
from mechaharness.factory import run as run_harness

app = typer.Typer(
    name="mechaharness",
    help="Agentic harness CLI — swap inference backends and harness families.",
    no_args_is_help=True,
)
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
    """Run a single prompt through the configured harness."""
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
    """Show metadata for a configured inference backend."""
    import json

    env = get_settings()
    settings = Settings(
        inference_backend=backend,
        api_key=api_key if api_key is not None else env.api_key,
        base_url=base_url if base_url is not None else env.base_url,
        model=model or env.model,
    )
    meta = asyncio.run(describe(settings))
    console.print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    app()
