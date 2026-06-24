# Graveyard tech-4 — 2026-06-25 — PropertyVerifier (ADR-040 ext)

Cuarentena REVERSIBLE (git + aquí), NO borrado. Regla `wire-before-claim`.

## Módulo (en `orphan_modules/`)

| Módulo | Qué era | Por qué a cuarentena |
|---|---|---|
| `core/decider/property_verifier.py` | `PropertyVerifier` (ADR-040 ext): verificación estática de propiedades sobre un **string de código Python** (path containment, no import-side-effects, no risky imports, preservación Merkle/governance, no privilege escalation) vía análisis AST. Base para "proof-carrying patches". | **0 consumidores vivos** y, lo decisivo, **no existe el flujo que necesita**: su consumidor natural sería auto-codegen que produzca *source* Python → verificación estática antes del Allow del Decider. Hoy ese flujo NO existe (investigado 2026-06-25). |

## La investigación (decide-with-facts, 2026-06-25)

Se trazó el flujo real antes de decidir:
- `PropertyVerifier.verify(code: str)` necesita un **string de código Python** (AST-parseable).
- **ColdUpdateManager (ADR-025)** trabaja con **patches diff** (`.patch` + `git apply` + validación en
  worktree/sandbox), no con source AST-parseable. Cabecera literal: *"No hot self-patch; no autonomous
  code generation in MVP."*
- **`autonomous_decider.decide(action, intent, context)`** no recibe código: en su único call real
  (`cold_update_manager.py:366`) el `context` lleva `forensics`, no el patch. Es routing de anomalías.
- **El adopter** (`self_maintenance/adopter.py`) adopta `McpProposal` (servidores MCP), no código Python.

Conclusión: cablearlo ahora añadiría un verificador a un flujo inexistente — el mismo vapor que
`wire-before-claim` prohíbe. La defensa estática de patches es un diseño válido, pero **prematuro**.

## Cuándo RESCATARLO

Cuando exista un flujo vivo de **auto-codegen que produzca source Python** (no diffs) y haya un
chokepoint real donde verificarlo antes de aplicar/aprobar (p.ej. el adopter ADR-039 generando módulos,
o el `autonomous_decider` recibiendo el código en `context`). Ahí: mover de vuelta a `src/`, cablear al
chokepoint, y añadir el test de integración que demuestre que un patch que viola una propiedad es
rechazado.

## Estado

- Sin tests asociados (nunca tuvo) → no hay `orphan_tests/`.
- El módulo está sintáctica y type-check limpio (se reparó una corrupción de tokens antes de cuarentenarlo);
  queda listo para rescate directo.
