# Atlas Core

Runtime local soberano de inteligencia. Coordina modelos locales y APIs
gratuitas para alcanzar comportamiento de frontier sin depender de
ninguna SaaS. Atlas decide; el resto sirve a Atlas.

## Estado

**Gates A–I (fundaciones históricas)**: sellados en tags v0.2–v0.8 (vision → local core → inference → dashboard/voice → computer-use → operational service → synthesis → health endpoints). Incluyen ADRs de observability y cold updates. El estado vivo se consulta con `atlas reality` (versión, git SHA, checks, browser, Hermes, LLM, MCP, Merkle y freshness de docs).

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
PYTHONPATH=src atlas reality
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
atlas reality                            # estado factual, sin claims heredados
atlas capabilities                       # plano de capacidades y evidencia
atlas security-audit src/atlas           # auditoría estática defensiva Python
atlas gate-h                              # validación Gate H
atlas self-audit run --hours 1 --profile quick  # ciclo de auto-auditoría
atlas update propose|validate|approve|apply      # cold update workflow
```

Equivalente sin instalar entry-point: `PYTHONPATH=src python -m atlas.interfaces.cli <cmd>`.

Ver [docs/reference/USAGE.md](docs/reference/USAGE.md) para guía detallada de operación.

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

Ver `docs/reference/prometheus_setup.md` para guía de deploy de Prometheus + Grafana.

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
- [docs/reference/USAGE.md](docs/reference/USAGE.md) — guía de operación detallada,
  configuración, troubleshooting.
- [docs/governance/gates/CLOSURE.md](docs/governance/gates/CLOSURE.md) — cierre/roll-up de
  los Gates A–I (históricos, sellados; el proyecto pivotó a Osmosis).
- [docs/governance/audits/](docs/governance/audits/) — auditorías y postmortems técnicos
  (incluye `audit_postmortem_memory_substrate_2026-06-21.md` y los self-audits diarios).
- [docs/reference/prometheus_setup.md](docs/reference/prometheus_setup.md) — guía operacional
  Prometheus + alertas + Grafana.
- [docs/governance/gates/gate_c_seal.md](docs/governance/gates/gate_c_seal.md) — evidencia cierre Gate C.
- [docs/governance/gates/gate_d_seal.md](docs/governance/gates/gate_d_seal.md) — evidencia cierre Gate D.
- [docs/governance/gates/gate_e_seal.md](docs/governance/gates/gate_e_seal.md) — evidencia cierre Gate E.
- [docs/governance/gates/gate_f_seal.md](docs/governance/gates/gate_f_seal.md) — evidencia cierre Gate F.
- [docs/governance/gates/gate_g_seal.md](docs/governance/gates/gate_g_seal.md) — evidencia cierre Gate G.
- [docs/governance/gates/gate_h_seal.md](docs/governance/gates/gate_h_seal.md) — evidencia cierre Gate H.
- [docs/governance/gates/gate_i_seal.md](docs/governance/gates/gate_i_seal.md) — evidencia cierre Gate I.
- [memory/system_context/](memory/system_context/) — visión, reglas y
  ADRs canónicos.

## Filosofía (3 frases)

1. Atlas es soberano local. No SaaS, no llamadas a Claude/OpenAI como
   dependencia de runtime.
2. Cada efecto externo queda en el MerkleLogger; cada acción no
   determinista va por capability + executor.
3. Free tiers oportunistas: Groq, OpenRouter, Gemini, Together. Si
   todos fallan, Hermes-VPS o L0 local.
