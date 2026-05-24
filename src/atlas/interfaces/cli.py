"""Atlas Core — CLI local."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from atlas.core.contracts import TaskSource
from atlas.core.orchestrator import Orchestrator

console = Console()
_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch


@click.group()
@click.version_option("0.1.0", prog_name="atlas")
def cli() -> None:
    """Atlas Core v0.1 — Sistema operativo personal de inteligencia."""


@cli.command()
def status() -> None:
    """Estado del core: permisos, herramientas, cola y Merkle chain."""
    orch = get_orchestrator()
    st = orch.status()

    console.print("\n[bold cyan]Atlas Core v0.1[/bold cyan]")
    console.print(f"  Workspace:       {st.workspace}")
    console.print(f"  Version:         {st.version}")
    console.print(f"  Uptime:          {st.uptime_seconds}s")
    console.print(f"  Governance:      {'[green]OK[/green]' if st.governance_ok else '[red]EMERGENCY[/red]'}")
    console.print(f"  Merkle chain:    {'[green]OK[/green]' if st.chain_ok else '[red]CORRUPTA[/red]'}")
    console.print(f"  Hermes mode:     {st.hermes_mode}")
    console.print(f"  Queue depth:     {st.queue_depth}")
    console.print(f"  Tools:           {st.tool_count}")
    console.print(f"  Audit records:   {st.record_count}")
    if st.emergency_mode:
        console.print("\n[bold red]⚠  ATLAS EN MODO DE EMERGENCIA[/bold red]")


@cli.command()
@click.argument("intent", nargs=-1, required=True)
@click.option("--priority", "-p", default=3, type=click.IntRange(1, 5))
@click.option("--source", default="cli", type=click.Choice(["cli", "api", "internal"]))
def task(intent: tuple, priority: int, source: str) -> None:
    """Convierte una intencion en una tarea y la procesa."""
    intent_str = " ".join(intent)
    src = TaskSource(source)
    orch = get_orchestrator()

    console.print(f"\n[bold]Procesando:[/bold] {intent_str}")
    t = orch.handle_intent(intent_str, source=src)

    status_color = {
        "done": "green", "blocked": "red", "failed": "red",
        "delegated": "yellow", "awaiting_approval": "yellow",
    }.get(t.status.value, "white")

    console.print(f"  Status:   [{status_color}]{t.status.value.upper()}[/{status_color}]")
    console.print(f"  Route:    {t.route.value if t.route else 'N/A'}")
    console.print(f"  Tool:     {t.tool_name or 'N/A'}")
    console.print(f"  Task ID:  {t.id}")

    if t.result:
        console.print("\n[bold]Resultado:[/bold]")
        console.print_json(json.dumps(t.result, ensure_ascii=False, default=str))

    if t.error:
        console.print(f"\n[bold red]Error:[/bold red] {t.error}")


@cli.command()
@click.option("--level", "-l", type=click.Choice(["L-det", "L0", "L1", "L2"]))
def tools(level: str | None) -> None:
    """Lista las herramientas del Tool Registry."""
    orch = get_orchestrator()
    all_tools = orch.tools()

    if level:
        all_tools = [t for t in all_tools if t["level"] == level]

    table = Table(title="Tool Registry", show_header=True)
    table.add_column("Nombre", style="cyan", width=25)
    table.add_column("Nivel", width=8)
    table.add_column("Permiso", width=10)
    table.add_column("Descripcion")

    perm_color = {"auto": "green", "confirm": "yellow", "approve": "red", "blocked": "dim"}

    for t in all_tools:
        p = t["permission_level"]
        table.add_row(
            t["name"],
            t["level"],
            f"[{perm_color.get(p, 'white')}]{p}[/{perm_color.get(p, 'white')}]",
            t["description"],
        )
    console.print(table)


@cli.command()
@click.option("--layer", "-l", default="system_context",
              type=click.Choice(["system_context", "error_registry", "approved_patterns"]))
def memory(layer: str) -> None:
    """Lee una capa de memoria de Atlas."""
    orch = get_orchestrator()
    result = orch.memory_read(layer)
    console.print(f"\n[bold cyan]Memoria — {layer}[/bold cyan]\n")
    if isinstance(result, str):
        console.print(result if result else "[dim](vacia)[/dim]")
    else:
        console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@cli.command()
@click.option("--tail", "-n", default=20, help="Ultimas N entradas")
@click.option("--verify", is_flag=True, help="Verificar integridad de la cadena")
def audit(tail: int, verify: bool) -> None:
    """Muestra el Merkle audit log."""
    orch = get_orchestrator()

    if verify:
        from atlas.logging.merkle_logger import MerkleLogger
        from pathlib import Path
        ml = MerkleLogger(
            Path(orch.status().workspace) / "memory" / "audit"
        )
        ok, msg = ml.verify_chain()
        if ok:
            console.print("[bold green]✓ Cadena Merkle integra[/bold green]")
        else:
            console.print(f"[bold red]✗ Cadena Merkle CORRUPTA: {msg}[/bold red]")
        return

    records = orch.audit_tail(tail)
    if not records:
        console.print("[dim]Audit log vacio.[/dim]")
        return

    table = Table(title=f"Audit Log (ultimas {tail} entradas)")
    table.add_column("Timestamp", width=28)
    table.add_column("Action", width=22)
    table.add_column("Agent", width=18)
    table.add_column("Result", width=10)
    table.add_column("Risk", width=10)

    result_color = {"success": "green", "failure": "red", "blocked": "red", "pending": "yellow"}
    risk_color = {"safe": "green", "moderate": "yellow", "high": "red", "critical": "bold red"}

    for r in records:
        res = r.get("result", "")
        risk = r.get("risk_level", "")
        table.add_row(
            r.get("timestamp", "")[:26],
            r.get("action", ""),
            r.get("agent", ""),
            f"[{result_color.get(res, 'white')}]{res}[/{result_color.get(res, 'white')}]",
            f"[{risk_color.get(risk, 'white')}]{risk}[/{risk_color.get(risk, 'white')}]",
        )
    console.print(table)


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address (solo localhost por seguridad).")
@click.option("--port", default=7331, show_default=True, type=int, help="Puerto del dashboard.")
def dashboard(host: str, port: int) -> None:
    """Arranca el dashboard web local en localhost:7331."""
    from atlas.interfaces.dashboard import serve  # noqa: PLC0415
    console.print(f"\n[bold cyan]Atlas Dashboard[/bold cyan] → http://{host}:{port}")
    console.print("[dim]Ctrl+C para detener. Auto-refresca cada 30s.[/dim]\n")
    serve(host=host, port=port)


if __name__ == "__main__":
    cli()
