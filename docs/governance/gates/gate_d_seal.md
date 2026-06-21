# Gate D — Seal

**Fecha:** 2026-05-24
**Estado:** COMPLETE
**Tests:** 347/347 passing
**mypy:** verde en 38 archivos fuente
**Tag:** `v0.3-gate-d`

## Resumen

Gate D cierra con la pila de inteligencia real montada: inferencia con
proveedores externos via LiteLLM, memoria vectorial + grafo embedded,
compresion semantica de contexto, capability tokens para seguridad
estructural, sustitucion de PII determinista, time-travel debugging
con checkpoints encadenados, ghost replay cache topologico y
clasificacion SLM-based.

La filosofia se mantiene intacta:
- Atlas sigue siendo el soberano local (ADR-000).
- Cada efecto externo pasa por MerkleLogger (cadena hash continua).
- Cada accion no determinista va por capability + executor (ADR-020).
- Cada respuesta externa puede ser cacheada (ADR-022) y los datos
  sensibles sustituidos (ADR-023) antes de salir.

Quedan documentados como **follow-up explicito** los cableos
automaticos en el pipeline (`Orchestrator.handle_intent` consumiendo
distiller + ghost_replay + slm_classifier + timetravel). Las piezas
estan, la integracion completa entra en proximo gate.

## Modulos entregados

| ADR | Modulo | Tests |
|---|---|---|
| ADR-016 | `src/atlas/core/inference_hub.py` (LiteLLM) | 9 |
| ADR-020 | `src/atlas/security/{capabilities,executor}.py` | 31 + 5 integ |
| ADR-008 | `src/atlas/memory/{embeddings,vector_store}.py` | 34 + 7 integ |
| ADR-018 | `src/atlas/memory/distiller.py` | 17 |
| ADR-023 | `src/atlas/security/pii_surrogate.py` | 33 |
| ADR-021 | `src/atlas/core/{checkpoint,timetravel}.py` | 22 |
| ADR-022 | `src/atlas/core/ghost_replay.py` | 21 |
| ADR-010 | `src/atlas/router/slm_classifier.py` | 21 |

Total nuevos en Gate D: **200 tests** (de 147 baseline al cerrar Gate C
hasta 347 al cerrar Gate D).

## Subgates Gate D

| Sub | Resultado |
|---|---|
| D1 InferenceHub real | DONE. Modo auto/live/stub. Fallback chain Groq -> OpenRouter -> Together -> Gemini -> L0. Cooldown rate-limit 60s. Smoke real PASS contra 4 proveedores. |
| D2 SLM classifier | DONE. Wrapper sobre InferenceHub con prompt estructurado, parseo JSON robusto, cache opcional via GhostReplay. Complementa al rule-based, no lo sustituye. |
| D3 Capability tokens + AtlasExecutor | DONE. Tokens frozen (Read/Write/Network/Exec). Issuer valida contra PermissionProfile + SSRFBridge. Executor canaliza IO con audit log. Integrado en Orchestrator via properties. |
| D4 KuzuDB vector + graph memory | DONE. StubEmbedder + LiteLLMEmbedder. Schema Pattern/Failure/Evidence + REL tables. ErrorRegistry y ApprovedPatternStore aceptan vector_store opcional (mirror automatico + find_similar). |
| MemoryDistiller | DONE. Compresion pre-LLM por relevancia con budget de tokens. System chunks intocables, recent al final, scorables filtrados. Hook con KuzuVectorStore. |
| D5 Time-Travel + Ghost Replay | DONE. Time-Travel con checkpoints encadenados por hash + fork counterfactual + verify_chain. Ghost Replay con TTL + LRU + purge para presion de memoria. |
| D6 PII Surrogate | DONE. Deteccion regex (email, DNI ES, IBAN, telefono ES, IPv4/v6, API keys) + sustitucion determinista que preserva formato. Salt configurable. Redact + restore roundtrip. |
| D7 Cierre + tag | DONE (este documento + tag `v0.3-gate-d`). |

## ADRs cerrados o reconfirmados por Gate D

- **ADR-008** Vector + graph memory: KuzuDB — RESUELTO (implementado).
- **ADR-010** SLM classifier — RESUELTO (apoyado en LiteLLM, sin SLM
  local hardcoded).
- **ADR-016** InferenceHub: LiteLLM — RECONFIRMADO en operacion real.
- **ADR-018** Memory Distiller — RESUELTO v1 (determinista, sin LLM
  secundario).
- **ADR-020** Capability tokens — RESUELTO.
- **ADR-021** Time-Travel — RESUELTO.
- **ADR-022** Ghost Replay — RESUELTO.
- **ADR-023** PII Surrogate — RESUELTO v1 (regex + pools; SLM-based v2
  diferido).

## Lo que NO se hizo en Gate D (consciente)

- **Integracion automatica de las nuevas piezas en `Orchestrator.handle_intent`**:
  capability_issuer/executor, ghost_replay, distiller, slm_classifier y
  timetravel estan expuestos pero el pipeline existente sigue usando
  IO crudo y el rule-based classifier. La migracion del pipeline es
  el primer follow-up post-Gate D.
- **Sandbox OMEGA real (Proxmox)**: sigue en stub, depende de ADR-002
  abierto. Es responsabilidad de Gate E.
- **PII Surrogate v2 con SLM**: nombres, ciudades, direcciones — la
  pieza v1 funciona con regex; ampliar requiere modelo local o nueva
  llamada al InferenceHub.
- **Memoria sync Hermes <-> Atlas Core** (ADR-012): la decision esta
  tomada (pull-on-reconnect) pero el codigo no se ha escrito.

## Verificacion en cierre

```
$ source .venv/bin/activate
$ PYTHONPATH=src python -m pytest tests/ -q
347 passed in ~16s

$ MYPYPATH=src python -m mypy src/atlas/
Success: no issues found in 38 source files

$ git log --oneline --since="2026-05-23 00:00"
<commits del periodo Gate C close -> Gate D close>
```

## Siguiente

Gate E — Entorno local definitivo:
- ADR-002: decision Proxmox VE vs alternativas tras experimentos en el
  HP Omen.
- E1: instalacion Proxmox y migracion del Atlas Core local.
- E2: Dashboard de telemetria.
- E3: Voz (Whisper + Piper) — ADR-003.

Antes de Gate E, idealmente: cableo automatico en Orchestrator de las
piezas Gate D (consume distiller antes de cada inferencia, ghost
replay como pre-check, slm_classifier en cascada con el rule-based,
timetravel grabando checkpoints en cada handle_intent).
