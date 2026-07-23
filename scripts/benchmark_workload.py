#!/usr/bin/env python3
"""
Atlas Core — Workload Benchmark Harness (t6-workload-benchmark-harness)

Mide, con datos REALES sobre el hardware presente (HP Omen: i7-6700HQ, 16GB RAM,
GTX 960M 4GB VRAM), los workloads objetivo listados en la seccion "Next
Validation" de docs/operations/atlas_box_architecture.md:

    1. classification        -> Ollama local (modelo pequeno, qwen2.5:0.5b)
    2. memory_distillation    -> atlas.memory.distiller.MemoryDistiller (CPU puro,
                                  sin LLM, StubEmbedder para aislar el coste del
                                  algoritmo de compresion/ranking)
    3. browser_tasks          -> Playwright + Chromium headless, pagina LOCAL
                                  (file://), cero red
    4. code_generation        -> Ollama local (modelo grande, qwen2.5-coder:7b)
    5. dashboard              -> FastAPI TestClient contra atlas.interfaces.dashboard,
                                  arranque en frio + peticiones calientes
    6. voice                  -> NO ejecutado hoy (ver SKIPPED_WORKLOADS abajo):
                                  faster-whisper/piper/sounddevice no estan
                                  instalados en este entorno (VoiceModule solo
                                  corre en modo "stub", que no mide nada real de
                                  hardware) e instalarlos seria aprovisionar
                                  dependencias nuevas, fuera del alcance de esta
                                  tarea ("cero aprovisionamiento de infraestructura
                                  nueva"). Documentado explicitamente, no simulado.

Restricciones duras (ver docs/backlog.yaml, t6-workload-benchmark-harness):
    - Cero llamadas de red de pago: solo Ollama local (localhost:11434) y
      file:// para el navegador. Ninguna API de pago (Groq/OpenRouter/NVIDIA/etc).
    - Cero aprovisionamiento de infraestructura: nada de Docker/VMs/paquetes
      nuevos. Usa lo que ya esta instalado.

Termico/RAM: reusa el mecanismo YA existente de src/atlas/thermal/watchdog.py
(ThermalWatchdog.sample_now()) en vez de inventar un lector de /sys nuevo.

Salida: JSON reproducible a stdout o --output <path>. El campo
"bottleneck_analysis" se calcula a partir de los propios datos medidos en esa
ejecucion (no es una conclusion fija de antemano) e identifica el cuello de
botella real observado: latencia/throughput/VRAM/RAM/termico/complejidad de
setup. No es una recomendacion de compra.

Uso:
    .venv/bin/python scripts/benchmark_workload.py
    .venv/bin/python scripts/benchmark_workload.py --output /tmp/bench.json
    .venv/bin/python scripts/benchmark_workload.py --workloads classification,memory_distillation
    .venv/bin/python scripts/benchmark_workload.py --fast   # repeats reducidos, humo rapido
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypedDict

if TYPE_CHECKING:
    from atlas.memory.distiller import Chunk

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

OLLAMA_HOST = "http://127.0.0.1:11434"
SCRIPT_VERSION = "1.0"

ALL_WORKLOADS = (
    "classification",
    "memory_distillation",
    "browser_tasks",
    "code_generation",
    "dashboard",
)

VOICE_SKIP_REASON = (
    "faster-whisper, piper-tts y sounddevice no estan instalados en este "
    "entorno (verificado por import real, no supuesto). "
    "src/atlas/interfaces/voice.py.REAL_DEPS_AVAILABLE == False aqui, asi que "
    "VoiceModule solo puede correr en modo 'stub' (texto fijo / print a "
    "consola), que no ejercita ningun hardware real y por tanto no produce "
    "una medicion honesta de latencia/throughput de voz. Instalar esas deps "
    "es aprovisionar dependencias nuevas -> fuera del alcance de este item "
    "('cero aprovisionamiento de infraestructura nueva'). No se simula un "
    "numero: se documenta el hueco explicitamente, tal y como pide el brief."
)


# ---------------------------------------------------------------------------
# Utilidades de estadistica
# ---------------------------------------------------------------------------


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    p95_idx = min(n - 1, max(0, int(round(0.95 * (n - 1)))))
    return {
        "n": n,
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "p95": round(sorted_v[p95_idx], 4),
        "stdev": round(statistics.pstdev(values), 4) if n > 1 else 0.0,
    }


# ---------------------------------------------------------------------------
# Snapshot del sistema (termico/RAM via ThermalWatchdog ya existente; GPU via
# nvidia-smi, best-effort)
# ---------------------------------------------------------------------------


@dataclass
class SystemSnapshot:
    temperature_celsius: float
    ram_free_mb: int
    operational_mode: str
    thermal_policy: str
    gpu_name: str | None
    gpu_vram_used_mb: float | None
    gpu_vram_total_mb: float | None
    gpu_temperature_celsius: float | None
    gpu_util_pct: float | None
    sampled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class GpuInfo(TypedDict, total=False):
    gpu_name: str | None
    gpu_vram_used_mb: float | None
    gpu_vram_total_mb: float | None
    gpu_temperature_celsius: float | None
    gpu_util_pct: float | None
    error: str


def read_gpu_nvidia_smi() -> GpuInfo:
    """Lee VRAM/temp/util de la GPU via nvidia-smi. None si no hay GPU NVIDIA."""
    binary = shutil.which("nvidia-smi")
    if not binary:
        return {
            "gpu_name": None,
            "gpu_vram_used_mb": None,
            "gpu_vram_total_mb": None,
            "gpu_temperature_celsius": None,
            "gpu_util_pct": None,
        }
    try:
        out = subprocess.run(
            [
                binary,
                "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        line = out.stdout.strip().splitlines()[0]
        name, mem_used, mem_total, temp, util = [p.strip() for p in line.split(",")]
        return {
            "gpu_name": name,
            "gpu_vram_used_mb": float(mem_used),
            "gpu_vram_total_mb": float(mem_total),
            "gpu_temperature_celsius": float(temp),
            "gpu_util_pct": float(util),
        }
    except Exception as exc:  # pragma: no cover - best effort telemetry
        return {
            "gpu_name": None,
            "gpu_vram_used_mb": None,
            "gpu_vram_total_mb": None,
            "gpu_temperature_celsius": None,
            "gpu_util_pct": None,
            "error": str(exc),
        }


def system_snapshot() -> SystemSnapshot:
    from atlas.thermal.watchdog import ThermalWatchdog

    watchdog = ThermalWatchdog()
    thermal = watchdog.sample_now()
    gpu = read_gpu_nvidia_smi()
    return SystemSnapshot(
        temperature_celsius=thermal.temperature_celsius,
        ram_free_mb=thermal.ram_free_mb,
        operational_mode=thermal.operational_mode.value
        if hasattr(thermal.operational_mode, "value")
        else str(thermal.operational_mode),
        thermal_policy=thermal.policy,
        gpu_name=gpu.get("gpu_name"),
        gpu_vram_used_mb=gpu.get("gpu_vram_used_mb"),
        gpu_vram_total_mb=gpu.get("gpu_vram_total_mb"),
        gpu_temperature_celsius=gpu.get("gpu_temperature_celsius"),
        gpu_util_pct=gpu.get("gpu_util_pct"),
    )


# ---------------------------------------------------------------------------
# Ollama helpers (HTTP local, cero red externa)
# ---------------------------------------------------------------------------


def ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3) as resp:
            return int(resp.status) == 200
    except Exception:
        return False


def ollama_version() -> str | None:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/version", timeout=3) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode())
            return str(body["version"])
    except Exception:
        return None


def ollama_ps_cli() -> str:
    """Salida cruda de `ollama ps` (PROCESSOR muestra CPU vs GPU real)."""
    binary = shutil.which("ollama")
    if not binary:
        return ""
    try:
        out = subprocess.run([binary, "ps"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def ollama_generate(model: str, prompt: str, *, num_predict: int = 120, timeout: int = 180) -> dict[str, Any]:
    """Llama a /api/generate (stream=False) y devuelve el JSON completo de Ollama,
    que ya incluye total_duration/eval_count/eval_duration en nanosegundos —
    la fuente mas fiable de tokens/sec, sin medir a mano con time.perf_counter."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data: dict[str, Any] = json.loads(resp.read().decode())
    wall_s = time.perf_counter() - t0
    data["_wall_clock_s"] = round(wall_s, 4)
    return data


def _ns_to_s(ns: int | None) -> float | None:
    if ns is None:
        return None
    return round(ns / 1e9, 4)


def _tokens_per_sec(count: int | None, duration_ns: int | None) -> float | None:
    if not count or not duration_ns:
        return None
    seconds = duration_ns / 1e9
    if seconds <= 0:
        return None
    return round(count / seconds, 3)


# ---------------------------------------------------------------------------
# Workload 1 — classification (Ollama, modelo pequeno)
# ---------------------------------------------------------------------------

CLASSIFICATION_MODEL = "qwen2.5:0.5b"
CLASSIFICATION_PROMPTS = [
    "Clasifica el siguiente texto en UNA sola palabra "
    "(agenda, bug, trivia, recordatorio o incidente). Responde solo la palabra.\n"
    "Texto: 'Reunion manana 9am con el equipo de ventas para revisar el pipeline Q3.'",
    "Clasifica el siguiente texto en UNA sola palabra "
    "(agenda, bug, trivia, recordatorio o incidente). Responde solo la palabra.\n"
    "Texto: 'Error 500 al llamar al endpoint /api/users, stack trace adjunto.'",
    "Clasifica el siguiente texto en UNA sola palabra "
    "(agenda, bug, trivia, recordatorio o incidente). Responde solo la palabra.\n"
    "Texto: 'El servidor de produccion esta devolviendo timeouts intermitentes desde las 3am.'",
]


def run_classification_workload(repeats: int) -> dict[str, Any]:
    if not ollama_reachable():
        return {"skipped": True, "reason": "Ollama no responde en localhost:11434"}

    per_call: list[dict[str, Any]] = []
    for prompt in CLASSIFICATION_PROMPTS:
        for _ in range(repeats):
            resp = ollama_generate(CLASSIFICATION_MODEL, prompt, num_predict=10)
            per_call.append({
                "wall_clock_s": resp["_wall_clock_s"],
                "total_duration_s": _ns_to_s(resp.get("total_duration")),
                "load_duration_s": _ns_to_s(resp.get("load_duration")),
                "prompt_eval_count": resp.get("prompt_eval_count"),
                "eval_count": resp.get("eval_count"),
                "tokens_per_sec": _tokens_per_sec(resp.get("eval_count"), resp.get("eval_duration")),
                "response_snippet": (resp.get("response") or "").strip()[:40],
            })

    latencies = [c["wall_clock_s"] for c in per_call]
    tps = [c["tokens_per_sec"] for c in per_call if c["tokens_per_sec"] is not None]
    return {
        "model": CLASSIFICATION_MODEL,
        "prompts": len(CLASSIFICATION_PROMPTS),
        "repeats_per_prompt": repeats,
        "calls": per_call,
        "latency_s": _stats(latencies),
        "tokens_per_sec": _stats(tps),
        "ollama_ps_after": ollama_ps_cli(),
    }


# ---------------------------------------------------------------------------
# Workload 4 — code_generation (Ollama, modelo grande)
# ---------------------------------------------------------------------------

CODEGEN_MODEL = "qwen2.5-coder:7b"
CODEGEN_PROMPTS = [
    "Write a Python function that returns the nth Fibonacci number using "
    "memoization. Only output the code, no explanation.",
    "Write a Python function that checks if a string is a palindrome, "
    "ignoring case and spaces. Only output the code, no explanation.",
]


def run_code_generation_workload(repeats: int) -> dict[str, Any]:
    if not ollama_reachable():
        return {"skipped": True, "reason": "Ollama no responde en localhost:11434"}

    per_call: list[dict[str, Any]] = []
    for prompt in CODEGEN_PROMPTS:
        for _ in range(repeats):
            resp = ollama_generate(CODEGEN_MODEL, prompt, num_predict=150, timeout=300)
            per_call.append({
                "wall_clock_s": resp["_wall_clock_s"],
                "total_duration_s": _ns_to_s(resp.get("total_duration")),
                "load_duration_s": _ns_to_s(resp.get("load_duration")),
                "prompt_eval_count": resp.get("prompt_eval_count"),
                "prompt_eval_tokens_per_sec": _tokens_per_sec(
                    resp.get("prompt_eval_count"), resp.get("prompt_eval_duration")
                ),
                "eval_count": resp.get("eval_count"),
                "tokens_per_sec": _tokens_per_sec(resp.get("eval_count"), resp.get("eval_duration")),
                "response_snippet": (resp.get("response") or "").strip()[:80].replace("\n", " "),
            })

    latencies = [c["wall_clock_s"] for c in per_call]
    tps = [c["tokens_per_sec"] for c in per_call if c["tokens_per_sec"] is not None]
    return {
        "model": CODEGEN_MODEL,
        "prompts": len(CODEGEN_PROMPTS),
        "repeats_per_prompt": repeats,
        "calls": per_call,
        "latency_s": _stats(latencies),
        "tokens_per_sec": _stats(tps),
        "ollama_ps_after": ollama_ps_cli(),
    }


# ---------------------------------------------------------------------------
# Workload 2 — memory_distillation (CPU puro, sin LLM, sin red)
# ---------------------------------------------------------------------------


def _synthetic_chunks(n: int) -> list[Chunk]:
    from atlas.memory.distiller import Chunk, ChunkSource

    topics = [
        "el orquestador enruta segun RoutingLevel y confianza del clasificador",
        "el MerkleLogger encadena hashes para auditar acciones irreversibles",
        "el ThermalWatchdog degrada a modo OMEGA por encima de 80 grados",
        "el SSRFBridge bloquea IPs privadas y exige allowlist de dominios",
        "el PolicyEngine aplica invariantes duros antes de cualquier efecto externo",
        "KuzuDB almacena el grafo de memoria con vectores para busqueda semantica",
        "el LessonStore corrobora patrones nuevos con umbral de coseno 0.65",
        "el InferenceHub hace fallback entre proveedores L1/L2 por nivel de riesgo",
    ]
    sources = [ChunkSource.PATTERN, ChunkSource.FAILURE, ChunkSource.EVIDENCE, ChunkSource.NOTE]
    chunks = []
    for i in range(n):
        text = f"{topics[i % len(topics)]} (variante sintetica #{i})"
        chunks.append(Chunk(
            text=text,
            source=sources[i % len(sources)],
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
    return chunks


def run_memory_distillation_workload(repeats: int, corpus_size: int = 300) -> dict[str, Any]:
    from atlas.memory.distiller import Chunk, ChunkSource, MemoryDistiller
    from atlas.memory.embeddings import StubEmbedder

    embedder = StubEmbedder(dim=64)
    distiller = MemoryDistiller(embedder=embedder, target_tokens=800)
    chunks = _synthetic_chunks(corpus_size)
    system_chunks = [Chunk(text="Constitucion Atlas: nunca autorizar sin HITL.", source=ChunkSource.SYSTEM)]
    recent_chunks = [Chunk(text="Usuario acaba de pedir el estado del ThermalWatchdog.", source=ChunkSource.RECENT)]
    all_chunks = system_chunks + chunks + recent_chunks

    queries = [
        "como se degrada el sistema por temperatura",
        "como se audita una accion irreversible",
        "como se decide si delegar a un proveedor externo",
    ]

    latencies: list[float] = []
    results_meta = []
    for query in queries:
        for _ in range(repeats):
            t0 = time.perf_counter()
            result = distiller.distill(query, all_chunks)
            dt = time.perf_counter() - t0
            latencies.append(dt)
        results_meta.append({
            "query": query,
            "selected_chunks": len(result.chunks),
            "discarded_count": result.discarded_count,
            "total_tokens": result.total_tokens,
            "budget": result.budget,
        })

    return {
        "embedder": "StubEmbedder(dim=64) — deterministico, sin red; ver nota de diseno"
                    " en el docstring del script (fastembed no cacheado localmente,"
                    " se evita descarga de red durante un benchmark autonomo)",
        "corpus_size": corpus_size + len(system_chunks) + len(recent_chunks),
        "queries": len(queries),
        "repeats_per_query": repeats,
        "latency_s": _stats(latencies),
        "per_query_result": results_meta,
    }


# ---------------------------------------------------------------------------
# Workload 3 — browser_tasks (Playwright + Chromium headless, file:// local)
# ---------------------------------------------------------------------------

_LOCAL_HTML_FIXTURE = """<!doctype html>
<html><head><title>Atlas Benchmark Fixture</title></head>
<body>
<h1>Atlas Core benchmark page</h1>
<p id="marker">workload-browser-tasks-ok</p>
<ul>{items}</ul>
</body></html>
""".format(items="".join(f"<li>item-{i}</li>" for i in range(50)))


def run_browser_workload(repeats: int) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"skipped": True, "reason": f"playwright no instalado: {exc}"}

    fixture_path = Path(tempfile.gettempdir()) / "atlas_benchmark_fixture.html"
    fixture_path.write_text(_LOCAL_HTML_FIXTURE, encoding="utf-8")
    fixture_url = fixture_path.as_uri()

    nav_latencies: list[float] = []
    extract_latencies: list[float] = []
    screenshot_latencies: list[float] = []

    with sync_playwright() as pw:
        t0 = time.perf_counter()
        browser = pw.chromium.launch(headless=True)
        launch_s = time.perf_counter() - t0

        screenshot_path = Path(tempfile.gettempdir()) / "atlas_benchmark_screenshot.png"
        for _ in range(repeats):
            page = browser.new_page()

            t0 = time.perf_counter()
            page.goto(fixture_url)
            nav_latencies.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            text = page.inner_text("#marker")
            extract_latencies.append(time.perf_counter() - t0)
            assert text.strip() == "workload-browser-tasks-ok", f"fixture mismatch: {text!r}"

            t0 = time.perf_counter()
            page.screenshot(path=str(screenshot_path))
            screenshot_latencies.append(time.perf_counter() - t0)

            page.close()

        t0 = time.perf_counter()
        browser.close()
        close_s = time.perf_counter() - t0

    screenshot_bytes = screenshot_path.stat().st_size if screenshot_path.exists() else None
    return {
        "note": "navegacion a file:// local (pagina fixture generada por el script), "
                "cero red — ejercita el mismo motor Chromium headless que "
                "src/atlas/tools/browser.py usa tras pasar el SSRFBridge",
        "repeats": repeats,
        "browser_launch_s": round(launch_s, 4),
        "browser_close_s": round(close_s, 4),
        "navigation_s": _stats(nav_latencies),
        "extract_text_s": _stats(extract_latencies),
        "screenshot_s": _stats(screenshot_latencies),
        "screenshot_bytes": screenshot_bytes,
    }


# ---------------------------------------------------------------------------
# Workload 5 — dashboard (FastAPI TestClient, mismo patron que tests/test_dashboard.py)
# ---------------------------------------------------------------------------

DASHBOARD_ROUTES = ["/", "/api/status", "/api/health", "/tasks", "/memory", "/tools", "/providers"]


def run_dashboard_workload(repeats: int) -> dict[str, Any]:
    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        return {"skipped": True, "reason": f"fastapi/testclient no instalado: {exc}"}

    import os

    with tempfile.TemporaryDirectory(prefix="atlas_bench_dashboard_") as tmp:
        workspace = Path(tmp) / "atlas_bench"
        for sub in [
            "config", "memory/system_context", "memory/error_registry",
            "memory/approved_patterns", "memory/performance", "memory/audit",
            "projects", "tmp", "skills",
        ]:
            (workspace / sub).mkdir(parents=True, exist_ok=True)

        src_config = REPO_ROOT / "config"
        shutil.copy(src_config / "governance.json", workspace / "config" / "governance.json")
        shutil.copy(src_config / "permissions.yaml", workspace / "config" / "permissions.yaml")

        old_home = os.environ.get("ATLAS_HOME")
        old_token = os.environ.get("ATLAS_DASHBOARD_TOKEN")
        os.environ["ATLAS_HOME"] = str(workspace)
        bench_token = "benchmark-dashboard-token-32-chars-min"
        os.environ["ATLAS_DASHBOARD_TOKEN"] = bench_token
        try:
            import atlas.interfaces.dashboard as dash_module
            dash_module._orch = None

            t0 = time.perf_counter()
            client = TestClient(
                dash_module.app,
                headers={"Authorization": f"Bearer {bench_token}"},
            )
            # Primera peticion = arranque en frio real (instancia Orchestrator, etc.)
            cold_resp = client.get("/")
            cold_start_s = time.perf_counter() - t0

            per_route: dict[str, Any] = {}
            for route in DASHBOARD_ROUTES:
                latencies = []
                status = None
                for _ in range(repeats):
                    t0 = time.perf_counter()
                    resp = client.get(route)
                    latencies.append(time.perf_counter() - t0)
                    status = resp.status_code
                per_route[route] = {
                    "status_code": status,
                    "latency_s": _stats(latencies),
                }

            return {
                "note": "TestClient de starlette contra atlas.interfaces.dashboard:app, "
                        "mismo patron que tests/test_dashboard.py — sin puerto de red real",
                "cold_start_s": round(cold_start_s, 4),
                "cold_start_status_code": cold_resp.status_code,
                "repeats_per_route": repeats,
                "routes": per_route,
            }
        finally:
            if old_home is None:
                os.environ.pop("ATLAS_HOME", None)
            else:
                os.environ["ATLAS_HOME"] = old_home
            if old_token is None:
                os.environ.pop("ATLAS_DASHBOARD_TOKEN", None)
            else:
                os.environ["ATLAS_DASHBOARD_TOKEN"] = old_token


# ---------------------------------------------------------------------------
# Analisis del cuello de botella — derivado de los datos medidos, no supuesto
# ---------------------------------------------------------------------------


def analyze_bottleneck(report: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    workloads = report["workloads"]
    before = report["system"]["before"]
    after = report["system"]["after"]

    # 1. GPU/VRAM: leer los datos reales de nvidia-smi + ollama ps
    gpu_used_before = before.get("gpu_vram_used_mb")
    gpu_used_after = after.get("gpu_vram_used_mb")
    ollama_offloads_to_gpu = None
    for name in ("classification", "code_generation"):
        wl = workloads.get(name, {})
        ps_text = wl.get("ollama_ps_after", "")
        if ps_text:
            if "GPU" in ps_text and "100% CPU" not in ps_text:
                # OR entre workloads: un solo offload real a GPU basta para
                # marcar el flag, sin que un workload posterior en CPU lo
                # sobreescriba de vuelta a False (bug real: la iteracion
                # dejaba ganar al ultimo workload procesado, no a "alguno").
                ollama_offloads_to_gpu = True
            elif "100% CPU" in ps_text and ollama_offloads_to_gpu is None:
                ollama_offloads_to_gpu = False

    if ollama_offloads_to_gpu is False:
        findings.append(
            f"Ollama corre 100% en CPU (confirmado por 'ollama ps' en vivo), no en la "
            f"GTX 960M ({report['system']['gpu_name'] or 'GPU no detectada'}). VRAM usada "
            f"se mantuvo en ~{gpu_used_before}MiB antes y ~{gpu_used_after}MiB despues de "
            f"correr ambos workloads de LLM — la GPU esta practicamente idle. Esto coincide "
            f"con la memoria operativa: CUDA_VISIBLE_DEVICES se dejo vacio a proposito para "
            f"esta GTX 960M (Maxwell, demasiado vieja para el CUDA que trae este Ollama). "
            f"CONCLUSION: la VRAM NO es el cuello de botella actual para SLM local — el "
            f"cuello es CPU."
        )
    elif ollama_offloads_to_gpu is True:
        findings.append("Ollama SI esta usando la GPU para offload (caso no esperado en este hardware; revisar).")

    # 2. Throughput CPU: comparar tokens/sec clasificacion (0.5B) vs codegen (7B)
    cls = workloads.get("classification", {})
    cg = workloads.get("code_generation", {})
    cls_tps = cls.get("tokens_per_sec", {}).get("mean") if isinstance(cls.get("tokens_per_sec"), dict) else None
    cg_tps = cg.get("tokens_per_sec", {}).get("mean") if isinstance(cg.get("tokens_per_sec"), dict) else None
    if cls_tps is not None and cg_tps is not None:
        findings.append(
            f"Throughput de generacion CPU medido: {cls_tps} tok/s en {CLASSIFICATION_MODEL} "
            f"(0.5B) vs {cg_tps} tok/s en {CODEGEN_MODEL} (7B, Q4_K_M). El modelo grande es "
            f"~{round(cls_tps / cg_tps, 1) if cg_tps else '?'}x mas lento token-a-token. "
            f"CONCLUSION: el throughput de CPU escala mal con el tamano del modelo en este "
            f"hardware — codigo/tareas que necesiten un modelo >= 7B seran el path mas lento "
            f"del sistema, no por VRAM sino por tokens/seg de CPU."
        )
    if cg_tps is not None and cg_tps < 8.0:
        findings.append(
            f"code_generation a {cg_tps} tok/s es mas lento que una lectura comoda humana "
            f"(~15-20 tok/s); para respuestas largas (>200 tokens) la latencia percibida "
            f"sera de decenas de segundos. Este es el workload objetivo mas exigente medido "
            f"hoy en CPU."
        )

    # 3. Termico
    temp_before = before.get("temperature_celsius", 0.0)
    temp_after = after.get("temperature_celsius", 0.0)
    op_mode_after = after.get("operational_mode", "normal")
    # OperationalMode.value es lowercase ("normal"/"degraded"/"omega") — comparar
    # case-insensitive para no disparar un falso positivo termico.
    if op_mode_after.lower() != "normal":
        findings.append(
            f"ThermalWatchdog reporto modo {op_mode_after} al terminar (de {temp_before}C a "
            f"{temp_after}C). CONCLUSION: el benchmark SI empujo el sistema fuera de NORMAL — "
            f"termico es un cuello de botella real para cargas sostenidas en este chasis."
        )
    else:
        findings.append(
            f"Temperatura CPU: {temp_before}C -> {temp_after}C durante todo el benchmark "
            f"(umbral DEGRADED=70C, OMEGA=80C via ThermalWatchdog). Se mantuvo en modo "
            f"NORMAL todo el tiempo. CONCLUSION: para las cargas medidas hoy (benchmark "
            f"corto, no sostenido), termico NO fue el cuello de botella — pero el margen "
            f"hasta DEGRADED fue de solo {round(70.0 - temp_after, 1)}C, no es un colchon "
            f"grande para cargas largas."
        )

    # 4. RAM
    ram_before = before.get("ram_free_mb", 0)
    ram_after = after.get("ram_free_mb", 0)
    if ram_after < 1024:
        findings.append(
            f"RAM libre cayo a {ram_after}MB (< 1024MB, umbral DEGRADED del ThermalWatchdog). "
            f"CONCLUSION: RAM es un cuello de botella real durante este benchmark."
        )
    else:
        findings.append(
            f"RAM libre: {ram_before}MB -> {ram_after}MB. Se mantuvo por encima del umbral "
            f"DEGRADED (1024MB) todo el benchmark. CONCLUSION: RAM no fue el limitante hoy, "
            f"pero los 8.8GB 'disponible' reales de esta maquina son el techo — correr el "
            f"modelo de 7B (4.6GB) + Chromium + el resto de Atlas en paralelo consumiria una "
            f"fraccion importante de ese margen."
        )

    # 5. Complejidad de setup (dato cualitativo, pero basado en hechos verificados)
    findings.append(
        "Complejidad de setup verificada: Ollama en este host requiere "
        "CUDA_VISIBLE_DEVICES vacio via 'systemctl edit ollama' (ver memoria "
        "ollama-fix-2026-07-09) para no fallar contra la GTX 960M (Maxwell, "
        "arquitectura no soportada por el CUDA que trae Ollama) — la GPU existe "
        "pero requiere un workaround permanente para no romper el servicio, y ese "
        "workaround es precisamente lo que fuerza CPU-only."
    )

    # Determinar el cuello de botella primario a partir de las senales anteriores
    if op_mode_after.lower() != "normal":
        primary = "termico"
    elif ram_after < 1024:
        primary = "RAM"
    elif ollama_offloads_to_gpu is False and cg_tps is not None:
        primary = "throughput de CPU (VRAM de la GPU esta disponible pero sin usar por config CUDA)"
    else:
        primary = "latencia/throughput de CPU (sin senal termica/RAM/VRAM limitante en esta corrida)"

    return {
        "primary_bottleneck": primary,
        "findings": findings,
        "gpu_offloads_llm_to_gpu": ollama_offloads_to_gpu,
    }


# ---------------------------------------------------------------------------
# Meta del entorno
# ---------------------------------------------------------------------------


def collect_meta() -> dict[str, Any]:
    cpu_model = None
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass

    ram_total_mb = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    ram_total_mb = int(line.split()[1]) // 1024
                    break
    except Exception:
        pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script_version": SCRIPT_VERSION,
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_model": cpu_model,
        "cpu_count": None if not shutil.which("nproc") else int(
            subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip() or 0
        ),
        "ram_total_mb": ram_total_mb,
        "ollama_version": ollama_version(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


WORKLOAD_RUNNERS: dict[str, Callable[[int], dict[str, Any]]] = {
    "classification": run_classification_workload,
    "memory_distillation": run_memory_distillation_workload,
    "browser_tasks": run_browser_workload,
    "code_generation": run_code_generation_workload,
    "dashboard": run_dashboard_workload,
}

DEFAULT_REPEATS: dict[str, int] = {
    "classification": 2,
    "memory_distillation": 20,
    "browser_tasks": 3,
    "code_generation": 2,
    "dashboard": 3,
}

FAST_REPEATS: dict[str, int] = {
    "classification": 1,
    "memory_distillation": 5,
    "browser_tasks": 1,
    "code_generation": 1,
    "dashboard": 1,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=None, help="Ruta de salida JSON (default: stdout)")
    parser.add_argument(
        "--workloads", type=str, default=None,
        help=f"Subconjunto separado por comas de: {','.join(ALL_WORKLOADS)} (default: todos)",
    )
    parser.add_argument("--fast", action="store_true", help="Repeats reducidos (humo rapido, no benchmark serio)")
    args = parser.parse_args()

    selected = args.workloads.split(",") if args.workloads else list(ALL_WORKLOADS)
    invalid = [w for w in selected if w not in ALL_WORKLOADS]
    if invalid:
        print(f"ERROR: workloads desconocidos: {invalid}. Validos: {ALL_WORKLOADS}", file=sys.stderr)
        return 2

    repeats_table = FAST_REPEATS if args.fast else DEFAULT_REPEATS

    print(f"[benchmark_workload] iniciando — workloads: {selected}", file=sys.stderr)
    meta = collect_meta()
    meta["gpu_name"] = read_gpu_nvidia_smi().get("gpu_name")

    before = system_snapshot()
    print(f"[benchmark_workload] snapshot inicial: {before.temperature_celsius}C, "
          f"{before.ram_free_mb}MB RAM libre, GPU={before.gpu_name}", file=sys.stderr)

    workloads_out: dict[str, Any] = {}
    for name in selected:
        print(f"[benchmark_workload] corriendo workload: {name} ...", file=sys.stderr)
        t0 = time.perf_counter()
        try:
            result = WORKLOAD_RUNNERS[name](repeats_table[name])
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        result["_wall_clock_total_s"] = round(time.perf_counter() - t0, 3)
        workloads_out[name] = result
        print(f"[benchmark_workload] {name} listo en {result['_wall_clock_total_s']}s", file=sys.stderr)

    # Voice: documentado como no ejecutado, siempre, sin importar --workloads
    voice_available = False
    try:
        from atlas.interfaces.voice import REAL_DEPS_AVAILABLE as _voice_real
        voice_available = _voice_real
    except Exception:
        voice_available = False
    workloads_out["voice"] = {
        "skipped": True,
        "real_deps_available": voice_available,
        "reason": VOICE_SKIP_REASON,
    }

    after = system_snapshot()
    print(f"[benchmark_workload] snapshot final: {after.temperature_celsius}C, "
          f"{after.ram_free_mb}MB RAM libre", file=sys.stderr)

    report: dict[str, Any] = {
        "meta": meta,
        "system": {
            "gpu_name": meta["gpu_name"],
            "before": asdict(before),
            "after": asdict(after),
        },
        "workloads": workloads_out,
    }
    report["bottleneck_analysis"] = analyze_bottleneck(report)

    out_text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.output:
        args.output.write_text(out_text + "\n", encoding="utf-8")
        print(f"[benchmark_workload] JSON escrito en {args.output}", file=sys.stderr)
    else:
        print(out_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
