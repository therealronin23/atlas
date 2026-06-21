# Inventario de lo construido — 2026-06-14

Foto de lo que **existe y funciona** (no lo que falta — eso en `backlog.md` y el
roadmap). Estado vivo real siempre por `atlas reality --json`; esto es el mapa
estructural. ~28 ADRs (013b–048), ~14 paquetes en `src/atlas`, 90 ficheros de
test (~1174 tests), mypy limpio (121 ficheros).

## 0. Base defensiva — "sellada" (dirección 2026-06-12)

- **ADR-034** endurecimiento de subprocess → `security/process_hardening.py`.
- **ADR-036** modelo de amenazas + hoja de murallas.
- **ADR-037** frontera de contenido no confiable (muralla P0).
- **ADR-038** gate de adopción "Atlas Sentinel" → `security/sentinel_gate.py`.
- `security/ssrf_bridge.py` (gateo de egress), `security/sandbox.py`
  (`LayeredIsolationSandbox`), `security/writer_lock.py` (`MerkleWriterLock`,
  escritor único de la cadena Merkle).

## 1. Las 4 capas — el constructor verificable

- **Capa 1 — Verificador universal (ADR-041)** `core/verify.py`:
  `verify(artifact) → Evidence`, regla asimétrica, `UnifiedDiffVerifier`,
  `StaticCodeVerifier`, `OutputShapeVerifier`, `SandboxRunVerifier`,
  `UniversalVerifier`. Tiers de coste ordinales.
- **Capa 2 — Cascada con routing (ADR-042)** `router/cascade.py`: routing por
  dificultad/verificabilidad, `CostLedger`, productores; cableada al codegen con
  evidencia en Merkle. `router/slm_classifier.py`.
- **Capa 3 — Enjambre (ADR-045/046/048)**: `core/swarm.py` (blackboard,
  coordinador, envelopes), `core/swarm_backend.py` (worktree workers),
  `core/swarm_cycle.py` + `core/swarm_validate.py` + `core/swarm_reconcile.py`
  (ciclo vivo, propuesta-solo), `core/verified_producer.py` (lazo cerrado),
  `core/deterministic_producer.py` (arnés), `core/llm_producer.py`,
  `core/maintenance_scout.py` + `core/maintenance_worker.py`,
  `core/adversarial_panel.py` (ADR-047 pieza 1). **Vivo y gated**:
  `ATLAS_SWARM_SCHEDULER`.
- **Capa 4 — LessonStore (ADR-044)**: núcleo verificable (sin consumidores aún).

## 2. Autonomía gobernada

- **ADR-040** decisor central human-ON-the-loop: `AutonomousDecider`
  (invariantes deterministas: IOC→Deny, sensitivity=high→Deny, sin anclaje de
  intención→Deny, sin undo→Deny), `HumanDecider`, híbrido. `ATLAS_DECIDER`.
- **ADR-025** `core/cold_update_manager.py`: intake de patch → worktree aislado
  → validate (pytest+mypy) → approve → apply con rollback; orígenes
  manual/self_audit/swarm.
- **ADR-039** agente de auto-mantenimiento: scouts (registry/dep), analyst
  dual-LLM + gate de corroboración, proposer, adopter, `MaintenanceScheduler`
  (cron + dep-cycle). En `core/self_maintenance/`.
- **Self-audit 24h** `core/self_audit.py` + `core/patch_generator.py`: bucle
  perpetuo dentro de `serve` (escritor único). `ATLAS_SELF_AUDIT_SCHEDULER`.

## 3. Inferencia y razonamiento

- **ADR-016** InferenceHub (LiteLLM, cadena de fallback Groq→OpenRouter→
  Together→Gemini→local). `ATLAS_INFERENCE_MODE`.
- **ADR-031/032/033** loop agéntico de tool-calls (tools mutantes con HITL
  inline, suspendible, barrido de TTL).
- **ADR-019** framework de validación estadística.

## 4. Memoria

- `core/memory/` + `_workspace/memory/`: **ADR-030** block memory (Letta/MemGPT),
  `KuzuVectorStore` (vector), `error_registry`, `approved_patterns`,
  `checkpoints`, `ghost_cache`, `system_context`, `blocks`.
- **ADR-029** búsqueda full-text de auditoría + reverse twin audit.

## 5. Observabilidad y auditoría

- **ADR-024** observability v2: `logging/` (`merkle_logger`, `microledger`,
  `observability`, `telemetry_bus`, `operational_wal`). Cadena Merkle como
  registro de auditoría inmutable.
- `monitoring/prometheus_exporter.py` (`ATLAS_PROMETHEUS`).
- `thermal/` watchdog (`ATLAS_THERMAL_MONITOR`).

## 6. Interfaces y twin

- `interfaces/`: `cli.py` (con lock de escritor), `dashboard.py`
  (`ATLAS_SERVE_DASHBOARD`), `telegram_bot.py`, `exec_api.py` (**ADR-027**
  `/api/exec/intent`).
- **ADR-026** twin Atlas+Hermes-Agent + **ADR-028** kanban bridge (Hermes VPS
  dado de baja 2026-06-11 → modo local: `ATLAS_HERMES_LOCAL`).
- **ADR-035** cliente MCP (`mcp/`). **ADR-013b** computer-use (`lab/`, `tools/`).

## 7. Runtime

- `runtime/service_runner.py` (Gate I): `AtlasServiceRunner` 24/7 — offline
  monitor, alertas operacionales, y los daemons gated (dashboard, prometheus,
  thermal, maintenance, self-audit, **swarm**). Arranque por `atlas reality
  --strict`.

## Verticales propuestas (diseño, sin código)

- **ADR-043** autorización verificable + `SECURITY_FINDING` (vertical ofensiva).
- **ADR-047** verificación adversarial + grounding de dominio + asistencia al
  verificador (pieza 1, `AdversarialPanel`, ya construida).
