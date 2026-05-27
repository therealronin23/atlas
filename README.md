# Atlas Core

Runtime local soberano de inteligencia. Coordina modelos locales y APIs
gratuitas para alcanzar comportamiento de frontier sin depender de
ninguna SaaS. Atlas decide; el resto sirve a Atlas.

## Estado

- **Gate A — SEALED**: visión, entidades y principios fijados.
- **Gate B — COMPLETE**: core local funcional.
- **Gate C — COMPLETE** (tag `v0.2-gate-c`): Hermes-VPS desplegado en
  Hetzner CPX22 con Tailscale, REST + HMAC-SHA256 end-to-end.
- **Gate D — COMPLETE** (tag `v0.3-gate-d`): InferenceHub real (LiteLLM),
  KuzuDB vector + grafo, MemoryDistiller, capability tokens + AtlasExecutor,
  Time-Travel checkpoints, Ghost Replay cache, PII Surrogate, SLM Classifier,
  pipeline integrado en Orchestrator.
- **Gate E — COMPLETE** (tag `v0.4-gate-e`): ADR-002 sellado como bare metal +
  venv, dashboard web FastAPI/Jinja2 en localhost:7331, voz STT/TTS con
  extras opcionales.
- **Gate F — COMPLETE** (tag `v0.5-gate-f`): computer-use con Playwright
  (BrowserTool + EditorTool + VisionLoop), Merkle logging, Orchestrator routing
  con approval flow, ADR-013b resuelto.
- **Gate G — COMPLETE** (tag `v0.6-gate-g`): operacionalización local.
  Hermes-VPS restaurado y smoked, GitHub sincronizado, approvals persistentes
  por CLI, Telegram autorizado y smoked, runbook operacional.
- **Gate H — MVP COMPLETE** (tag `v0.7-gate-h`): H1–H6 audited synthesis,
  gate_h_smoke.py, `atlas gate-h` CLI.
- **Gate I — COMPLETE** (tag `v0.8-gate-i`): `atlas serve`, `atlas health`,
  `/api/health`, `AtlasServiceRunner`, systemd unit.
- **ADR-024 — Observability v2**: MVP sellado. TelemetryBus, MicroLedger,
  OperationalWAL, ObservabilityStack, Prometheus opt-in (`ATLAS_PROMETHEUS=1`),
  dashboard `/observability`.
- **ADR-025 — ColdUpdateManager**: MVP sellado + SelfAuditLoop. Worktree
  aislado, `atlas update propose|validate|approve|apply`, `atlas self-audit
  run|status|proposals|report|stop`. Ciclos fríos auditables sin hot-patch.
- **Auditoría completa 2026-05-25**: 564 core tests + 25 computer_use = 589
  total, mypy clean (62 source files), Hermes-VPS live, Telegram smoked,
  Prometheus operativo.
- **Versión actual**: `v0.9.0`

## Quick start

```bash
git clone git@github.com:therealronin23/atlas.git ~/proyectos/atlas-core
cd ~/proyectos/atlas-core

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configurar .env (ver .env.example)
cp .env.example .env
# Editar .env: pega tus GROQ_API_KEY, OPENROUTER_API_KEY,
# HERMES_BASE_URL/HERMES_API_KEY si tienes Hermes-VPS desplegado.

# Verificar que todo funciona
PYTHONPATH=src python -m pytest tests/ -q
MYPYPATH=src python -m mypy src/atlas/
```

## Comandos básicos

Tras `pip install -e ".[dev]"` queda disponible el binario `atlas`:

```bash
atlas status                              # estado global del core
atlas task "git status"                   # procesar una intención
atlas task "lista los archivos"           # otra intención
atlas memory --layer system_context       # inspeccionar memoria
atlas memory --layer error_registry
atlas memory --layer approved_patterns
atlas audit --tail 20                     # audit log
atlas audit --verify                      # verificar integridad de la cadena
atlas tools                               # listar tool registry
atlas tools --level L1
atlas health                              # health check del servicio
atlas gate-h                              # validación Gate H
atlas self-audit run --hours 1 --profile quick  # ciclo de auto-auditoría
atlas update propose|validate|approve|apply      # cold update workflow
```

Equivalente sin instalar entry-point: `PYTHONPATH=src python -m atlas.interfaces.cli <cmd>`.

Ver [docs/USAGE.md](docs/USAGE.md) para guía detallada de operación.

## Activar el pipeline Gate D

El pipeline integrado (ghost replay → hybrid classifier → distiller +
PII + InferenceHub → time-travel) está **opt-in**:

```bash
# Vía env var
ATLAS_PIPELINE_GATE_D=1 atlas task "..."

# Vía código
from atlas.core.orchestrator import Orchestrator
from atlas.core.inference_hub import InferenceHub

orch = Orchestrator()
orch.enable_gate_d_pipeline(inference_hub=InferenceHub(mode="auto"))
task = orch.handle_intent("explicame que es un Merkle tree")
# task.tool_name == "inference_hub.complete"
# task.result["text"] == "<respuesta real de Groq>"
```

## Observability + Prometheus

La observabilidad v2 (ADR-024) está disponible vía env var:

```bash
ATLAS_PROMETHEUS=1 atlas serve  # habilita /metrics endpoint

# En otra terminal:
curl http://localhost:7331/metrics

# Dashboard de observabilidad:
curl http://localhost:7331/api/observability
```

Ver `docs/prometheus_setup.md` para guía de deploy de Prometheus + Grafana.

## Smoke tests reales (infra viva)

```bash
# Hermes-VPS (REST + HMAC sobre Tailscale)
set -a && source .env && set +a
PYTHONPATH=src python scripts/hermes_smoke.py

# InferenceHub por proveedor (Groq + OpenRouter)
PYTHONPATH=src python scripts/inference_smoke.py

# Pipeline Gate D end-to-end (5 intents, cubre cada bifurcación)
PYTHONPATH=src python scripts/pipeline_smoke.py

# Gate H smoke (síntesis auditada)
PYTHONPATH=src python scripts/gate_h_smoke.py

# Gate I smoke (service runner + health)
PYTHONPATH=src python scripts/gate_i_smoke.py

# Operacional completo (Hermes + CLI approvals + Telegram)
PYTHONPATH=src python scripts/operational_smoke.py
```

## Arquitectura mínima

```
intent → Orchestrator.handle_intent
            ├─ GhostReplay.lookup (cache topológica)
            ├─ Classifier (regex deterministic, microsegundos)
            ├─ SLMClassifier (LiteLLM, solo si rule confianza < 1.0)
            ├─ route: block | delegate | approve | execute
            ├─ Execute:
            │    ├─ DETERMINISTIC_TOOL → git/fs/atlas tools
            │    └─ LOCAL_SAFE → MemoryDistiller + PIISurrogate + InferenceHub
            ├─ GhostReplay.record
            └─ TimeTravel snapshot

Todo logueado en MerkleLogger (cadena SHA-256 inmutable).
Todo IO con efecto externo va por capability tokens (AtlasExecutor).
```

## Documentación

- [AGENTS.md](AGENTS.md) — contexto completo del proyecto (estado de gates,
  ADRs, naming rules, coding rules, estructura de proyecto).
- [CLAUDE.md](CLAUDE.md) — contexto para Claude Code (sincronizado con AGENTS.md).
- [docs/USAGE.md](docs/USAGE.md) — guía de operación detallada,
  configuración, troubleshooting.
- [docs/auditoria_final_postmortem.md](docs/auditoria_final_postmortem.md) —
  auditoría completa + postmortem técnico (verificación independiente).
- [docs/AUDIT_COMPLETO_2026-05-25.md](docs/AUDIT_COMPLETO_2026-05-25.md) —
  auditoría técnica de 8 partes (arquitectura, seguridad, tests, rendimiento).
- [docs/prometheus_setup.md](docs/prometheus_setup.md) — guía operacional
  Prometheus + alertas + Grafana.
- [docs/gate_c_seal.md](docs/gate_c_seal.md) — evidencia cierre Gate C.
- [docs/gate_d_seal.md](docs/gate_d_seal.md) — evidencia cierre Gate D.
- [docs/gate_e_seal.md](docs/gate_e_seal.md) — evidencia cierre Gate E.
- [docs/gate_f_seal.md](docs/gate_f_seal.md) — evidencia cierre Gate F.
- [docs/gate_g_seal.md](docs/gate_g_seal.md) — evidencia cierre Gate G.
- [docs/gate_h_seal.md](docs/gate_h_seal.md) — evidencia cierre Gate H.
- [docs/gate_i_seal.md](docs/gate_i_seal.md) — evidencia cierre Gate I.
- [memory/system_context/](memory/system_context/) — visión, reglas y
  ADRs canónicos.

## Filosofía (3 frases)

1. Atlas es soberano local. No SaaS, no llamadas a Claude/OpenAI como
   dependencia de runtime.
2. Cada efecto externo queda en el MerkleLogger; cada acción no
   determinista va por capability + executor.
3. Free tiers oportunistas: Groq, OpenRouter, Gemini, Together. Si
   todos fallan, Hermes-VPS o L0 local.