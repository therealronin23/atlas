#!/usr/bin/env python3
"""
Atlas Core — Pipeline Smoke Test (end-to-end, infra real)

Construye un Orchestrator efimero con pipeline Gate D activo,
le inyecta un InferenceHub real (LiteLLM contra los proveedores
configurados en .env) y ejecuta una secuencia de intents que
ejercita cada bifurcacion del pipeline:

  1. intent determinista        -> rule-based 1.0 -> ejecuta + ghost record
  2. intent repetido            -> ghost HIT  (camino corto)
  3. intent ambiguo de resumen  -> rule-based < umbral -> SLM toma relevo
                                                          (Groq real)
  4. intent destructivo         -> rule-based BLOCKED (governance)
  5. intent que requiere aprobacion -> queue de approvals

Al final, verify_chain en MerkleLogger + cada cadena de TimeTravel,
y un resumen con latencias, paths del classifier y stats del cache.

Uso:
    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
      .venv/bin/python scripts/pipeline_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.core.contracts import RoutingLevel, TaskStatus, TaskSource
from atlas.core.inference_hub import DEFAULT_PROVIDERS, InferenceHub
from atlas.core.orchestrator import Orchestrator
from atlas.memory.embeddings import StubEmbedder


# ---------------------------------------------------------------------------
# Resultado por intent
# ---------------------------------------------------------------------------


@dataclass
class IntentResult:
    label: str
    intent: str
    status: str
    route: str | None
    tool_name: str | None
    classifier_path: str          # "rule" | "rule->slm" | "ghost_hit" | "n/a"
    ghost: str                    # "miss-record" | "hit" | "not_checked"
    latency_ms: float
    expected_status: str | None = None
    tt_steps: list[str] = field(default_factory=list)
    error: str | None = None
    inference_provider: str | None = None
    inference_latency_ms: int | None = None
    inference_tokens: int | None = None
    inference_excerpt: str | None = None
    pii_redacted: int | None = None

    @property
    def matches_expectation(self) -> bool:
        if self.status == "exception":
            return False
        if self.expected_status is None:
            return True
        return self.status == self.expected_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


PALETTE = {
    "ok":      "\033[92m",   # verde
    "warn":    "\033[93m",   # amarillo
    "err":     "\033[91m",   # rojo
    "dim":     "\033[2m",
    "bold":    "\033[1m",
    "reset":   "\033[0m",
}


def color(text: str, name: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{PALETTE.get(name, '')}{text}{PALETTE['reset']}"


def header(title: str) -> None:
    print(color(f"\n=== {title} ===", "bold"))


def detect_provider_keys() -> dict[str, bool]:
    """Mapa env_var -> presente. Mostrado en cabecera."""
    seen: dict[str, bool] = {}
    for p in DEFAULT_PROVIDERS:
        if p.api_key_env is None:
            continue
        seen[p.api_key_env] = bool(os.environ.get(p.api_key_env))
    return seen


def classifier_path_from_merkle(orch: Orchestrator, task_id: str) -> str:
    """
    Inspecciona el audit log para deducir que rama del classifier corrio.
      - ghost_hit       -> action 'task.ghost_hit' presente
      - rule->slm[wins] -> SLM consultado y winner=slm en task.classified
      - rule (slm-tied) -> SLM consultado pero rule gano el empate
      - rule            -> rule directamente, sin consultar SLM
      - n/a             -> nada (bloqueo temprano o aprobacion antes de clasificar)
    """
    records = list(orch._merkle.tail(80))
    relevant = [r for r in records if r.task_id == task_id]
    if any(r.action == "task.ghost_hit" for r in relevant):
        return "ghost_hit"
    classified = next((r for r in relevant if r.action == "task.classified"), None)
    if classified is None:
        return "n/a"
    winner = (classified.payload or {}).get("winner", "rule")
    slm_consulted = any(r.action == "classify.slm_consulted" for r in relevant)
    if winner == "slm":
        return "rule->slm[wins]"
    if slm_consulted:
        return "rule (slm-tied)"
    return "rule"


def timetravel_labels(orch: Orchestrator, task_id: str) -> list[str]:
    if orch.timetravel is None:
        return []
    return [h.label for h in orch.timetravel.list_history(task_id)]


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def run_intent(
    orch: Orchestrator, label: str, intent: str, *,
    expected_status: str | None = None,
) -> IntentResult:
    """Ejecuta un intent, mide latencia y compone el IntentResult."""
    start = time.perf_counter()
    error: str | None = None
    try:
        task = orch.handle_intent(intent, source=TaskSource.INTERNAL)
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        return IntentResult(
            label=label, intent=intent, status="exception",
            route=None, tool_name=None,
            classifier_path="n/a", ghost="not_checked",
            latency_ms=(time.perf_counter() - start) * 1000.0,
            expected_status=expected_status,
            tt_steps=[], error=error,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000.0

    classifier = classifier_path_from_merkle(orch, task.id)
    ghost = "hit" if classifier == "ghost_hit" else (
        "miss-record" if task.status == TaskStatus.DONE else "not_checked"
    )
    tt = timetravel_labels(orch, task.id)

    # Si la tarea pasó por inference_hub, extraemos los metadatos.
    inference_provider = None
    inference_latency_ms = None
    inference_tokens = None
    inference_excerpt = None
    pii_redacted = None
    if task.tool_name == "inference_hub.complete" and isinstance(task.result, dict):
        inference_provider = task.result.get("provider")
        inference_latency_ms = task.result.get("latency_ms")
        inference_tokens = task.result.get("tokens_used")
        txt = task.result.get("text") or ""
        inference_excerpt = txt[:120] + "..." if len(txt) > 120 else txt
        pii_redacted = task.result.get("pii_redacted")

    return IntentResult(
        label=label,
        intent=intent,
        status=task.status.value,
        route=task.route.value if task.route else None,
        tool_name=task.tool_name,
        classifier_path=classifier,
        ghost=ghost,
        latency_ms=elapsed_ms,
        expected_status=expected_status,
        tt_steps=tt,
        error=task.error,
        inference_provider=inference_provider,
        inference_latency_ms=inference_latency_ms,
        inference_tokens=inference_tokens,
        inference_excerpt=inference_excerpt,
        pii_redacted=pii_redacted,
    )


def print_result(idx: int, total: int, r: IntentResult) -> None:
    if r.matches_expectation:
        tag = color(r.status, "ok") if r.status == "done" else color(r.status, "warn")
    else:
        tag = color(r.status, "err")
    intent_short = r.intent if len(r.intent) <= 60 else r.intent[:57] + "..."
    print(f"\n[{idx}/{total}] {color(r.label, 'bold')}")
    print(f"  intent     : {intent_short!r}")
    print(f"  status     : {tag}" + (
        f"  (esperado: {r.expected_status})" if r.expected_status else ""
    ))
    if r.route:
        print(f"  route      : {r.route}")
    if r.tool_name:
        print(f"  tool       : {r.tool_name}")
    print(f"  classifier : {r.classifier_path}")
    print(f"  ghost      : {r.ghost}")
    print(f"  latency    : {r.latency_ms:.1f} ms")
    if r.inference_provider is not None:
        print(f"  inference  : provider={r.inference_provider} "
              f"latency_hub={r.inference_latency_ms}ms tokens={r.inference_tokens}")
        if r.pii_redacted:
            print(f"  pii        : {r.pii_redacted} elemento(s) sustituido(s) ida + restaurado(s) vuelta")
        if r.inference_excerpt:
            print(f"  excerpt    : {r.inference_excerpt!r}")
    if r.tt_steps:
        print(f"  timetravel : {' -> '.join(r.tt_steps)}")
    if r.error and r.status != "blocked":
        # Para BLOCKED, task.error suele llevar el detalle del block reason,
        # no es un fallo del pipeline. Solo lo mostramos como warning.
        print(f"  {color('error: ' + r.error, 'err')}")
    elif r.error:
        print(f"  {color('block reason: ' + r.error, 'dim')}")


def main() -> int:
    header("Atlas Core — Pipeline Smoke (end-to-end)")
    keys = detect_provider_keys()
    present = [k for k, v in keys.items() if v]
    missing = [k for k, v in keys.items() if not v]
    print(f"  provider keys present : {present}")
    if missing:
        print(color(f"  provider keys missing : {missing}", "dim"))
    if not present:
        print(color(
            "\nNo hay keys de proveedores en el entorno. El SLM en modo live\n"
            "necesita al menos una. Sigo igualmente — el SLM caera a stub\n"
            "para los intents que requieran clasificacion no determinista.\n",
            "warn",
        ))

    with tempfile.TemporaryDirectory(prefix="atlas-smoke-") as d:
        workspace = Path(d) / "atlas"
        os.environ["ATLAS_HOME"] = str(workspace)
        print(f"  workspace             : {workspace}")

        # InferenceHub real (modo auto -> live si hay key + no en pytest)
        hub = InferenceHub(mode="auto")
        orch = Orchestrator(workspace=workspace)
        orch.enable_gate_d_pipeline(
            embedder=StubEmbedder(dim=64),
            inference_hub=hub,
            slm_mode="auto",
        )

        # ----------------------------------------------------------------
        # Secuencia de intents
        # ----------------------------------------------------------------

        intents: list[tuple[str, str, str]] = [
            (
                "rule-based determinista (miss + record)",
                "lista los archivos del workspace",
                "done",
            ),
            (
                "ghost hit (intent repetido)",
                "lista los archivos del workspace",
                "done",
            ),
            (
                "intent ambiguo - puede activar SLM",
                "explicame brevemente que es un Merkle tree",
                "done",
            ),
            (
                "governance block (rule-based prevalece)",
                "ejecuta sudo rm -rf /var/log",
                "blocked",
            ),
            (
                "requires approval (git push)",
                "haz git push origin main",
                "awaiting_approval",
            ),
        ]

        results: list[IntentResult] = []
        for i, (label, intent, expected) in enumerate(intents, 1):
            r = run_intent(orch, label, intent, expected_status=expected)
            results.append(r)
            print_result(i, len(intents), r)

        # ----------------------------------------------------------------
        # Verificaciones
        # ----------------------------------------------------------------

        header("Verifications")
        ok_merkle, msg_merkle = orch._merkle.verify_chain()
        merkle_tag = color("OK", "ok") if ok_merkle else color("FAIL", "err")
        print(f"  Merkle chain  : {merkle_tag} ({orch._merkle.record_count} records)  {msg_merkle}")

        tt_all_ok = True
        if orch.timetravel is not None:
            for task_id in orch.timetravel.list_tasks():
                ok, msg = orch.timetravel.verify_chain(task_id)
                if not ok:
                    print(color(f"  TimeTravel    : FAIL en {task_id}: {msg}", "err"))
                    tt_all_ok = False
            if tt_all_ok:
                count = len(orch.timetravel.list_tasks())
                print(f"  TimeTravel    : {color('OK', 'ok')} ({count} tareas)")

        # ----------------------------------------------------------------
        # Stats
        # ----------------------------------------------------------------

        header("Stats")
        if orch.ghost_replay is not None:
            stats = orch.ghost_replay.stats()
            print(f"  ghost_replay  : hits={stats['hits']}  misses={stats['misses']}  "
                  f"entries={stats['entries']}")
        path_counts: dict[str, int] = {}
        for r in results:
            path_counts[r.classifier_path] = path_counts.get(r.classifier_path, 0) + 1
        print(f"  classifier    : {path_counts}")

        # ----------------------------------------------------------------
        # Resumen final
        # ----------------------------------------------------------------

        header("Summary")
        failed = [r for r in results if not r.matches_expectation]
        if failed:
            print(color(f"  {len(failed)} intent(s) NO cumplen su expectativa.", "err"))
            for p in failed:
                print(f"    - {p.label}: status={p.status} esperado={p.expected_status} "
                      f"{('error=' + p.error) if p.error else ''}")
            return 1
        if not ok_merkle or not tt_all_ok:
            print(color("  cadena hash con fallo de integridad.", "err"))
            return 1
        print(color(
            f"  Pipeline Gate D verificado end-to-end ({len(results)}/{len(results)} intents OK).",
            "ok",
        ))
        return 0


if __name__ == "__main__":
    sys.exit(main())
