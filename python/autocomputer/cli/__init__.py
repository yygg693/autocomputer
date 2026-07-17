"""Command-line interface — powered by typer + rich."""

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="ac",
    help="autocomputer — AI-driven desktop GUI automation",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Show version info."""
    from autocomputer import __version__
    from autocomputer.core._bridge import _RUST_AVAILABLE

    console.print(f"[bold cyan]autocomputer[/] v[green]{__version__}[/]")
    console.print(
        f"Rust core: [green]available[/]"
        if _RUST_AVAILABLE
        else "Rust core: [yellow]not available (pure-Python fallback)[/]"
    )


@app.command()
def see(
    monitor: int = typer.Option(0, "--monitor", "-m", help="Monitor index (0 = primary)"),
    save: str = typer.Option(None, "--save", "-s", help="Save screenshot to file"),
) -> None:
    """Capture a screenshot and display info."""
    from autocomputer.core import capture_screen, list_monitors, MonitorInfo, CaptureResult

    monitors = list_monitors()
    if not monitors:
        console.print("[yellow]No monitors detected[/yellow]")
        return

    # Show monitor list
    table = Table(title="Connected Monitors", border_style="dim")
    table.add_column("#", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Resolution", style="green")
    table.add_column("Position", style="dim")
    table.add_column("Primary", style="yellow")

    for m in monitors:
        table.add_row(
            str(m.index),
            m.name,
            f"{m.width}x{m.height}",
            f"({m.x}, {m.y})",
            "★" if m.is_primary else "",
        )

    console.print(table)

    # Capture
    result: CaptureResult = capture_screen(monitor)
    console.print()
    console.print(f"[bold]Screenshot[/] — Monitor {monitor}: [green]{result.width}x{result.height}[/]")
    console.print(f"  PNG size: [cyan]{len(result.png):,} bytes[/]")
    console.print(f"  Raw RGBA: [cyan]{len(result.raw):,} bytes ({result.width * result.height * 4:,} expected)[/]")

    if save:
        from pathlib import Path

        out = Path(save)
        if out.suffix.lower() != ".png":
            out = out.with_suffix(".png")
        out.write_bytes(result.png)
        console.print(f"  [green]Saved to:[/] {out}")


@app.command()
def monitors() -> None:
    """List all connected monitors."""
    from autocomputer.core import list_monitors

    monitors = list_monitors()
    if not monitors:
        console.print("[yellow]No monitors detected[/yellow]")
        return

    for m in monitors:
        primary = " ★" if m.is_primary else ""
        console.print(
            f"  [{m.index}] [cyan]{m.name}[/] — "
            f"[green]{m.width}x{m.height}[/] @ ({m.x}, {m.y}) "
            f"scale: [yellow]{m.scale_factor:.0%}[/]{primary}"
        )


@app.command()
def serve(port: int = typer.Option(8765, "--port", "-p"), host: str = typer.Option("127.0.0.1", "--host")) -> None:
    """Start API + GUI server."""
    from autocomputer.server import run_server
    run_server(host=host, port=port)


@app.command()
def run(
    goal: str = typer.Argument(..., help="Natural language goal to execute"),
    model: str = typer.Option("openai/gpt-4o", "--model", "-m", help="LLM model for planning"),
) -> None:
    """Run a natural language automation goal."""
    from autocomputer.agent.core import Agent
    console.print(f"[bold cyan]Goal:[/] {goal}")
    console.print(f"[dim]Model: {model}[/]")
    agent = Agent(model=model)
    result = agent.run(goal)
    if result["success"]:
        console.print(f"[green]✓ Done[/] in {result['elapsed_ms']:.0f}ms, {len(result['steps'])} steps")
    else:
        console.print(f"[red]✗ Failed[/] after {result.get('retries_used', 0)} retries")
        for r in result["steps"]:
            if not r.get("success"):
                console.print(f"  [red]•[/] {r.get('action', '?')}: {r.get('error', 'unknown error')}")


@app.command()
def record(output: str = typer.Option("flow.json", "--output", "-o")):
    """Record a new automation flow."""
    from autocomputer.record.engine import FlowRecorder
    recorder = FlowRecorder(name="CLI Record")
    console.print("[bold cyan]Recording...[/] (call .stop() and .save() in code)")
    console.print(f"  Output: {output}")
    # In future: hook into global keyboard listener
    console.print("  [dim]Note: interactive recording requires Python API[/]")


@app.command()
def replay(
    flow_file: str = typer.Argument(..., help="Flow JSON file to replay"),
    speed: float = typer.Option(1.0, "--speed", "-s"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Replay a recorded flow."""
    import json
    from autocomputer.record.engine import FlowRecorder, FlowReplayer

    console.print(f"[bold cyan]Loading:[/] {flow_file}")
    with open(flow_file) as f:
        data = json.load(f)

    recorder = FlowRecorder.from_dict(data)
    replayer = FlowReplayer(recorder)
    results = replayer.replay(speed=speed, dry_run=dry_run)

    ok = sum(1 for r in results if r.get("success"))
    console.print(f"[green]✓ {ok}/{len(results)} steps[/]")


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Natural language goal"),
    model: str = typer.Option("openai/gpt-4o", "--model", "-m"),
):
    """Generate an action plan without executing."""
    from autocomputer.agent.core import Agent, ScreenContext
    ctx = ScreenContext.capture(with_ocr=True)
    agent = Agent(model=model)
    plan = agent.plan(goal, context=ctx)

    console.print(f"[bold cyan]Plan for:[/] {goal}")
    console.print(f"[dim]Context: {ctx.to_prompt()}[/]")
    for i, step in enumerate(plan.steps):
        console.print(f"  {i+1}. [yellow]{step.action}[/] — {step.reasoning or '(no reasoning)'}")


@app.command()
def plugins_list():
    """List installed plugins."""
    from autocomputer.plugins import PluginRegistry
    actions = PluginRegistry.list_actions()
    if actions:
        console.print(f"[green]{len(actions)} action(s)[/]: {', '.join(actions)}")
    else:
        console.print("[dim]No plugins installed[/]")
    console.print("[dim]Add plugins via entry_points group 'autocomputer.plugins'[/]")


def main() -> None:
    app()
