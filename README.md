# Atlas Core

Runtime local soberano de inteligencia. Coordina modelos locales y APIs
gratuitas para alcanzar comportamiento de frontier sin depender de
ninguna SaaS. Atlas decide; el resto sirve a Atlas.

## Estado

- **Gate A — SEALED**: visión, entidades y principios fijados.
- **Gate B — COMPLETE**: core local funcional.
- **Gate C — COMPLETE** (tag `v0.2-gate-c`): Hermes-VPS desplegado en
  Hetzner CPX22 con Tailscale, REST + HMAC-SHA256 end-to-end.
- **Gate D — COMPLETE** (tag `v0.3-gate-d`, 368 tests verdes):
  InferenceHub real (LiteLLM), KuzuDB vector + grafo, MemoryDistiller,
  capability tokens + AtlasExecutor, Time-Travel checkpoints, Ghost
  Replay cache, PII Surrogate, SLM Classifier, pipeline integrado en
  Orchestrator.
- **Gate E — COMPLETE** (tag `v0.4-gate-e`, 449 tests verdes):
  ADR-002 sellado como bare metal + venv, dashboard web FastAPI/Jinja2
  en localhost:7331, voz STT/TTS con extras opcionales.
- **Gate F — IN PROGRESS**: computer-use con Playwright y herramienta de
  editor ya existen con tests; falta hardening completo vía capabilities,
  MerkleLogger y approval flow antes de cerrar el Gate.

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
# Estado local auditado: 494 tests verdes, mypy sobre 42 source files.
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

## Smoke tests reales (infra viva)

```bash
# Hermes-VPS (REST + HMAC sobre Tailscale)
set -a && source .env && set +a
PYTHONPATH=src python scripts/hermes_smoke.py

# InferenceHub por proveedor (Groq + OpenRouter)
PYTHONPATH=src python scripts/inference_smoke.py

# Pipeline Gate D end-to-end (5 intents, cubre cada bifurcación)
PYTHONPATH=src python scripts/pipeline_smoke.py
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

- [CLAUDE.md](CLAUDE.md) — contexto del proyecto para sesiones con
  Claude Code (estado de gates, ADRs, naming rules, coding rules).
- [docs/USAGE.md](docs/USAGE.md) — guía de operación detallada,
  configuración, troubleshooting.
- [docs/absorption_master_plan.md](docs/absorption_master_plan.md) —
  plan limpio de investigación/forking selectivo.
- [docs/gate_f_plan.md](docs/gate_f_plan.md) — alcance y criterios de
  cierre de Gate F.
- [docs/gate_f_real_world_readiness.md](docs/gate_f_real_world_readiness.md) —
  checklist de host real para Gate F.
- [docs/atlas_box_architecture.md](docs/atlas_box_architecture.md) —
  notas de arquitectura hardware/topología.
- [docs/fleet_security_plan.md](docs/fleet_security_plan.md) —
  plan futuro para nodos Atlas distribuidos.
- [docs/product_strategy_notes.md](docs/product_strategy_notes.md) —
  notas no legales de posicionamiento y producto.
- [docs/gate_c_seal.md](docs/gate_c_seal.md) — evidencia cierre Gate C.
- [docs/gate_d_seal.md](docs/gate_d_seal.md) — evidencia cierre Gate D.
- [docs/gate_e_seal.md](docs/gate_e_seal.md) — evidencia cierre Gate E.
- [memory/system_context/](memory/system_context/) — visión, reglas y
  ADRs canónicos.

## Filosofía (3 frases)

1. Atlas es soberano local. No SaaS, no llamadas a Claude/OpenAI como
   dependencia de runtime.
2. Cada efecto externo queda en el MerkleLogger; cada acción no
   determinista va por capability + executor.
3. Free tiers oportunistas: Groq, OpenRouter, Gemini, Together. Si
   todos fallan, Hermes-VPS o L0 local.
