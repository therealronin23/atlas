"""Atlas Core — CLI local."""

from __future__ import annotations

import json
import sys
import contextlib
import importlib.util
import io
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape as _markup_escape
from rich.table import Table
from rich import print as rprint

from typing import TYPE_CHECKING, Any

from atlas.core.contracts import TaskSource
from atlas.core.orchestrator import Orchestrator
from atlas import __version__

if TYPE_CHECKING:
    from atlas.memory.block_memory import BlockMemory
    from atlas.security.writer_lock import MerkleWriterLock

console = Console()
_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch


def _acquire_writer_lock_or_die(orch: Orchestrator) -> "MerkleWriterLock":
    """Single-writer guard (ROADMAP §7): los entrypoints de larga vida que
    escriben la cadena Merkle (serve, self-audit run) se niegan a arrancar si
    ya hay otro escritor sobre el mismo workspace."""
    from atlas.security.writer_lock import MerkleWriterLock, WriterLockHeld  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    lock = MerkleWriterLock(Path(orch.status().workspace))
    try:
        lock.acquire()
    except WriterLockHeld as exc:
        console.print(f"[bold red]✗ {exc}[/bold red]")
        raise SystemExit(1) from None
    return lock


@click.group()
@click.version_option(__version__, prog_name="atlas")
def cli() -> None:
    """Atlas Core — Sistema operativo personal de inteligencia."""


@cli.command()
def status() -> None:
    """Estado del core: permisos, herramientas, cola y Merkle chain."""
    orch = get_orchestrator()
    st = orch.status()

    console.print(f"\n[bold cyan]Atlas Core v{__version__}[/bold cyan]")
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
def task(intent: tuple[str, ...], priority: int, source: str) -> None:
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
    table.add_column("Mutaciones")
    table.add_column("Reason")
    table.add_column("Intent")
    for item in items:
        # ADR-033: muestra el lote de mutaciones (id:nombre) si es un loop
        # agéntico suspendido, para poder usar `approve --only <ids>`.
        muts = item.get("pending_mutations") or []
        muts_str = ", ".join(
            f"{m.get('id')}:{m.get('name')}" for m in muts
        ) if muts else "-"
        table.add_row(
            str(item.get("task_id", "")),
            str(item.get("tool") or ""),
            muts_str,
            str(item.get("reason") or ""),
            str(item.get("intent") or ""),
        )
    console.print(table)


@cli.command("approve")
@click.argument("task_id", required=True)
@click.option("--deny", is_flag=True, help="Rechaza la tarea en vez de aprobarla.")
@click.option("--abort", is_flag=True,
              help="Con --deny: cancela el loop del todo (CANCELLED) en vez de re-planificar.")
@click.option("--only", "only", default="",
              help="Aprobación parcial: ids de tool_call separados por coma a ejecutar; "
                   "el resto del lote se deniega. Implica aprobación.")
def approve(task_id: str, deny: bool, abort: bool, only: str) -> None:
    """Aprueba o rechaza una tarea pendiente.

    Loops agénticos (ADR-032/033): --only id1,id2 ejecuta solo esas mutaciones
    del lote; --deny --abort cancela el loop suspendido por completo.
    """
    orch = get_orchestrator()
    approve_only = [s.strip() for s in only.split(",") if s.strip()] or None
    approved = not deny
    if approve_only is not None:
        approved = True  # aprobación parcial implica aprobar
    result = orch.approve_pending(
        task_id, approved=approved, abort=abort, approve_only=approve_only,
    )
    status = result.get("status", "unknown")
    color = "green" if status == "done" else "yellow" if status == "cancelled" else "red"
    console.print(f"Status: [{color}]{status}[/{color}]")
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@cli.command("sweep")
@click.option("--ttl", type=float, default=None,
              help="Segundos de antigüedad para cancelar loops suspendidos. "
                   "Sin valor usa ATLAS_AGENTIC_SUSPENSION_TTL.")
def sweep(ttl: float | None) -> None:
    """Cancela loops agénticos suspendidos y abandonados (ADR-033)."""
    orch = get_orchestrator()
    cancelled = orch.sweep_expired_suspensions(ttl_seconds=ttl)
    if not cancelled:
        console.print("[green]Nada que barrer.[/green]")
        return
    console.print(f"[yellow]Cancelados {len(cancelled)} loop(s) suspendido(s):[/yellow]")
    for tid in cancelled:
        console.print(f"  {tid}")


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
    proposals = mgr.list_proposals()
    if not proposals:
        console.print("[green]Sin propuestas.[/green]")
        return
    for p in proposals:
        console.print(f"  {p.id}  {p.status:10}  {p.intent[:60]}")
    # Receta HITL explícita (2026-07-10): el operador señaló que "no hay un
    # mecanismo fácil y claro" — lo había, pero nada lo enseñaba en el momento
    # de decidir. Cada estado imprime su siguiente paso copy-pasteable.
    next_step = {
        "proposed": "atlas update validate {id}   # pytest+mypy en worktree aislado",
        "validated": "atlas update approve {id}    # y después: atlas update apply {id}",
        "approved": "atlas update apply {id}",
    }
    actionable = [p for p in proposals if p.status in next_step]
    if actionable:
        console.print("\n[bold]Siguiente paso por propuesta:[/bold]")
        for p in actionable:
            console.print(f"  {next_step[p.status].format(id=p.id)}")
        console.print("  (rechazar: atlas update reject <id> --reason '...')")


@update.command("batch-review")
@click.option("--id", "batch_id", default=None, help="Ver un lote concreto (default: el último)")
def update_batch_review(batch_id: str | None) -> None:
    """Muestra el último lote de autoauditoría probado, listo para revisión episódica."""
    orch = get_orchestrator()
    batcher = orch.maintenance_cold_update_batcher()
    result = batcher.get_batch(batch_id) if batch_id else batcher.latest_batch()
    if result is None:
        console.print("[yellow]No hay ningún lote todavía.[/yellow]")
        return
    color = "green" if result.passed else "red"
    console.print(f"[{color}]Lote {result.id}[/{color}] passed={result.passed}")
    console.print(f"Incluidos: {len(result.included)}")
    for pid in result.included:
        console.print(f"  + {pid}")
    console.print(f"Excluidos: {len(result.excluded)}")
    for exc in result.excluded:
        console.print(f"  - {exc.get('proposal_id')}: {exc.get('reason')}")
    console.print("\n[bold]Resumen tests:[/bold]")
    console.print(result.pytest_summary[-1000:] if result.pytest_summary else "(sin salida)")


@update.command("batch-approve")
@click.argument("batch_id")
def update_batch_approve(batch_id: str) -> None:
    """Aprueba+aplica TODO un lote de una vez (única decisión humana del flujo batch).

    Sigue pasando por el seam del decisor existente (NO bypass de HITL): por cada
    proposal incluida en el lote, llama a orch.advance_cold_update(proposal_id) en
    el orden en que aparecen. Si alguna falla a mitad, reporta cuáles se aplicaron
    y cuáles no, y PARA (no sigue aplicando tras un fallo, para no dejar un estado
    parcialmente inconsistente sin que el humano lo sepa).
    """
    orch = get_orchestrator()
    batcher = orch.maintenance_cold_update_batcher()
    result = batcher.get_batch(batch_id)
    if result is None:
        console.print(f"[red]Lote {batch_id} no existe.[/red]")
        raise SystemExit(1)
    if not result.passed:
        console.print(f"[red]Lote {batch_id} no pasó validación — no se puede aprobar.[/red]")
        raise SystemExit(1)
    applied: list[str] = []
    for pid in result.included:
        outcome = orch.advance_cold_update(pid)
        if outcome.startswith("error") or outcome.startswith("denegado") or outcome.startswith("validation_failed"):
            console.print(f"[red]Fallo aplicando {pid}: {outcome}[/red]")
            console.print(f"Aplicados antes del fallo: {applied}")
            raise SystemExit(1)
        applied.append(pid)
    console.print(f"[green]Lote {batch_id} aplicado completo[/green] — {len(applied)} cambios.")


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
    with _acquire_writer_lock_or_die(orch):
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
@click.option("--run-checks", is_flag=True, help="Ejecuta pytest core + mypy para evidencia viva.")
@click.option("--include-browser", is_flag=True, help="Con --run-checks, incluye tests computer_use.")
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
@click.option("--strict", is_flag=True, help="Exit 1 si hay fallos de readiness estricta.")
def reality(run_checks: bool, include_browser: bool, as_json: bool, strict: bool) -> None:
    """Fuente factual: estado verificable, unknown/degraded si no hay evidencia."""
    from atlas.core.reality import collect_reality  # noqa: PLC0415

    report = collect_reality(
        run_checks=run_checks,
        include_browser=include_browser,
    )
    if as_json:
        console.print_json(json.dumps(report, ensure_ascii=False, default=str))
        if strict and report.get("strict_failures"):
            raise click.exceptions.Exit(1)
        return

    color = "green" if report["status"] == "ok" else "yellow"
    console.print(f"\n[bold {color}]Atlas reality — {report['status'].upper()}[/bold {color}]\n")
    console.print(f"  Version:       {report['repo']['version']}")
    console.print(f"  Commit:        {report['repo']['commit']} ({report['repo']['branch']})")
    console.print(f"  Dirty:         {report['repo']['dirty']} ({report['repo']['dirty_count']})")
    console.print(f"  Source files:  {report['runtime']['source_file_count']}")
    console.print(f"  Test files:    {report['runtime']['test_file_count']}")
    console.print(f"  Merkle:        {report['workspace']['merkle']['status']}")
    console.print(f"  Browser:       {report['browser']['status']} — {report['browser']['reason']}")
    console.print(f"  Hermes:        {report['hermes']['mode']} — {report['hermes']['reason']}")
    console.print(f"  LLM:           {report['llm']['status']} — {report['llm']['reason']}")
    console.print(f"  Decider:       {report['autonomy']['decider']}")
    console.print(f"  Docs:          {report['docs']['status']} — {report['docs']['reason']}")
    if report["checks"]:
        table = Table(title="Live checks", show_header=True)
        table.add_column("Check", style="cyan")
        table.add_column("Exit", justify="right")
        table.add_column("Summary")
        for name, check in report["checks"].items():
            table.add_row(name, str(check["exit_code"]), check["summary"])
        console.print(table)
    if report.get("strict_failures"):
        console.print(f"[yellow]Strict failures:[/yellow] {', '.join(report['strict_failures'])}")
    if strict and report.get("strict_failures"):
        raise click.exceptions.Exit(1)


def _load_completeness_demo_module() -> Any:
    demo_path = Path(__file__).resolve().parents[3] / "docs" / "demo" / "completeness_demo.py"
    spec = importlib.util.spec_from_file_location("atlas_completeness_demo", demo_path)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"No se pudo cargar demo: {demo_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@cli.command("completeness-demo")
@click.option("--json", "as_json", is_flag=True, help="Salida JSON estable para demos/scripts.")
def completeness_demo(as_json: bool) -> None:
    """Ejecuta la demo reproducible de subject-enforced completeness."""
    demo = _load_completeness_demo_module()

    def run_scenarios() -> dict[str, bool]:
        return {
            "honest": demo.run_session("honest", demo.OperatorBehaviour()) == [],
            "input_omission_detected": demo.run_session(
                "input_omission",
                demo.OperatorBehaviour(omit_seqs={2}),
            ) == [2],
            "faked_ack_rejected": demo.run_session(
                "faked_ack",
                demo.OperatorBehaviour(fake_ack_seqs={2}),
            ) == [2],
            "rewrite_detected": 3 in demo.run_session(
                "rewrite",
                demo.OperatorBehaviour(rewrite_at_seq=3),
            ),
            "forgery_rejected": demo.run_forgery_scenario(),
            "network_attribution": demo.run_network_attribution_scenario(),
            "output_omission_detected": demo.run_output_inspection_scenario(),
            "shadow_routing_transparent": demo.run_shadow_routing_scenario(),
            "behavioral_drift_flagged": demo.run_behavioral_drift_scenario(),
        }

    if as_json:
        with contextlib.redirect_stdout(io.StringIO()):
            scenarios = run_scenarios()
    else:
        scenarios = run_scenarios()
    report = {
        "status": "ok" if all(scenarios.values()) else "failed",
        "scenarios": scenarios,
    }
    if as_json:
        console.print_json(json.dumps(report, ensure_ascii=False, default=str))
    else:
        table = Table(title="Subject-Enforced Completeness Demo", show_header=True)
        table.add_column("Scenario", style="cyan")
        table.add_column("Result")
        for name, ok in scenarios.items():
            table.add_row(name, "PASS" if ok else "FAIL")
        console.print(table)
        console.print(f"Status: [{'green' if report['status'] == 'ok' else 'red'}]{report['status']}[/]")
    if report["status"] != "ok":
        raise click.exceptions.Exit(1)


@cli.command("capabilities")
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
def capabilities(as_json: bool) -> None:
    """Plano de capacidades: readiness, confianza, mutación, reversibilidad."""
    from atlas.core.reality import collect_reality  # noqa: PLC0415

    caps = collect_reality()["capabilities"]
    if as_json:
        console.print_json(json.dumps(caps, ensure_ascii=False, default=str))
        return

    table = Table(title="Atlas capabilities", show_header=True)
    table.add_column("Capability", style="cyan")
    table.add_column("Status")
    table.add_column("Trusted")
    table.add_column("Mutating")
    table.add_column("Reversible")
    table.add_column("Evidence")
    for cap in caps:
        table.add_row(
            str(cap["name"]),
            str(cap["status"]),
            str(cap["trusted"]),
            str(cap["mutating"]),
            str(cap["reversible"]),
            str(cap["evidence"]),
        )
    console.print(table)


@cli.command("security-audit")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
def security_audit(path: Path, as_json: bool) -> None:
    """Auditoría estática defensiva Python (CWE-tagged, read-only)."""
    from atlas.security.static_audit import audit_path  # noqa: PLC0415

    findings = audit_path(path)
    payload = [f.to_dict() for f in findings]
    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
        return
    if not findings:
        console.print("[green]Sin hallazgos estáticos.[/green]")
        return
    table = Table(title=f"Security audit: {path}", show_header=True)
    table.add_column("Severity")
    table.add_column("CWE")
    table.add_column("Rule")
    table.add_column("Location")
    table.add_column("Message")
    for finding in findings:
        table.add_row(
            finding.severity,
            finding.cwe,
            finding.rule,
            f"{finding.path}:{finding.line}",
            finding.message,
        )
    console.print(table)


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
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", "-n", default=20, show_default=True, type=int, help="Máximo de resultados.")
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
def search(query: tuple[str, ...], limit: int, as_json: bool) -> None:
    """Búsqueda full-text sobre el Merkle ledger (FTS5). Términos = AND implícito."""
    from atlas.core.audit_search import search_records  # noqa: PLC0415

    orch = get_orchestrator()
    records = orch.audit_tail(50_000)
    q = " ".join(query)
    results = search_records(records, q, limit=limit)

    if as_json:
        console.print_json(json.dumps(results, ensure_ascii=False, default=str))
        return

    if not results:
        console.print(f"[dim]Sin resultados para '{q}'.[/dim]")
        return

    table = Table(title=f"Búsqueda: '{q}' ({len(results)})", show_header=True)
    table.add_column("Timestamp", width=26)
    table.add_column("Action", style="cyan")
    table.add_column("Agent")
    table.add_column("Result")
    for r in results:
        table.add_row(
            r.get("timestamp", "")[:26],
            r.get("action", ""),
            r.get("agent", ""),
            r.get("result", ""),
        )
    console.print(table)


@cli.group()
def blocks() -> None:
    """ADR-030 block memory — bloques etiquetados siempre-en-contexto (Letta/MemGPT)."""


def _block_memory() -> "BlockMemory":  # noqa: F821
    return get_orchestrator().block_memory


@blocks.command("list")
@click.option("--json", "as_json", is_flag=True, help="Salida JSON cruda.")
def blocks_list(as_json: bool) -> None:
    """Lista los bloques con su ocupación."""
    mem = _block_memory()
    items = mem.all()
    if as_json:
        console.print_json(json.dumps([b.to_dict() for b in items], ensure_ascii=False))
        return
    if not items:
        console.print("[dim]Sin bloques.[/dim]")
        return
    table = Table(title="Block memory")
    table.add_column("Label", style="cyan")
    table.add_column("Chars", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Description")
    for b in items:
        color = "red" if b.is_full else "white"
        table.add_row(b.label, f"[{color}]{b.chars}[/{color}]", str(b.limit), b.description)
    console.print(table)


@blocks.command("show")
@click.argument("label")
def blocks_show(label: str) -> None:
    """Muestra el contenido de un bloque."""
    block = _block_memory().get(label)
    if block is None:
        console.print(f"[red]Bloque '{label}' no existe.[/red]")
        return
    console.print(f"[bold cyan]<{block.label}>[/bold cyan] ({block.chars}/{block.limit})")
    console.print(block.value or "[dim](vacío)[/dim]")


@blocks.command("create")
@click.argument("label")
@click.argument("value", nargs=-1)
@click.option("--limit", default=2000, show_default=True, type=int)
@click.option("--description", default="", help="Para qué sirve el bloque.")
def blocks_create(label: str, value: tuple[str, ...], limit: int, description: str) -> None:
    """Crea un bloque nuevo."""
    from atlas.memory.block_memory import BlockMemoryError  # noqa: PLC0415

    try:
        b = _block_memory().create(label, " ".join(value), limit=limit, description=description)
    except BlockMemoryError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(f"[green]Bloque '{b.label}' creado[/green] ({b.chars}/{b.limit})")


@blocks.command("set")
@click.argument("label")
@click.argument("value", nargs=-1, required=True)
def blocks_set(label: str, value: tuple[str, ...]) -> None:
    """Reemplaza el contenido completo de un bloque."""
    from atlas.memory.block_memory import BlockMemoryError  # noqa: PLC0415

    try:
        b = _block_memory().set(label, " ".join(value))
    except BlockMemoryError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(f"[green]'{b.label}' actualizado[/green] ({b.chars}/{b.limit})")


@blocks.command("append")
@click.argument("label")
@click.argument("text", nargs=-1, required=True)
def blocks_append(label: str, text: tuple[str, ...]) -> None:
    """Añade texto al final de un bloque."""
    from atlas.memory.block_memory import BlockMemoryError  # noqa: PLC0415

    try:
        b = _block_memory().append(label, " ".join(text))
    except BlockMemoryError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(f"[green]'{b.label}' ampliado[/green] ({b.chars}/{b.limit})")


@blocks.command("delete")
@click.argument("label")
def blocks_delete(label: str) -> None:
    """Elimina un bloque."""
    from atlas.memory.block_memory import BlockMemoryError  # noqa: PLC0415

    try:
        _block_memory().delete(label)
    except BlockMemoryError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(f"[yellow]'{label}' eliminado[/yellow]")


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
    with _acquire_writer_lock_or_die(orch):
        orch.log_session_start()
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


@cli.command("os-bridge")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address (solo localhost por seguridad).")
@click.option("--port", default=7341, show_default=True, type=int, help="Puerto del bridge Atlas OS.")
def os_bridge(host: str, port: int) -> None:
    """Arranca el Atlas OS Bridge (ADR-058): API + WS de eventos en localhost:7341."""
    from atlas.api.server import serve  # noqa: PLC0415
    console.print(f"\n[bold cyan]Atlas OS Bridge[/bold cyan] → http://{host}:{port}")
    console.print("[dim]Ctrl+C para detener. WS de eventos en /events.[/dim]\n")
    serve(host=host, port=port)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@cli.group("connections")
def connections_group() -> None:
    """Integration Fabric / Easy Connection Layer (Fase 15) — solo lectura y mock/sandbox."""


@connections_group.command("catalog")
def connections_catalog() -> None:
    """Catálogo de recetas de conexión agrupado por categoría humana."""
    from atlas.fabric.recipes import RecipeEngine  # noqa: PLC0415

    recipes = RecipeEngine(_repo_root() / "fixtures" / "connection_recipes")
    for category, items in sorted(recipes.catalog().items()):
        console.print(f"\n[bold cyan]{category}[/bold cyan]")
        for item in items:
            console.print(f"  {item['connector_id']:<28} {item['human_name']} "
                          f"[dim]({item['difficulty']}, {item['recommended_route']})[/dim]")
    if recipes.rejected:
        console.print("\n[bold red]Rechazadas[/bold red]")
        for connector_id, problems in recipes.rejected.items():
            console.print(f"  {connector_id}: {problems}")


@connections_group.command("plan")
@click.argument("connector_id")
def connections_plan(connector_id: str) -> None:
    """Plan de conexión humano (ruta, permisos, gates) para un conector."""
    from atlas.fabric.concierge import ConnectionConcierge  # noqa: PLC0415
    from atlas.fabric.policy import default_policy_engine  # noqa: PLC0415
    from atlas.fabric.recipes import RecipeEngine  # noqa: PLC0415

    root = _repo_root()
    recipes = RecipeEngine(root / "fixtures" / "connection_recipes")
    concierge = ConnectionConcierge(recipes, default_policy_engine(root))
    plan = concierge.plan(connector_id)
    if plan is None:
        console.print(f"[red]receta desconocida: {connector_id}[/red]")
        raise SystemExit(1)
    rprint(plan)


@connections_group.command("test")
@click.argument("connector_id")
@click.option("--mode", default="mock", type=click.Choice(["mock", "sandbox", "real"]), show_default=True)
def connections_test(connector_id: str, mode: str) -> None:
    """Prueba una conexión en modo mock/sandbox (real está bloqueado en Fase 15)."""
    from atlas.fabric.health import HealthMonitor  # noqa: PLC0415
    from atlas.fabric.recipes import RecipeEngine  # noqa: PLC0415
    from atlas.fabric.testing import ConnectionTestRunner  # noqa: PLC0415

    root = _repo_root()
    recipes = RecipeEngine(root / "fixtures" / "connection_recipes")
    runner = ConnectionTestRunner(recipes, HealthMonitor())
    rprint(runner.test(connector_id, mode=mode))


@cli.group("business")
def business_group() -> None:
    """Adaptive Question Engine / Business Core (Fase 15) — todo draft-first."""


@business_group.command("question-packs")
def business_question_packs() -> None:
    """Lista los packs de preguntas de onboarding disponibles por sector."""
    from atlas.business.questions import load_all_packs  # noqa: PLC0415

    packs = load_all_packs(_repo_root() / "fixtures" / "question_packs")
    for pack in packs.values():
        console.print(f"[bold cyan]{pack.pack_id}[/bold cyan] ({pack.sector_id}) "
                      f"— {len(pack.questions)} preguntas")


@business_group.command("onboarding-start")
@click.argument("pack_id")
def business_onboarding_start(pack_id: str) -> None:
    """Arranca una sesión de onboarding para el pack indicado."""
    from atlas.business.questions import QuestionEngine, load_all_packs  # noqa: PLC0415

    packs = load_all_packs(_repo_root() / "fixtures" / "question_packs")
    pack = packs.get(pack_id)
    if pack is None:
        console.print(f"[red]pack desconocido: {pack_id}[/red]")
        raise SystemExit(1)
    session = QuestionEngine().start_session(pack, demo=True)
    rprint(session.model_dump(mode="json"))


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


@cli.command()
@click.argument("task")
@click.option("--file", "-f", "context_files", multiple=True, help="Archivos de contexto (relativos al repo).")
@click.option("--test", "-t", "test_cmd", default="pytest -x -q", show_default=True, help="Comando de tests.")
@click.option("--level", type=click.Choice(["L0", "L1", "L2"]), default="L1", show_default=True, help="Nivel de modelo.")
@click.option("--parallel/--no-parallel", default=False, help="Lanzar subtareas en paralelo con todos los workers disponibles.")
@click.option("--iterations", default=3, show_default=True, help="Máximo de iteraciones por worker.")
@click.option(
    "--engine", type=click.Choice(["atlas", "tool"]), default="atlas", show_default=True,
    help="Motor de codificación: atlas=completación de texto, "
         "tool=tool-calling ADR-031 (4/4 en enjambre fácil y difícil medido 2026-07-02 "
         "vs 0/4 de atlas; apply-model es moot en tool-calling).",
)
@click.option(
    "--repo-map/--no-repo-map", "use_repo_map", default=True, show_default=True,
    help="Incluir repo-map (firmas de los .py más relevantes, budget 4KB) en el "
         "prompt — patrón Aider; estaba cableado a nivel de librería pero el CLI "
         "nunca lo pasaba (dormido hasta 2026-07-08).",
)
def code(
    task: str, context_files: tuple[str, ...], test_cmd: str, level: str,
    parallel: bool, iterations: int, engine: str, use_repo_map: bool,
) -> None:
    """Codifica una tarea usando InferenceHub (Groq/NIM/Gemini).

    Ejemplos:\n
      atlas code "añade tests para SqliteMemoryIndex.recall_all"\n
      atlas code "refactor auth module" -f src/auth.py -t "pytest tests/test_auth.py"\n
      atlas code "implementa ADR-X, ADR-Y" --parallel --level L2\n
      atlas code "crea src/greet.py" --engine tool
    """
    from atlas.core.inference_hub import InferenceHub, InferenceLevel  # noqa: PLC0415
    from atlas.core.atlas_coder import AtlasCoder, CodingStrategy  # noqa: PLC0415
    from atlas.core.tool_coder import ToolCoder  # noqa: PLC0415
    from atlas.core.parallel_coder import ParallelCoder, discover_workers  # noqa: PLC0415

    inference_level = InferenceLevel[level]
    cmd_parts = test_cmd.split()
    files = list(context_files)
    repo_root = Path.cwd()

    # Repo-map (patrón Aider): ficheros .py trackeados como candidatos; el
    # builder recorta por relevancia respecto a los context_files y respeta
    # su budget de 4KB, así que pasarlos todos es seguro.
    repo_map_files: list[str] = []
    if use_repo_map:
        import subprocess  # noqa: PLC0415

        ls = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=repo_root, capture_output=True, text=True, check=False,
        )
        if ls.returncode == 0:
            repo_map_files = ls.stdout.splitlines()

    console.print(f"\n[bold cyan]Atlas Code[/bold cyan] — motor=[yellow]{engine}[/yellow] nivel=[yellow]{level}[/yellow] paralelo=[yellow]{parallel}[/yellow]")
    console.print(f"[dim]Tarea:[/dim] {task}")
    if files:
        console.print(f"[dim]Archivos:[/dim] {', '.join(files)}")
    console.print(f"[dim]Tests:[/dim] {test_cmd}\n")

    if parallel:
        workers = discover_workers(level=inference_level)
        if not workers:
            console.print(f"[yellow]⚠ Sin workers disponibles para {level}. Configura las API keys.[/yellow]")
            console.print("[dim]Ejemplo: export NVIDIA_API_KEY=nvapi-... GROQ_API_KEY=gsk_...[/dim]")
            raise SystemExit(1)
        console.print(f"[green]✓ {len(workers)} workers disponibles[/green]")
        subtasks = [t.strip() for t in task.split(";;") if t.strip()] or [task]
        console.print(f"[dim]Subtareas detectadas: {len(subtasks)}[/dim]\n")

        coder_factory = (
            (lambda hub, root, timeout: ToolCoder(hub, repo_root=root, timeout_s=timeout))
            if engine == "tool" else None
        )
        pc = ParallelCoder(repo_root=repo_root, coder_factory=coder_factory)
        with console.status("[bold green]Ejecutando workers en paralelo…[/bold green]"):
            result = pc.run(subtasks, files, cmd_parts, level=inference_level, max_iterations=iterations)

        table = Table(title="Resultados paralelos")
        table.add_column("Subtarea", style="cyan", max_width=50)
        table.add_column("Provider")
        table.add_column("Estado")
        table.add_column("Iteraciones")
        for wr in result.results:
            estado = "[green]PASS[/green]" if wr.coder_result.success else "[red]FAIL[/red]"
            table.add_row(wr.subtask[:48], wr.provider_name, estado, str(wr.coder_result.iterations))
        console.print(table)
        console.print(f"\n[bold]{'✓ Todo correcto' if result.success else '✗ Hay fallos'}[/bold] — {result.subtasks_passed}/{result.subtasks_total} subtareas pasaron")
        raise SystemExit(0 if result.success else 1)

    else:
        hub = InferenceHub(mode="auto")
        if engine == "tool":
            tool_coder = ToolCoder(hub, repo_root=repo_root, timeout_s=120)
            with console.status("[bold green]Generando código…[/bold green]"):
                result_c = tool_coder.code(
                    task, files, cmd_parts, max_iterations=iterations,
                    level=inference_level, repo_map_files=repo_map_files or None,
                )
        else:
            atlas_coder = AtlasCoder(hub, repo_root=repo_root, timeout_s=120)
            with console.status("[bold green]Generando código…[/bold green]"):
                result_c = atlas_coder.code(
                    task, files, cmd_parts, max_iterations=iterations,
                    repo_map_files=repo_map_files or None,
                )

        if result_c.success:
            console.print(f"[bold green]✓ Listo[/bold green] en {result_c.iterations} iteración{'es' if result_c.iterations > 1 else ''}")
            if result_c.files_changed:
                console.print(f"[dim]Archivos modificados:[/dim] {', '.join(result_c.files_changed)}")
        else:
            console.print(f"[bold red]✗ No convergió[/bold red] tras {result_c.iterations} iteraciones")
            if result_c.error:
                console.print(f"[red]{_markup_escape(result_c.error)}[/red]")
            if result_c.test_output:
                console.print("\n[dim]Output de tests:[/dim]")
                console.print(result_c.test_output[:800])
        raise SystemExit(0 if result_c.success else 1)


@cli.command()
@click.argument("task")
@click.option("--file", "-f", "context_files", multiple=True, help="Archivos de contexto.")
@click.option("--test", "-t", "test_cmd", default="pytest -x -q", show_default=True)
@click.option("--level", type=click.Choice(["L1", "L2"]), default="L2", show_default=True)
@click.option("--cycles", default=2, show_default=True, help="Máximo de ciclos Cónclave→build→audit.")
@click.option("--iterations", default=3, show_default=True, help="Iteraciones por worker por ciclo.")
def cycle(task: str, context_files: tuple[str, ...], test_cmd: str, level: str, cycles: int, iterations: int) -> None:
    """Loop deliberativo: Cónclave planifica → workers paralelos → Cónclave audita → itera.

    Separa subtareas con comas o deja que el Cónclave las genere automáticamente.\n
    Ejemplos:\n
      atlas cycle "implementa el módulo de autenticación"\n
      atlas cycle "refactor cache, añade tests, actualiza docs" --level L2 --cycles 3
    """
    from atlas.core.inference_hub import InferenceHub, InferenceLevel  # noqa: PLC0415
    from atlas.core.code_cycle import CodeCycle  # noqa: PLC0415
    from atlas.core.parallel_coder import discover_workers  # noqa: PLC0415

    inference_level = InferenceLevel[level]
    cmd_parts = test_cmd.split()
    files = list(context_files)

    workers = discover_workers(level=inference_level)
    console.print(f"\n[bold cyan]Atlas Cycle[/bold cyan] — nivel=[yellow]{level}[/yellow] workers=[yellow]{len(workers)}[/yellow] ciclos_max=[yellow]{cycles}[/yellow]")
    console.print(f"[dim]Tarea:[/dim] {task}\n")

    if not workers:
        console.print(f"[yellow]⚠ Sin workers disponibles para {level}. Configura las API keys.[/yellow]")
        raise SystemExit(1)

    hub = InferenceHub(mode="auto")
    cc = CodeCycle(hub, repo_root=Path.cwd(), timeout_s=120)

    with console.status("[bold green]Ejecutando loop deliberativo…[/bold green]"):
        result = cc.run(task, files, cmd_parts, max_cycles=cycles, level=inference_level)

    console.print(f"\n[dim]Subtareas generadas:[/dim] {len(result.subtasks)}")
    for i, st in enumerate(result.subtasks, 1):
        console.print(f"  {i}. {st}")

    if result.parallel_result:
        console.print(f"\n[dim]Ciclos ejecutados:[/dim] {result.cycles}")
        passed = result.parallel_result.subtasks_passed
        total = result.parallel_result.subtasks_total
        console.print(f"[dim]Build:[/dim] {passed}/{total} subtareas pasaron")

    verdict = result.council_verdict or "—"
    color = "green" if verdict == "pass" else "red" if verdict == "fail" else "yellow"
    console.print(f"[dim]Veredicto Cónclave:[/dim] [{color}]{verdict}[/{color}]")

    if result.success:
        console.print(f"\n[bold green]✓ Ciclo completado con éxito[/bold green]")
    else:
        console.print(f"\n[bold red]✗ No convergió tras {result.cycles} ciclo{'s' if result.cycles > 1 else ''}[/bold red]")
        if result.error:
            console.print(f"[red]{_markup_escape(result.error)}[/red]")

    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    cli()
