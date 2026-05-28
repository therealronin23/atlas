"""Atlas Core — CLI local."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape as _markup_escape
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
@click.version_option("0.9.0", prog_name="atlas")
def cli() -> None:
    """Atlas Core v0.6 — Sistema operativo personal de inteligencia."""


@cli.command()
def status() -> None:
    """Estado del core: permisos, herramientas, cola y Merkle chain."""
    orch = get_orchestrator()
    st = orch.status()

    console.print("\n[bold cyan]Atlas Core v0.6[/bold cyan]")
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


@cli.command("pending")
def pending() -> None:
    """Lista approvals pendientes persistidos por el Orchestrator."""
    orch = get_orchestrator()
    items = orch.pending_approvals()
    if not items:
        console.print("[green]Sin approvals pendientes.[/green]")
        return

    table = Table(title="Approvals pendientes", show_header=True)
    table.add_column("Task ID", style="cyan")
    table.add_column("Tool", style="magenta")
    table.add_column("Reason")
    table.add_column("Intent")
    for item in items:
        table.add_row(
            str(item.get("task_id", "")),
            str(item.get("tool") or ""),
            str(item.get("reason") or ""),
            str(item.get("intent") or ""),
        )
    console.print(table)


@cli.command("approve")
@click.argument("task_id", required=True)
@click.option("--deny", is_flag=True, help="Rechaza la tarea en vez de aprobarla.")
def approve(task_id: str, deny: bool) -> None:
    """Aprueba o rechaza una tarea pendiente."""
    orch = get_orchestrator()
    result = orch.approve_pending(task_id, approved=not deny)
    status = result.get("status", "unknown")
    color = "green" if status == "done" else "yellow" if status == "cancelled" else "red"
    console.print(f"Status: [{color}]{status}[/{color}]")
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


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


@cli.group("gate-h")
def gate_h() -> None:
    """Comandos de Gate H para resiliencia y reconstruccion."""
    pass


@gate_h.command("status")
def gate_h_status() -> None:
    """Muestra el estado de Gate H."""
    orch = get_orchestrator()
    status = orch.gate_h_status()
    console.print("\n[bold cyan]Gate H status[/bold cyan]\n")
    console.print_json(json.dumps(status, ensure_ascii=False, default=str))


@gate_h.command("rebuild-memory")
def gate_h_rebuild_memory() -> None:
    """Reconstruye la memoria derivada a partir del registro Merkle."""
    orch = get_orchestrator()
    result = orch.rebuild_memory()
    console.print("\n[bold cyan]Gate H rebuild memory[/bold cyan]\n")
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@gate_h.command("receipts")
@click.option("--tail", "-n", default=20, help="Ultimos N receipts")
def gate_h_receipts(tail: int) -> None:
    """Muestra reasoning receipts de herramientas generadas."""
    orch = get_orchestrator()
    items = orch.gate_h_receipts(tail)
    console.print("\n[bold cyan]Gate H receipts[/bold cyan]\n")
    console.print_json(json.dumps(items, ensure_ascii=False, default=str))


@gate_h.command("pause")
@click.argument("tool_name")
def gate_h_pause(tool_name: str) -> None:
    """Pausa manualmente una herramienta generada."""
    orch = get_orchestrator()
    orch._gate_h.pause_tool(tool_name)
    console.print(f"[yellow]Pausada:[/yellow] {tool_name}")


@gate_h.command("resume")
@click.argument("tool_name")
def gate_h_resume(tool_name: str) -> None:
    """Reanuda una herramienta pausada."""
    orch = get_orchestrator()
    orch._gate_h.resume_tool(tool_name)
    console.print(f"[green]Reanudada:[/green] {tool_name}")


@gate_h.group("diagnostic")
def gate_h_diagnostic() -> None:
    """Modo diagnostico Gate H (solo known-good tools)."""
    pass


@gate_h_diagnostic.command("on")
def gate_h_diagnostic_on() -> None:
    orch = get_orchestrator()
    orch._gate_h.set_diagnostic_mode(True)
    console.print("[yellow]Gate H diagnostic mode ON[/yellow]")


@gate_h_diagnostic.command("off")
def gate_h_diagnostic_off() -> None:
    orch = get_orchestrator()
    orch._gate_h.set_diagnostic_mode(False)
    console.print("[green]Gate H diagnostic mode OFF[/green]")


@gate_h.command("validate")
@click.argument("pattern_id")
def gate_h_validate(pattern_id: str) -> None:
    """Comprueba si un patron generado esta stale (H6) o vigente."""
    orch = get_orchestrator()
    pattern = orch._approved_patterns.get(pattern_id)
    if pattern is None:
        console.print(f"[red]Patron no encontrado:[/red] {pattern_id}")
        return
    stale = orch._gate_h._auditor.check_pattern_stale(pattern)
    if stale:
        orch._gate_h.record_stale_tool(pattern.name, pattern_id)
        console.print(f"[yellow]STALE[/yellow] — fingerprint de entorno cambio; revalidar antes de reutilizar.")
    else:
        console.print(f"[green]OK[/green] — patron {pattern_id} vigente.")
    console.print_json(json.dumps(pattern.to_dict(), ensure_ascii=False, default=str))


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


@cli.group()
def update() -> None:
    """ADR-025 ColdUpdateManager — parches aislados con validacion HITL."""


@update.command("propose")
@click.argument("intent", nargs=-1, required=True)
@click.option("--patch", "patch_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--base-ref", default="HEAD", show_default=True)
def update_propose(intent: tuple[str, ...], patch_path: Path, base_ref: str) -> None:
    """Registra un parche en worktree aislado."""
    orch = get_orchestrator()
    proposal = orch.cold_update().propose(" ".join(intent), patch_path, base_ref=base_ref)
    console.print(f"[green]Proposal {proposal.id}[/green] status={proposal.status}")


@update.command("validate")
@click.argument("proposal_id")
def update_validate(proposal_id: str) -> None:
    """Ejecuta pytest+mypy en el worktree."""
    orch = get_orchestrator()
    report = orch.cold_update().validate(proposal_id)
    color = "green" if report.passed else "red"
    console.print(f"[{color}]Validation passed={report.passed}[/{color}]")
    console.print_json(json.dumps(report.to_dict(), ensure_ascii=False))


@update.command("approve")
@click.argument("proposal_id")
def update_approve(proposal_id: str) -> None:
    """Aprueba un proposal validado (HITL)."""
    orch = get_orchestrator()
    p = orch.cold_update().approve(proposal_id)
    console.print(f"[yellow]Approved[/yellow] {p.id} — usar 'atlas update apply' para aplicar")


@update.command("apply")
@click.argument("proposal_id")
def update_apply(proposal_id: str) -> None:
    """Aplica parche al ATLAS_CORE_ROOT tras aprobacion."""
    orch = get_orchestrator()
    result = orch.cold_update().apply(proposal_id)
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@update.command("reject")
@click.argument("proposal_id")
@click.option("--reason", default="")
def update_reject(proposal_id: str, reason: str) -> None:
    orch = get_orchestrator()
    p = orch.cold_update().reject(proposal_id, reason=reason)
    console.print(f"[red]Rejected[/red] {p.id}")


@update.command("status")
@click.option("--id", "proposal_id", default=None, help="Detalle de un proposal")
def update_status(proposal_id: str | None) -> None:
    orch = get_orchestrator()
    mgr = orch.cold_update()
    if proposal_id:
        summary = mgr.review_summary(proposal_id)
        console.print_json(json.dumps(summary, ensure_ascii=False, default=str))
        return
    for p in mgr.list_proposals():
        console.print(f"  {p.id}  {p.status:10}  {p.intent[:60]}")


@cli.group("self-audit")
def self_audit() -> None:
    """Atlas 24h self-audit loop — cold, auditable, no hot self-patch."""


@self_audit.command("run")
@click.option("--hours", default=24.0, show_default=True, type=float)
@click.option(
    "--profile",
    default="full",
    show_default=True,
    type=click.Choice(["quick", "full", "resilience", "autonomy"]),
)
@click.option("--cycle-minutes", default=60.0, show_default=True, type=float)
@click.option("--max-cycles", default=None, type=int, help="Limite de ciclos para smoke/dry-run.")
@click.option("--dry-run", is_flag=True, help="No marca candidatos como listos para patch.")
def self_audit_run(
    hours: float,
    profile: str,
    cycle_minutes: float,
    max_cycles: int | None,
    dry_run: bool,
) -> None:
    """Ejecuta ciclos de auditoria autonoma acotados."""
    orch = get_orchestrator()
    report = orch.self_audit().run(
        hours=hours,
        profile=profile,
        cycle_interval_minutes=cycle_minutes,
        max_cycles=max_cycles,
        dry_run=dry_run,
    )
    console.print_json(json.dumps(report.to_dict(), ensure_ascii=False, default=str))


@self_audit.command("status")
def self_audit_status() -> None:
    """Estado del ultimo loop y flag de stop."""
    orch = get_orchestrator()
    console.print_json(json.dumps(orch.self_audit().status(), ensure_ascii=False, default=str))


@self_audit.command("proposals")
def self_audit_proposals() -> None:
    """Lista candidatos generados por el ultimo self-audit."""
    orch = get_orchestrator()
    console.print_json(json.dumps(orch.self_audit().proposals(), ensure_ascii=False, default=str))


@self_audit.command("report")
def self_audit_report() -> None:
    """Muestra el ultimo reporte persistido."""
    orch = get_orchestrator()
    report = orch.self_audit().latest_report()
    if report is None:
        console.print("[yellow]No hay reporte self-audit todavia.[/yellow]")
        return
    console.print_json(json.dumps(report, ensure_ascii=False, default=str))


@self_audit.command("stop")
def self_audit_stop() -> None:
    """Solicita parada cooperativa del loop."""
    orch = get_orchestrator()
    orch.self_audit().stop()
    console.print("[yellow]Self-audit stop requested[/yellow]")


@cli.command()
def health() -> None:
    """Estado de salud operativo (JSON). Gate I."""
    orch = get_orchestrator()
    console.print_json(json.dumps(orch.health_report(), ensure_ascii=False, default=str))


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
def doctor(as_json: bool) -> None:
    """Diagnóstico operativo unificado: governance, Merkle, workspace, twin Hermes."""
    from atlas.core.doctor import run_diagnostics  # noqa: PLC0415

    orch = get_orchestrator()
    report = run_diagnostics(orch)

    if as_json:
        console.print_json(json.dumps(report, ensure_ascii=False, default=str))
        return

    status = report["status"]
    color = "green" if status == "ok" else "yellow"
    console.print(f"\n[bold {color}]Atlas doctor — {status.upper()}[/bold {color}]\n")
    table = Table(show_header=True)
    table.add_column("Check", style="cyan", width=16)
    table.add_column("Estado", width=8)
    table.add_column("Detalle")
    for c in report["checks"]:
        if c["ok"]:
            badge = "[green]OK[/green]"
        elif c["advisory"]:
            badge = "[yellow]WARN[/yellow]"
        else:
            badge = "[red]FAIL[/red]"
        table.add_row(c["name"], badge, c["detail"])
    console.print(table)
    s = report["summary"]
    console.print(f"\n[dim]{s['passed']}/{s['total']} checks passed[/dim]")


@cli.command()
@click.option("--hours", "-H", default=None, type=float, help="Ventana en horas (default: todo el historial).")
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
def insights(hours: float | None, as_json: bool) -> None:
    """Analytics de uso derivados del Merkle ledger."""
    from atlas.core.insights import compute_insights  # noqa: PLC0415

    orch = get_orchestrator()
    records = orch.audit_tail(10_000)
    report = compute_insights(records, window_hours=hours)

    if as_json:
        console.print_json(json.dumps(report, ensure_ascii=False, default=str))
        return

    win = f"últimas {hours}h" if hours else "histórico completo"
    console.print(f"\n[bold cyan]Atlas insights[/bold cyan] — {win}\n")
    console.print(f"  Eventos totales: {report['total_events']}")
    rate = report["success_rate"]
    console.print(f"  Tasa de éxito:   {f'{rate:.1%}' if rate is not None else 'N/A'}")
    console.print(f"  Por resultado:   {report['by_result']}")
    console.print(f"  Por riesgo:      {report['by_risk']}")

    if report["top_actions"]:
        table = Table(title="Top acciones", show_header=True)
        table.add_column("Acción", style="cyan")
        table.add_column("Conteo", justify="right")
        for action, count in report["top_actions"]:
            table.add_row(action, str(count))
        console.print(table)


@cli.command()
@click.option(
    "--poll-interval",
    default=1.0,
    show_default=True,
    type=float,
    help="Intervalo del loop principal (s).",
)
def serve(poll_interval: float) -> None:
    """Proceso 24/7: Telegram + OfflineMonitor + alertas (+ dashboard opcional)."""
    from atlas.runtime.service_runner import AtlasServiceRunner  # noqa: PLC0415

    orch = get_orchestrator()
    runner = AtlasServiceRunner(orch)
    console.print("[bold cyan]Atlas serve[/bold cyan] — Ctrl+C para detener")
    console.print("[dim]ATLAS_SERVE_DASHBOARD=1 para dashboard; ATLAS_THERMAL_MONITOR=1 para termico[/dim]")
    runner.run_forever(poll_interval_s=poll_interval)


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address (solo localhost por seguridad).")
@click.option("--port", default=7331, show_default=True, type=int, help="Puerto del dashboard.")
def dashboard(host: str, port: int) -> None:
    """Arranca el dashboard web local en localhost:7331."""
    from atlas.interfaces.dashboard import serve  # noqa: PLC0415
    console.print(f"\n[bold cyan]Atlas Dashboard[/bold cyan] → http://{host}:{port}")
    console.print("[dim]Ctrl+C para detener. Auto-refresca cada 30s.[/dim]\n")
    serve(host=host, port=port)


@cli.command()
@click.option("--mode", default="auto", type=click.Choice(["auto", "real", "stub"]), show_default=True, help="Modo de voz.")
@click.option("--whisper-model", default="small", show_default=True, help="Tamaño modelo Whisper (tiny|base|small|medium).")
def voice(mode: str, whisper_model: str) -> None:
    """Loop interactivo de voz: STT (Whisper) + TTS (Piper). Deps: pip install 'atlas-core[voice]'"""
    from atlas.interfaces.voice import VoiceModule, VoiceConfig  # noqa: PLC0415
    cfg = VoiceConfig(whisper_model=whisper_model)
    try:
        vm = VoiceModule(config=cfg, mode=mode)
    except RuntimeError as e:
        console.print(f"[red]{_markup_escape(str(e))}[/red]")
        console.print("[dim]Instala las deps de voz: pip install 'atlas-core\\[voice]'[/dim]")
        return
    console.print(f"\n[bold cyan]Atlas Voz[/bold cyan] (modo={vm.mode}, whisper={whisper_model})")
    if not vm.is_real:
        console.print("[yellow]Modo stub: sin hardware real. Instala atlas-core\\[voice] para audio.[/yellow]")
    orch = get_orchestrator()
    vm.run_loop(orchestrator=orch)


if __name__ == "__main__":
    cli()
