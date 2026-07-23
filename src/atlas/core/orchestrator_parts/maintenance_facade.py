"""Cluster de auto-mantenimiento — extraído del god-object ``Orchestrator`` (ADR-039).

Agrupa los métodos de factory/acceso perezoso de las piezas de auto-mantenimiento:
scout, adopter, registry scout, dep scout/proposer, community scout, codegen proposer
y el scheduler que los compone. Todos son **read-only de creación**: instancian una
vez y devuelven el mismo objeto; la lógica vive en los módulos self_maintenance/*.

Inyección: ``MaintenanceFacade(orch)`` guarda ``self._orch`` y lee los colaboradores
del Orchestrator en tiempo de llamada (mismo patrón que ``AgenticExecutor``). El
import de ``Orchestrator`` se hace bajo ``TYPE_CHECKING`` para evitar ciclos.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from atlas.core.contracts import EventType
from atlas.core.provider_discovery import discover_available_models

_log = logging.getLogger(__name__)


def _isolated_cycle(name: str, tick: Callable[[], object]) -> None:
    """Ejecuta un ciclo de mantenimiento aislado: un fallo no tumba el
    scheduler, pero JAMÁS desaparece en silencio — se loguea con traceback.
    (Lección 2026-07-17: el tick del grafo llevaba horas fallando/arrastrándose
    y el `except: pass` original no dejaba ni una línea de rastro; el
    diagnóstico exigió py-spy sobre el daemon vivo.)"""
    try:
        tick()
    except Exception:  # noqa: BLE001 — una pasada rota no tumba el scheduler
        _log.exception("ciclo de mantenimiento %r falló (aislado, el scheduler sigue)", name)

if TYPE_CHECKING:
    from atlas.core.orchestrator import Orchestrator

# Cota del cuerpo descargado (mismo criterio que SecureExecutor: no leer
# respuestas ilimitadas aunque la URL esté en la allowlist).
_EGRESS_MAX_BYTES = 5 * 1024 * 1024


def _build_avoid_section(recaller: Any, store: Any, query: str) -> str:
    """Construye la sección '## Patrones a evitar' para el prompt de codegen.

    Recupera hasta 3 lecciones relevantes del store via el recaller y concatena
    sus avoid_patterns. Devuelve cadena vacía si no hay lecciones que superen
    el threshold del recaller o si el recaller/store son None."""
    if recaller is None or store is None:
        return ""
    recaller.index()
    results = recaller.recall_all(query, k=3)
    if not results:
        return ""
    patterns = "\n".join(
        f"- {lesson.avoid_pattern}"
        for r in results
        if r.matched and (lesson := store.get(r.lesson_id)) is not None
    )
    if not patterns:
        return ""
    return f"\n\n## Patrones a evitar (lecciones del sistema)\n{patterns}"


def _egress_fetch_text(url: str, *, timeout: float = 15.0) -> str:
    """Descarga el cuerpo de una URL ya autorizada por el bridge (stdlib).

    El gateo de egress lo hace el llamador vía ``SSRFBridge.check`` antes de
    invocar esto; aquí solo se hace el GET HTTP, acotando el tamaño leído."""
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — gateado por SSRFBridge
        raw: bytes = resp.read(_EGRESS_MAX_BYTES)
    return raw.decode("utf-8", errors="replace")


def _render_research_report(
    today: str, seeds: list[str], queries: list[str], findings: list[Any]
) -> str:
    """Informe crudo para docs/inbox/ — flujo sancionado: docs_triage.py lo
    clasifica después (nunca 'vigente' hasta revisión humana)."""
    lines = [
        f"# Investigación autónoma — {today}",
        "",
        "status: propuesto",
        "",
        f"Semillas ({len(seeds)}): " + ", ".join(seeds),
        f"Consultas expandidas ({len(queries)}): " + ", ".join(queries),
        "",
        f"## Hallazgos ({len(findings)})",
        "",
    ]
    if not findings:
        lines.append("Sin hallazgos esta pasada — todas las fuentes fallaron o no hubo resultados.")
    for finding in findings:
        lines.append(f"### [{finding.source}] {finding.title}")
        lines.append(f"- tema: {finding.topic}")
        lines.append(f"- url: {finding.url}")
        if finding.excerpt:
            lines.append(f"- extracto: {finding.excerpt}")
        lines.append("")
    return "\n".join(lines) + "\n"


class MaintenanceFacade:
    """Factory perezosa de todas las piezas de auto-mantenimiento (ADR-039).

    El Orchestrator instancia este facade en ``_init_components`` y delega cada
    método público ``maintenance_*`` a él. El facade lee los colaboradores del
    Orchestrator (``_merkle``, ``_ssrf_bridge``, …) en tiempo de llamada, no en
    el constructor — igual que ``AgenticExecutor`` — para preservar paridad con
    los tests que sustituyen esos atributos después de construir el Orchestrator.
    """

    def __init__(self, orch: "Orchestrator") -> None:
        self._orch = orch

        # Estado perezoso — se inicializa aquí, no en orchestrator._init_components
        self._maintenance_scout: Any = None
        self._maintenance_adopter: Any = None
        self._maintenance_registry_scout: Any = None
        self._maintenance_scheduler: Any = None
        self._maintenance_dep_scout: Any = None
        self._maintenance_dep_proposer: Any = None
        self._maintenance_codegen_proposer: Any = None
        self._maintenance_community_scout: Any = None
        self._maintenance_cold_update_batcher: Any = None
        self._maintenance_self_build_runner: Any = None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _project_root() -> Path:
        return Path(
            os.environ.get("ATLAS_CORE_ROOT", str(Path.cwd()))
        ).expanduser().resolve()

    # ------------------------------------------------------------------
    # Métodos públicos — mirrors exactos de los métodos del Orchestrator
    # ------------------------------------------------------------------

    def maintenance_scout(self) -> Any:
        """ADR-039 slice 1 — Scout read-only de salud/deuda (no muta, no propone).

        Cableado a las primitivas read-only existentes (``health_report``,
        ``GitReadTools``, ``ErrorRegistry``). ``survey()`` devuelve un informe
        estructurado auditado en Merkle. El front-half del agente de
        auto-mantenimiento; Analyst/Proposer entran en slices posteriores."""
        if self._maintenance_scout is None:
            from atlas.core.self_maintenance import MaintenanceScout

            orch = self._orch
            self._maintenance_scout = MaintenanceScout(
                merkle=orch._merkle,
                health_provider=orch.health_report,
                git_status_provider=orch._run_git_status,
                failure_provider=orch._error_registry.all,
            )
        return self._maintenance_scout

    def maintenance_adopter(self) -> Any:
        """ADR-039 slice 3 — wire propuesta → ``add_server`` (reuso puro del seam).

        Traduce una ``McpProposal`` corroborada (slice 2) en una adopción real
        vía ``adopt_mcp_server``, que consulta el decisor (ADR-040). El adopter
        no decide: bajo ``HumanDecider`` el seam exige aprobación humana y nada
        se adopta; bajo autónomo/híbrido con la intención anclada, adopta y
        registra el undo reversible (``remove_server``)."""
        if self._maintenance_adopter is None:
            from atlas.core.self_maintenance import MaintenanceAdopter

            self._maintenance_adopter = MaintenanceAdopter(
                adopt=self._orch.adopt_mcp_server,
                merkle=self._orch._merkle,
            )
        return self._maintenance_adopter

    def maintenance_registry_scout(self) -> Any:
        """ADR-039 slice 1 (literal) — Scout externo autoritativo (read-only).

        Descubre candidatos de server MCP en el registro MCP oficial. Gatea el
        egress por ``SSRFBridge`` y transporta la prosa de cada entrada como
        ``Source`` no confiable (la digiere el Analyst, no el Scout). No muta ni
        propone: emite ``McpCandidate`` etiquetados como autoritativos para el
        gate de corroboración (slice 2)."""
        if self._maintenance_registry_scout is None:
            from atlas.core.self_maintenance import RegistryScout

            self._maintenance_registry_scout = RegistryScout(
                merkle=self._orch._merkle,
                bridge=self._orch._ssrf_bridge,
                fetch=_egress_fetch_text,
            )
        return self._maintenance_registry_scout

    def maintenance_scheduler(self) -> Any:
        """ADR-039 slice 4 — Scheduler cron del front-half. Cierra el lazo vía el decisor.

        Ata las piezas ya existentes: descubre con el ``RegistryScout``
        autoritativo, analiza con el ``MaintenanceAnalyst`` (dual-LLM + gate de
        corroboración) y, por cada propuesta corroborada, (1) la surfa publicando
        ``MAINTENANCE_PROPOSED`` en el bus y (2) la enruta al ``MaintenanceAdopter``.

        El cron no decide ni aplica por sí mismo: la adopción pasa SIEMPRE por
        ``adopt_mcp_server`` → seam del decisor (ADR-040). Bajo ``HumanDecider``
        (default) el seam devuelve "requiere aprobación humana" y nada se adopta
        — paridad exacta con el HITL de hoy, surfado por el evento. Bajo
        autónomo/híbrido con la intención anclada, adopta en caliente y registra
        el undo reversible. Esto es human-ON-the-loop: el punto de decisión es el
        decisor intercambiable, no un botón hardcodeado.

        Cadencia: 24h por defecto (conservador en coste LLM/red), configurable
        vía ``ATLAS_MAINTENANCE_POLL_S`` (segundos) — sin esto,
        ``_self_build_cycle``/``_dep_cycle``/``_batch_cycle`` solo corren UNA
        vez al arrancar el daemon."""
        if self._maintenance_scheduler is None:
            from atlas.core.inference_hub import InferenceHub
            from atlas.core.self_maintenance import (
                MaintenanceAnalyst,
                MaintenanceScheduler,
                McpProposal,
            )

            orch = self._orch
            hub = orch._inference_hub or InferenceHub(mode="auto")
            analyst = MaintenanceAnalyst(merkle=orch._merkle, hub=hub)

            def _notify(proposals: list[McpProposal]) -> None:
                orch._bus.publish_type(
                    EventType.MAINTENANCE_PROPOSED,
                    {
                        "proposal_ids": [p.id for p in proposals],
                        "capabilities": [p.capability for p in proposals],
                        "count": len(proposals),
                    },
                )
                # 2026-07-04: la llamada al adopter SÍ se restaura (había sido
                # retirada antes por error de diagnóstico). El hallazgo real de
                # la auditoría del historial (110 intentos, 25 "adoptados") no
                # era "esto salta el HITL" — `adopter.adopt()` YA pasaba
                # siempre por `adopt_mcp_server` → el seam del decisor
                # (ADR-040): bajo HumanDecider no hace nada, bajo
                # autónomo/híbrido adopta con la intención anclada. El bug de
                # verdad era que `McpRegistry.add_server()` solo mutaba la
                # config EN MEMORIA — una adopción aprobada por el decisor
                # nunca sobrevivía a un reinicio. Con `persist_path` cableado
                # (McpRegistry ahora reescribe mcp_servers.json en cada
                # add/remove), la adopción por fin es una acción durable, así
                # que el cribado ya construido (SSRFBridge + MaintenanceAnalyst
                # dual-LLM + decisor anclado) vuelve a tener un efecto real que
                # gatear, en vez de evaporarse solo.
                adopter = self._orch.maintenance_adopter()
                for proposal in proposals:
                    adopter.adopt(proposal)

            def _dep_cycle() -> None:
                # Rama de auto-actualización de deps.
                # Se enruta por self._orch para que los monkeypatches sobre
                # Orchestrator (e.g. _no_real_dep_scout en conftest) sean
                # respetados en tests (ADR-039 fix regresión).
                scout = self._orch.maintenance_dep_scout()
                proposer = self._orch.maintenance_dep_proposer()
                for cand in scout.discover() or []:
                    proposal = proposer.propose_bump(cand)
                    if proposal is not None:
                        orch.advance_cold_update(proposal.id)

            def _self_build_cycle() -> None:
                # Autoconstrucción: ver maintenance_self_build_tick (extraído a
                # método para que el preflight y el gating sean testeables).
                _isolated_cycle("self_build", self.maintenance_self_build_tick)

            def _research_cycle() -> None:
                # Investigación abierta: ver maintenance_research_tick. Aislado
                # como los demás ciclos — un fallo de red/parseo no tumba el
                # scheduler ni bloquea self-build/dep/batch.
                _isolated_cycle("research", self.maintenance_research_tick)

            def _provider_smoke_cycle() -> None:
                # Smoke de cadena: ver maintenance_provider_smoke_tick. Aislado
                # igual que los demás ciclos.
                _isolated_cycle("provider_smoke", self.maintenance_provider_smoke_tick)

            def _provider_discovery_cycle() -> None:
                # Descubrimiento de catálogo vs model_id configurado: ver
                # maintenance_provider_discovery_tick. Aislado igual que los
                # demás ciclos (T6, plan 2026-07-23-t5-provider-discovery-plan.md).
                _isolated_cycle("provider_discovery", self.maintenance_provider_discovery_tick)

            def _knowledge_ingest_cycle() -> None:
                # Cierre investigación→acción: ver maintenance_knowledge_ingest_tick.
                _isolated_cycle("knowledge_ingest", self.maintenance_knowledge_ingest_tick)

            def _project_graph_cycle() -> None:
                # Grafo vivo automático: ver maintenance_project_graph_tick.
                _isolated_cycle("project_graph", self.maintenance_project_graph_tick)

            def _batch_cycle() -> None:
                # Lote de self_audit probado en worktree efímero (ColdUpdateBatcher).
                # Se enruta por self._orch por el mismo motivo que _dep_cycle:
                # respetar monkeypatches de tests sobre el Orchestrator.
                #
                # TODO(batch+benchmark): ColdUpdateBatcher no expone las rutas del
                # worktree final antes de limpiar; integrar BenchmarkGate.compare()
                # requeriría ese hook — ver backlog. Fuera de alcance de este slice.
                batcher = self._orch.maintenance_cold_update_batcher()
                result = batcher.run_batch()
                if not result.included:
                    return  # nada real que revisar, evitar ruido
                manager = self._orch.cold_update()
                included_intents = [
                    p.intent for pid in result.included
                    if (p := manager.get(pid)) is not None
                ]
                orch._bus.publish_type(EventType.COLD_UPDATE_BATCH_READY, {
                    "batch_id": result.id,
                    "included": result.included,
                    "included_intents": included_intents,
                    "excluded": result.excluded,
                    "tests_passed": result.passed,
                    "pytest_summary": result.pytest_summary[:500],
                })

            scheduler_kwargs: dict[str, Any] = {}
            poll_raw = os.environ.get("ATLAS_MAINTENANCE_POLL_S", "").strip()
            if poll_raw:
                # 2026-07-04: antes no existía forma de configurar la cadencia
                # sin tocar código — el default (24h) hacía que
                # _self_build_cycle/_dep_cycle/_batch_cycle corrieran UNA vez
                # al arrancar el daemon y no de nuevo hasta el día siguiente,
                # muy lejos del "24/7" con el que se planteó la pieza. Sigue
                # siendo opt-in (por defecto 24h, conservador en coste de
                # LLM/red) — el operador decide la cadencia real.
                try:
                    scheduler_kwargs["poll_interval_seconds"] = int(float(poll_raw))
                except ValueError:
                    pass

            self._maintenance_scheduler = MaintenanceScheduler(
                merkle=orch._merkle,
                discover=self._orch.maintenance_registry_scout().discover,
                analyze=analyst.analyze,
                notify=_notify,
                extra_cycles=(
                    _dep_cycle, _batch_cycle, _self_build_cycle,
                    _research_cycle, _provider_smoke_cycle,
                    _knowledge_ingest_cycle, _project_graph_cycle,
                    _provider_discovery_cycle,
                ),
                **scheduler_kwargs,
            )
        return self._maintenance_scheduler

    def maintenance_self_build_tick(self) -> dict[str, Any]:
        """Un tick de autoconstrucción: preflight barato → UN item pending del backlog.

        Roadmap "juicio real" paso 1, cableado en producción (2026-07-08): antes
        de gastar LLM en construir, ``PreflightGate`` descarta gratis lo
        obviamente malo (CVEs de dependencias + radar de saneamiento). Si el
        preflight no pasa, el tick se salta ESTE ciclo con evidencia en Merkle
        (nunca silencioso) — no se construye sobre una base vulnerable; el
        ``_dep_cycle`` propone el bump que lo desbloquea.

        Opt-in explícito (gasta LLM): requiere ``ATLAS_SELF_BUILD=1``. Un item
        por tick acota el gasto; el resultado queda auditado en Merkle por el
        runner y las propuestas van a ColdUpdate (HITL intacto).

        t1-daemon-control-surface: si ``atlas selfbuild pause`` está activo
        (fichero ``workspace/self_build/pause_state.json``, ver
        ``self_build_pause.py``), el tick es un no-op inmediato -- NO
        consume el siguiente item del backlog, ni corre el preflight, ni
        gasta LLM. Es SOLO este ciclo (self_build); el resto de
        ``atlas serve`` (dashboard/API/MCP y los demás ciclos del
        scheduler: dep/batch/research/etc.) sigue corriendo intacto."""
        # Guardia anti-recursión (incidente 2026-07-09, EN PRODUCCIÓN): la
        # suite que el propio lazo corre en su worktree hereda el env del
        # daemon (ATLAS_SELF_BUILD=1 vía systemd EnvironmentFile) — un test
        # que arranque el MaintenanceScheduler real disparaba OTRO run_item
        # real → otro worktree → otra suite → cascada hasta agotar la máquina.
        # ToolCoder/AtlasCoder/ValidationRunner/evo marcan sus suites con
        # ATLAS_NESTED_TEST_RUN=1; aquí el tick se niega, gaste lo que gaste
        # el resto del env en pedirlo.
        if os.environ.get("ATLAS_NESTED_TEST_RUN", "").strip() == "1":
            return {"status": "nested_run_guard"}
        if os.environ.get("ATLAS_SELF_BUILD", "").strip() != "1":
            return {"status": "disabled"}

        from atlas.core.self_maintenance.self_build_pause import is_paused

        if is_paused(self._project_root()):
            return {"status": "paused"}

        from atlas.core.self_maintenance.backlog import (
            load_backlog,
            load_queue_state,
            next_runnable,
            record_outcome,
            save_queue_state,
        )
        from atlas.core.self_maintenance.preflight_gate import PreflightGate

        preflight = PreflightGate().check()
        if not preflight.passed:
            self._orch._merkle.log(
                action="self_build.preflight_blocked",
                agent="maintenance_facade",
                result="skipped",
                risk_level="moderate",
                payload={
                    "cve_found": preflight.cve_found,
                    "cve_findings": preflight.cve_findings[:20],
                },
            )
            return {"status": "preflight_blocked", "preflight": preflight.to_dict()}

        items = load_backlog(self._project_root() / "docs" / "backlog.yaml")
        # Selección con backoff (2026-07-09): un item que falla N ticks seguidos
        # cede el turno al siguiente pendiente en vez de acaparar el lazo — la
        # noche del 07-08 un solo item quemó todos los ticks mientras el resto
        # de la cola esperaba. El contador persiste entre reinicios del daemon.
        state_path = self._project_root() / "workspace" / "self_build" / "queue_state.json"
        state = load_queue_state(state_path)
        # No reproponer un item que ya tiene una propuesta esperando revisión
        # humana (incidente 2026-07-11, ver docstring de next_runnable).
        open_statuses = {"proposed", "validated", "approved"}
        open_proposal_item_ids = frozenset(
            item_id
            for p in self._orch.cold_update().list_proposals()
            if p.status in open_statuses
            and (item_id := p.evidence.get("backlog_item_id"))
        )
        item = next_runnable(items, state, open_proposal_item_ids=open_proposal_item_ids)
        if item is None:
            return {"status": "no_pending"}
        runner = self._orch.maintenance_self_build_runner()
        result: dict[str, Any] = runner.run_item(item)
        save_queue_state(
            state_path,
            record_outcome(state, item.id, success=result.get("status") == "proposed"),
        )
        # 2026-07-09: tres ticks fallidos en una noche dejaron CERO rastro —
        # solo el preflight se auditaba. El resultado de cada run_item queda
        # en Merkle siempre, converja o no; sin esto el lazo es ciego a sus
        # propios fracasos y nadie puede reconstruir qué pasó.
        self._orch._merkle.log(
            action="self_build.run_item",
            agent="maintenance_facade",
            result=str(result.get("status", "unknown")),
            risk_level="moderate",
            payload={
                "item_id": result.get("item_id"),
                "proposal_id": result.get("proposal_id"),
                "detail": str(result.get("detail") or "")[:800],
                "files_changed": result.get("files_changed", []),
            },
        )
        return {"status": "ran", "result": result}

    def maintenance_research_tick(self) -> dict[str, Any]:
        """Un tick de investigación: intereses recientes → consultas variadas →
        descubrimiento abierto → informe en docs/inbox/ (Fase 4, 2026-07-09).

        Causa raíz del hueco (barrido previo): ``PanoramaScout``,
        ``TopicExpander`` y ``SotaSnapshotRecorder`` estaban completos y
        probados, pero sin dueño en el scheduler — "ayer se suponía que Atlas
        iba a investigar y no lo hizo" (corrección directa del usuario).

        Descubrimiento ABIERTO, no lista fija (matiz de la visión: serendipia
        sistematizada, no vigilancia de una lista conocida de competidores):
        las semillas son los títulos de las lecciones más recientes del
        ``LessonStore`` — lo que Atlas acaba de aprender/fallar decide qué
        investiga después. Sin lecciones aún, cae a los 3 intereses de fondo
        que ``topic_expander.py`` documenta como ejemplo (memoria de agentes,
        orquestación local, auditoría verificable) — intereses propios de
        Atlas, no una lista de fuentes externas fijas.

        Opt-in explícito (gasta LLM + red saliente): requiere
        ``ATLAS_RESEARCH=1``. Cadencia propia de 24h vía fichero de estado
        (independiente del poll del scheduler) — no tiene sentido pagar el
        ciclo completo de descubrimiento más de una vez al día."""
        # Guardia anti-recursión — ver maintenance_self_build_tick.
        if os.environ.get("ATLAS_NESTED_TEST_RUN", "").strip() == "1":
            return {"status": "nested_run_guard"}
        if os.environ.get("ATLAS_RESEARCH", "").strip() != "1":
            return {"status": "disabled"}

        import json
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date().isoformat()
        state_path = self._project_root() / "workspace" / "research" / "state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        if state.get("last_run_date") == today:
            return {"status": "already_ran_today"}

        from atlas.core.inference_hub import InferenceHub
        from atlas.core.lesson_store import LessonStore
        from atlas.core.self_maintenance.panorama_scout import PanoramaScout
        from atlas.core.self_maintenance.topic_expander import TopicExpander

        orch = self._orch
        hub = orch._inference_hub or InferenceHub(mode="auto")

        # Semillas: títulos de las lecciones más recientes (lo aprendido/
        # fallado decide qué se investiga) — fallback a intereses de fondo
        # de Atlas si el store está vacío (arranque en frío, sin lecciones).
        store = LessonStore(self._project_root() / "workspace" / "lessons")
        recent = sorted(store.all(), key=lambda item: item.created_at, reverse=True)[:3]
        seeds = [lesson.title for lesson in recent] or [
            "memoria de agentes de IA",
            "orquestación local de modelos",
            "auditoría verificable de sistemas de IA",
        ]

        expander = TopicExpander(hub=hub, merkle=orch._merkle)
        queries = expander.expand(seeds, queries_per_seed=4)

        scout = PanoramaScout(
            merkle=orch._merkle,
            bridge=orch._ssrf_bridge,
            fetch=_egress_fetch_text,
            topics=queries,
            max_results_per_topic=4,
        )
        findings = scout.discover()

        report_path = self._project_root() / "docs" / "inbox" / f"research_{today}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_render_research_report(today, seeds, queries, findings), encoding="utf-8")

        state["last_run_date"] = today
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        orch._merkle.log(
            action="self_maintenance.research_tick",
            agent="maintenance_facade",
            result="ran",
            risk_level="safe",
            payload={
                "seeds": seeds,
                "queries_count": len(queries),
                "findings_count": len(findings),
                "report_path": str(report_path),
            },
        )
        return {
            "status": "ran",
            "seeds": seeds,
            "queries_count": len(queries),
            "findings_count": len(findings),
            "report_path": str(report_path),
        }

    def maintenance_provider_smoke_tick(self) -> dict[str, Any]:
        """Smoke diario de la cadena de proveedores (Fase 5, 2026-07-09).

        Causa raíz: modelos decomisionados/renombrados upstream se
        descubrían por accidente, quemando una llamada real fallida en
        cada pasada del fallback hasta retirarlos a mano — "falta smoke
        diario de cadena" (memoria provider-chain-rot). Cada proveedor de
        ``DEFAULT_PROVIDERS`` recibe UNA llamada mínima en aislamiento
        (``InferenceHub.probe_provider``, bypasea la cadena de fallback);
        el resultado (ok/failed/skipped) se persiste + audita en Merkle.
        Barato por diseño (max_tokens=8 por proveedor): no gasta el
        presupuesto de un LLM caro.

        Opt-in explícito: requiere ``ATLAS_PROVIDER_SMOKE=1``. Cadencia
        propia de 24h (fichero de estado, independiente del poll del
        scheduler)."""
        # Guardia anti-recursión — ver maintenance_self_build_tick.
        if os.environ.get("ATLAS_NESTED_TEST_RUN", "").strip() == "1":
            return {"status": "nested_run_guard"}
        if os.environ.get("ATLAS_PROVIDER_SMOKE", "").strip() != "1":
            return {"status": "disabled"}

        import json
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date().isoformat()
        state_path = self._project_root() / "workspace" / "self_build" / "provider_smoke_state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        if state.get("last_run_date") == today:
            return {"status": "already_ran_today"}

        from atlas.core.inference_hub import InferenceHub
        from atlas.core.self_maintenance.provider_smoke import ProviderChainSmoke

        orch = self._orch
        hub = orch._inference_hub or InferenceHub(mode="auto")
        smoke = ProviderChainSmoke(hub=hub)
        results = smoke.run()

        dead = [r.provider_name for r in results if r.outcome == "failed"]
        ok = [r.provider_name for r in results if r.outcome == "ok"]
        skipped = [r.provider_name for r in results if r.outcome == "skipped"]

        state["last_run_date"] = today
        state["last_results"] = [r.to_dict() for r in results]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        orch._merkle.log(
            action="self_maintenance.provider_smoke_tick",
            agent="maintenance_facade",
            result="ran",
            risk_level="safe",
            payload={"ok": ok, "dead": dead, "skipped": skipped},
        )
        return {"status": "ran", "ok": ok, "dead": dead, "skipped": skipped}

    def maintenance_provider_discovery_tick(self) -> dict[str, Any]:
        """Descubrimiento diario de catálogo servido vs `model_id` configurado
        (T5.2/T5.3, plan 2026-07-23-t5-provider-discovery-plan.md, T6).

        Complementa al smoke (T5.1), no lo sustituye: ``ModelCatalogDrift``
        (T4, ``model_catalog_drift.py``) cruza cada ``Provider.model_id`` de
        ``DEFAULT_PROVIDERS`` contra el catálogo que ``discover_available_models``
        (T3, ``provider_discovery.py``) confirma que el proveedor sirve AHORA
        -- ``GET .../models``, cero llamadas de inferencia, cero tokens.
        Predice el mismo fallo que ya mordió a la cadena (qwen3-coder 410,
        nvidia_kimi 404, deepseek decomisionado) ANTES de gastarlo en una
        llamada real. Un proveedor puede *listar* un modelo que su tier no
        sirve de verdad (caso NIM histórico) -- el smoke sigue siendo
        necesario para verificar la invocación; discovery/drift lo antecede
        y lo abarata filtrando primero los muertos-por-catálogo.

        Opt-in explícito: requiere ``ATLAS_PROVIDER_DISCOVERY=1``. Cadencia
        propia de 24h (fichero de estado, independiente del poll del
        scheduler) -- espejo exacto de ``maintenance_provider_smoke_tick``."""
        # Guardia anti-recursión -- ver maintenance_self_build_tick.
        if os.environ.get("ATLAS_NESTED_TEST_RUN", "").strip() == "1":
            return {"status": "nested_run_guard"}
        if os.environ.get("ATLAS_PROVIDER_DISCOVERY", "").strip() != "1":
            return {"status": "disabled"}

        import json
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date().isoformat()
        state_path = self._project_root() / "workspace" / "self_build" / "provider_discovery_state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        if state.get("last_run_date") == today:
            return {"status": "already_ran_today"}

        from atlas.core.self_maintenance.model_catalog_drift import ModelCatalogDrift

        orch = self._orch
        # `discover_available_models` referenciado por nombre a nivel de
        # módulo (no reimportado aquí) para que los tests puedan
        # monkeypatchear `maintenance_facade.discover_available_models` sin
        # tocar red real -- mismo patrón que `_egress_fetch_text` en
        # `maintenance_research_tick`.
        drift = ModelCatalogDrift(discover=discover_available_models)
        results = drift.run()

        missing = [r.provider_name for r in results if r.outcome == "missing"]
        present = [r.provider_name for r in results if r.outcome == "present"]
        skipped = [r.provider_name for r in results if r.outcome == "skipped"]

        state["last_run_date"] = today
        state["last_results"] = [r.to_dict() for r in results]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        orch._merkle.log(
            action="self_maintenance.provider_discovery_tick",
            agent="maintenance_facade",
            result="ran",
            risk_level="safe",
            payload={"missing": missing, "present": present, "skipped": skipped},
        )
        return {"status": "ran", "missing": missing, "present": present, "skipped": skipped}

    def maintenance_knowledge_ingest_tick(self) -> dict[str, Any]:
        """Cierre del ciclo investigación→acción (2026-07-09): los informes que
        ``maintenance_research_tick`` deja en docs/inbox/ morían allí.

        Tres pasos, todos deterministas (CERO LLM):
        1. Triage acotado: ``scripts/docs_triage.py`` clasifica los
           ``research_*.md`` del inbox por regla determinista → docs/knowledge
           con alta 'propuesto' en INDEX.yaml (flujo sancionado; 'vigente'
           sigue siendo del revisor humano).
        2. Ingesta al sustrato: la carga estándar del repo (docs vigentes +
           lecciones) y los informes triados entran al ``SqliteMemoryIndex``
           del tronco vía ``knowledge_ingest`` — antes era un one-shot manual
           sin dueño runtime. Solo ficheros CAMBIADOS (sha256 en el estado):
           la pasada diaria no re-embebe el corpus entero.
        3. Evidencia en Merkle.

        La BD es la del tronco MCP (~/atlas-mcp/memory.db) salvo override
        ``ATLAS_MEMORY_DB`` — mismo sustrato que sirve ``recall`` a cualquier
        agente conectado. Opt-in: ``ATLAS_KNOWLEDGE_INGEST=1``. Cadencia
        propia de 24h (fichero de estado, independiente del poll)."""
        # Guardia anti-recursión — ver maintenance_self_build_tick.
        if os.environ.get("ATLAS_NESTED_TEST_RUN", "").strip() == "1":
            return {"status": "nested_run_guard"}
        if os.environ.get("ATLAS_KNOWLEDGE_INGEST", "").strip() != "1":
            return {"status": "disabled"}

        import hashlib
        import json
        from datetime import datetime, timezone

        root = self._project_root()
        today = datetime.now(timezone.utc).date().isoformat()
        state_path = root / "workspace" / "knowledge" / "ingest_state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        if state.get("last_run_date") == today:
            return {"status": "already_ran_today"}

        # 1. Triage determinista acotado a research_*.md (sin LLM: la regla
        # por nombre basta y el tick no debe gastar inferencia en clasificar).
        triaged = 0
        triage_script = root / "scripts" / "docs_triage.py"
        if triage_script.is_file():
            import importlib.util

            spec = importlib.util.spec_from_file_location("docs_triage", triage_script)
            assert spec and spec.loader
            triage = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(triage)
            plan = [
                step for step in triage.build_plan(root / "docs", llm_classify=None)
                if step["file"].startswith("research_") and step["action"] == "move"
            ]
            if plan:
                triaged = triage.apply_plan(plan, root / "docs")

        # 2. Ingesta incremental al sustrato del tronco.
        from atlas.mcp.memory_server import build_gated_index
        from atlas.mcp.memory_trunk import MemoryTrunk
        from atlas.memory.knowledge_ingest import (
            ingest_paths, repo_knowledge_paths, research_report_paths,
        )

        db_env = os.environ.get("ATLAS_MEMORY_DB", "").strip()
        db_path = Path(db_env).expanduser() if db_env else Path.home() / "atlas-mcp" / "memory.db"
        ingested_sha: dict[str, str] = state.setdefault("ingested_sha", {})

        def _changed(paths: list[Path]) -> list[Path]:
            out: list[Path] = []
            for p in paths:
                try:
                    sha = hashlib.sha256(p.read_bytes()).hexdigest()
                except OSError:
                    continue
                rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
                if ingested_sha.get(rel) != sha:
                    out.append(p)
                    ingested_sha[rel] = sha
            return out

        index = build_gated_index(db_path)
        try:
            trunk = MemoryTrunk(index)
            repo_res = ingest_paths(
                trunk, _changed(repo_knowledge_paths(root)), repo_root=root,
            )
            research_res = ingest_paths(
                trunk, _changed(research_report_paths(root)), repo_root=root,
                record_type="research_report",
            )
        finally:
            index.close()

        # 3. Digestión (E, 2026-07-10): hallazgos de los informes → candidatos
        # de catálogo (determinista, dedupe fail-closed, status SIEMPRE
        # 'candidato'). El eslabón que faltaba: el ciclo consumía pero no
        # convertía hallazgos en candidatos accionables.
        digested = 0
        try:
            from atlas.core.self_maintenance.research_digest import (
                append_candidates_to_catalog,
                digest_findings,
            )
            from atlas.mcp.catalog import load_catalog, load_taxonomy

            catalog_path = root / "docs" / "design" / "mcp_catalog.yaml"
            classified_path = root / "docs" / "design" / "mcp_catalog_classified.yaml"
            if catalog_path.is_file():
                catalog = load_catalog(catalog_path)
                if classified_path.is_file():
                    catalog = catalog + load_catalog(classified_path)
                reports = [
                    p.read_text(encoding="utf-8", errors="replace")
                    for p in research_report_paths(root)
                ]
                suggestions = digest_findings(
                    reports, catalog, load_taxonomy(catalog_path)
                )
                if suggestions and classified_path.is_file():
                    digested = append_candidates_to_catalog(suggestions, classified_path)
        except Exception:  # noqa: BLE001 — la digestión es extra, nunca rompe la ingesta
            pass

        state["last_run_date"] = today
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        payload = {
            "triaged": triaged,
            "repo_docs": repo_res["docs"],
            "repo_records": repo_res["records"],
            "research_docs": research_res["docs"],
            "research_records": research_res["records"],
            "digested_candidates": digested,
            "db_path": str(db_path),
        }
        self._orch._merkle.log(
            action="self_maintenance.knowledge_ingest_tick",
            agent="maintenance_facade",
            result="ran",
            risk_level="safe",
            payload=payload,
        )
        return {"status": "ran", **payload}

    def maintenance_project_graph_tick(self) -> dict[str, Any]:
        """Regeneración automática del grafo vivo del proyecto (Fase 3bis).

        "El grafo ES el presente": las tools graph_* del tronco responden desde
        la BD Kuzu, y esta se quedaba atrás en cuanto había commits nuevos (la
        query de importers de inference_hub daba 19 vs 20 de grep por un módulo
        posterior a la última ingesta). Sin LLM y sin red: git log + parse de
        imports + MERGE idempotente en Kuzu (``build_project_graph``).

        Gating por HEAD, no por reloj: el grafo solo puede cambiar si hay
        commits nuevos, así que se salta mientras HEAD no se mueva — más
        fresco que una cadencia diaria (regenera al primer poll tras un
        commit) y más barato (cero trabajo en reposo).

        Regenera sobre una COPIA y hace swap al final: el write-lock de Kuzu
        es de proceso entero y excluye hasta las conexiones read-only de otros
        procesos (verificado en vivo 2026-07-10: ~9 min de "Could not set
        lock" en las tools graph_* durante un build directo). Con el swap la
        ventana de indisponibilidad pasa de minutos a microsegundos.

        Opt-in explícito: requiere ``ATLAS_PROJECT_GRAPH=1``. BD override:
        ``ATLAS_PROJECT_GRAPH_DB`` (default DEFAULT_GRAPH_DB)."""
        # Guardia anti-recursión — ver maintenance_self_build_tick.
        if os.environ.get("ATLAS_NESTED_TEST_RUN", "").strip() == "1":
            return {"status": "nested_run_guard"}
        if os.environ.get("ATLAS_PROJECT_GRAPH", "").strip() != "1":
            return {"status": "disabled"}

        import json
        import subprocess
        from datetime import datetime, timezone

        root = self._project_root()
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root, capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return {"status": "no_git"}

        state_path = root / "workspace" / "knowledge" / "project_graph_state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            state = {}
        if state.get("last_head") == head:
            return {"status": "up_to_date", "head": head}

        import shutil

        from atlas.memory.project_graph import (
            DEFAULT_GRAPH_DB,
            build_project_graph,
            resolve_graph_embedder,
        )

        db_env = os.environ.get("ATLAS_PROJECT_GRAPH_DB", "").strip()
        db = Path(db_env).expanduser() if db_env else DEFAULT_GRAPH_DB
        wal = db.with_name(db.name + ".wal")
        rebuild = db.with_name(db.name + ".rebuild")
        rebuild_wal = rebuild.with_name(rebuild.name + ".wal")
        rebuild.unlink(missing_ok=True)
        rebuild_wal.unlink(missing_ok=True)
        if db.exists():
            # Copia = el histórico bitemporal se conserva (MERGE incremental);
            # el write-lock cae sobre la copia, no sobre la BD servida.
            db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db, rebuild)
            if wal.exists():
                shutil.copy2(wal, rebuild_wal)

        # Vault-wiring (F3.2, 2026-07-16): sin vault_root las tablas
        # ObsidianNote/LINKS_TO jamás llegaban a la BD servida (hallazgo C2).
        # Default = <repo>/graphify-vault (donde graphify deja el vault);
        # override env ATLAS_OBSIDIAN_VAULT (mismo patrón que
        # ATLAS_PROJECT_GRAPH_DB). build_project_graph ya ignora un vault
        # inexistente (guard is_dir), así que esto nunca rompe la regen.
        vault_env = os.environ.get("ATLAS_OBSIDIAN_VAULT", "").strip()
        vault_root = Path(vault_env).expanduser() if vault_env else root / "graphify-vault"

        metrics = build_project_graph(
            root,
            rebuild,
            vault_root=vault_root,
            embedder=resolve_graph_embedder(),
        )

        # Call-graph de Graphify (D3, 2026-07-10): se ingiere al MISMO rebuild
        # antes del swap. El cache oficial vive en <repo>/graphify-out (no en
        # src/graphify-out, que era un residuo antiguo) y se limita al corpus
        # de producción src/atlas. Un cache ausente/roto o Symbol==0 invalida
        # TODA la regeneración: no se sirve una BD que finja tener call-graph.
        callgraph_cache = root / "graphify-out" / "cache" / "ast"
        try:
            if not callgraph_cache.is_dir():
                raise RuntimeError(
                    f"Graphify AST cache unavailable: {callgraph_cache}"
                )

            from atlas.memory.callgraph_to_kuzu import load_callgraph_into_kuzu

            callgraph_metrics = load_callgraph_into_kuzu(
                callgraph_cache,
                rebuild,
                source_prefix="src/atlas",
                replace=True,
                strict=True,
            )
            if int(callgraph_metrics.get("symbols", 0)) <= 0:
                raise RuntimeError(
                    "Graphify call-graph produced zero symbols for corpus src/atlas"
                )
            if int(callgraph_metrics.get("files", 0)) <= 0:
                raise RuntimeError(
                    "Graphify call-graph matched zero files for corpus src/atlas"
                )
            metrics["callgraph"] = callgraph_metrics
        except Exception:
            # El rebuild nunca se publica si Graphify falla; se elimina para
            # que tampoco parezca un artefacto listo en una inspección manual.
            rebuild.unlink(missing_ok=True)
            rebuild_wal.unlink(missing_ok=True)
            raise

        # Swap: primero el fichero principal, luego el wal (el close de la
        # ingesta hace checkpoint, así que el wal del rebuild suele estar
        # vacío/ausente). Ventana de inconsistencia: microsegundos.
        os.replace(rebuild, db)
        if rebuild_wal.exists():
            os.replace(rebuild_wal, wal)
        else:
            wal.unlink(missing_ok=True)

        state["last_head"] = head
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        self._orch._merkle.log(
            action="self_maintenance.project_graph_tick",
            agent="maintenance_facade",
            result="ran",
            risk_level="safe",
            payload={
                "head": head,
                "commits": len(metrics.get("commits", [])),
                "callgraph": metrics["callgraph"],
            },
        )
        return {"status": "ran", "head": head, "metrics": metrics}

    def maintenance_self_build_runner(self) -> Any:
        """Autoconstrucción — pega backlog → ToolCoder → ColdUpdate (self_audit).

        Reusa el ``ColdUpdateManager`` ya existente del orquestador; toda
        propuesta generada por este runner requiere aprobación humana
        explícita (invariante CVE-HITL, G0.8) — el runner solo PROPONE."""
        if self._maintenance_self_build_runner is None:
            from atlas.core.inference_hub import InferenceHub
            from atlas.core.self_maintenance.self_build_runner import SelfBuildRunner

            orch = self._orch
            hub = orch._inference_hub or InferenceHub(mode="auto")
            self._maintenance_self_build_runner = SelfBuildRunner(
                self._project_root(),
                hub,
                self._orch.cold_update(),
                backlog_path=self._project_root() / "docs" / "backlog.yaml",
            )
        return self._maintenance_self_build_runner

    def maintenance_cold_update_batcher(self) -> Any:
        """Lote de self_audit — combina propuestas `validated` del mismo origen
        y las prueba conjuntamente en un worktree efímero (ver
        ``ColdUpdateBatcher``). Reusa el ``ColdUpdateManager`` ya existente del
        orquestador; no aplica nada por sí mismo.

        Roadmap "juicio real" pasos 2 y 5, cableados en producción (2026-07-08):
        ``BatchPremortemGate`` razona sobre riesgos de la COMBINACIÓN antes de
        pagar la suite completa (señal, nunca gate duro) y ``FailureLessonSink``
        convierte cada exclusión de la bisección en una lección con contador de
        ocurrencias en el LessonStore unificado (<repo>/workspace/lessons) — sin
        esto el lazo no aprendía nada de sus propios fallos."""
        if self._maintenance_cold_update_batcher is None:
            from atlas.core.cold_update_batcher import ColdUpdateBatcher
            from atlas.core.inference_hub import InferenceHub
            from atlas.core.self_maintenance.batch_premortem import BatchPremortemGate
            from atlas.core.self_maintenance.failure_lesson_sink import (
                FailureLessonSink,
            )

            orch = self._orch
            hub = orch._inference_hub or InferenceHub(mode="auto")
            premortem = BatchPremortemGate(hub=hub, merkle=orch._merkle)

            # Mismo patrón defensivo que el LessonStore del codegen proposer:
            # si el store no puede abrirse, el batcher corre sin sink (señal
            # degradada) en vez de romper el ciclo de lotes.
            sink: Any = None
            try:
                from atlas.core.lesson_store import LessonStore

                _repo_root = orch._repo_root() or orch._workspace
                sink = FailureLessonSink(
                    store=LessonStore(_repo_root / "workspace" / "lessons"),
                )
            except Exception:  # noqa: BLE001 — sink opcional, nunca bloquea
                sink = None

            # 2026-07-10: BenchmarkGate por fin CABLEADO (TODO histórico de
            # este fichero). Señal, nunca gate bloqueante; sin dataset marca
            # skipped con receta accionable (scripts/fetch_longmemeval.py).
            from atlas.core.self_maintenance.benchmark_gate import BenchmarkGate

            self._maintenance_cold_update_batcher = ColdUpdateBatcher(
                manager=self._orch.cold_update(),
                premortem=premortem,
                failure_lesson_sink=sink,
                benchmark_gate=BenchmarkGate(repo_root=_repo_root),
            )
        return self._maintenance_cold_update_batcher

    def maintenance_dep_scout(self) -> Any:
        """ADR-039 slice 6 — Scout de bumps de dependencias PyPI (read-only).

        Lee los pisos de ``[project.dependencies]`` del ``pyproject`` y consulta
        PyPI (autoritativo, egress gateado) por la última estable. No muta:
        emite ``DepCandidate``; la materialización del patch es del proposer."""
        if self._maintenance_dep_scout is None:
            from atlas.core.self_maintenance import DepScout

            self._maintenance_dep_scout = DepScout(
                merkle=self._orch._merkle,
                bridge=self._orch._ssrf_bridge,
                fetch=_egress_fetch_text,
                deps_provider=self._orch._pyproject_dep_floors,
            )
        return self._maintenance_dep_scout

    def maintenance_dep_proposer(self) -> Any:
        """ADR-039 slice 6 — Materializa un bump como patch revisable de ColdUpdate.

        Construye el diff del bump y lo entrega a ``ColdUpdateManager.propose``
        con ``origin="self_audit"``. Nunca aplica: ColdUpdate valida en worktree
        y la adopción exige el seam del decisor (ADR-040)."""
        if self._maintenance_dep_proposer is None:
            from atlas.core.self_maintenance import DepProposer

            self._maintenance_dep_proposer = DepProposer(
                merkle=self._orch._merkle,
                propose=self._orch.cold_update().propose,
                pyproject_path=self._project_root() / "pyproject.toml",
            )
        return self._maintenance_dep_proposer

    def maintenance_community_scout(self) -> Any:
        """ADR-039 slice 5 — Scout community (foros) con corroboración obligatoria.

        El foro solo *surge* nombres candidatos; cada uno se contrasta contra el
        registro MCP oficial (autoritativo). Sin respaldo autoritativo se descarta
        (fail-closed): un candidato solo-foro nunca se propone. Los campos salen
        del candidato autoritativo; la prosa del foro viaja como ``Source``
        community no confiable."""
        if self._maintenance_community_scout is None:
            from atlas.core.self_maintenance import CommunityScout, McpCandidate

            index: dict[str, McpCandidate] = {}
            built = [False]

            def _lookup(name: str) -> "McpCandidate | None":
                if not built[0]:
                    for c in self._orch.maintenance_registry_scout().discover():
                        index[c.name] = c
                    built[0] = True
                if name in index:
                    return index[name]
                # Coincidencia laxa: el foro suele citar el nombre corto del paquete.
                for cname, cand in index.items():
                    if cname.endswith("/" + name) or name in cname.split("/"):
                        return cand
                return None

            self._maintenance_community_scout = CommunityScout(
                merkle=self._orch._merkle,
                bridge=self._orch._ssrf_bridge,
                fetch=_egress_fetch_text,
                forum_urls=[
                    "https://hn.algolia.com/api/v1/search?query=mcp%20server&tags=story",
                ],
                authoritative_lookup=_lookup,
            )
        return self._maintenance_community_scout

    def maintenance_codegen_proposer(self) -> Any:
        """ADR-039 slice 7 — Codegen como patch dirigido (revisable, nunca apply solo).

        El humano apunta el objetivo (``CodegenTarget``); el LLM de control genera
        un diff; el proposer impone que solo toque el fichero apuntado y lo entrega
        a ColdUpdate con ``origin="self_audit"``. Coherente con ADR-025: la
        generación es libre, la aplicación nunca es autónoma."""
        if self._maintenance_codegen_proposer is None:
            from atlas.core.inference_hub import InferenceHub, InferenceLevel
            from atlas.core.self_maintenance import CodegenProposer, CodegenTarget
            from atlas.core.verify import ArtifactKind, UnifiedDiffVerifier, UniversalVerifier
            from atlas.router.cascade import CascadeRouter, Difficulty, InferenceProducer, TaskSpec

            orch = self._orch
            hub = orch._inference_hub or InferenceHub(mode="auto")
            # Capa 2 (ADR-042): L0 local primero, escalada a L1 si el diff no
            # verifica. FRONTIER queda preparado: cuando exista un provider L2
            # es añadir un rung aquí. El path conversacional (CLAIM) NO se
            # cablea: sin verificador más barato que el modelo, la cascada
            # solo diría UNKNOWN — sería teatro de verificación.
            cascade = CascadeRouter(
                UniversalVerifier([UnifiedDiffVerifier()]),
                [
                    InferenceProducer(
                        hub, level=InferenceLevel.L0,
                        capability=Difficulty.HARD, temperature=0.0,
                    ),
                    InferenceProducer(
                        hub, level=InferenceLevel.L1,
                        capability=Difficulty.HARD, temperature=0.0,
                    ),
                ],
            )

            # Cargar LessonStore para inyección blanda de avoid_patterns.
            #
            # 2026-07-03: unificado a <repo_root>/workspace/lessons — la MISMA
            # convención que AtlasCoder/ToolCoder (src/atlas/core/atlas_coder.py,
            # tool_coder.py), donde YA viven las lecciones reales generadas por
            # el propio motor de codificación. Antes apuntaba a
            # `orch._workspace / "memory" / "lessons"` (~/atlas/memory/lessons,
            # runtime workspace) — una ruta que ni siquiera existía, así que el
            # self-audit del Orchestrator nunca veía las lecciones reales que el
            # propio Atlas ya había generado (hallazgo real, verificado en vivo).
            try:
                from atlas.core.lesson_store import LessonStore
                from atlas.immunity.lesson_recaller import LessonRecaller
                from atlas.memory.embeddings import default_embedder

                _repo_root = orch._repo_root() or orch._workspace
                _lesson_store = LessonStore(_repo_root / "workspace" / "lessons")
                # threshold 0.55 MEDIDO 2026-07-08 (antes: default 0.8, que en
                # la práctica no recuperaba NADA): con fastembed multilingüe,
                # consultas claramente relacionadas puntúan 0.55-0.69 y las no
                # relacionadas ≤0.47. A 0.8 el lazo "aprendía" lecciones que
                # jamás volvían a salir. Falso positivo aquí es barato (una
                # línea extra de avoid_pattern en el prompt de codegen); este
                # override NO toca los umbrales del sistema inmune.
                _lesson_recaller: Any = LessonRecaller(
                    _lesson_store,
                    embedder=default_embedder(),
                    threshold=0.55,
                )
            except Exception:  # noqa: BLE001 — directorio no existe u otro error; degradado
                _lesson_store = None
                _lesson_recaller = None

            def _generate(target: CodegenTarget) -> str:
                avoid_section = _build_avoid_section(
                    _lesson_recaller,
                    _lesson_store,
                    f"{target.goal} {target.path}",
                )
                prompt = (
                    "Genera SOLO un diff unificado (git apply) que logre el objetivo, "
                    f"tocando únicamente el fichero {target.path}. No expliques.\n\n"
                    f"Objetivo: {target.goal}\n"
                    f"{avoid_section}"
                )
                result = cascade.route(TaskSpec(
                    intent=prompt,
                    kind=ArtifactKind.PATCH,
                    metadata={
                        "context": target.context,
                        "task_id": "codegen.patch",
                        "allowed_paths": [target.path],
                    },
                ))
                orch._merkle.log(
                    action="cascade.route",
                    agent="codegen_cascade",
                    result="success" if result.verified else "failure",
                    risk_level="safe",
                    payload=result.to_dict(),
                    task_id="codegen.patch",
                )
                if not (result.verified and result.artifact is not None):
                    return ""
                return str(result.artifact.payload.get("diff", ""))

            self._maintenance_codegen_proposer = CodegenProposer(
                merkle=orch._merkle,
                generate=_generate,
                propose=orch.cold_update().propose,
            )
        return self._maintenance_codegen_proposer
