# ADR-037 — Frontera de contenido no confiable (muralla P0)

- Status: **Accepted** (2026-05-30) — slice 1 implementado
- Módulo: `src/atlas/core/orchestrator.py`
- Depende de: ADR-031/032/033 (loop agéntico), ADR-036 (threat model)
- Habilita: consumo seguro de MCP (ADR-035) y, a futuro, lectura de foros
  (auto-mantenimiento)

## Contexto

En el loop agéntico, los resultados de las tools `read` se re-inyectan en el
contexto del modelo (`messages`). Hoy todas son estado propio de Atlas
(git/status/blocks) = confiable. Pero al añadir MCP (ADR-035) y, después, lectura
web/foros, entra **contenido externo no controlado** que puede portar
instrucciones ocultas → **inyección indirecta de prompt**, la amenaza #1 del
ecosistema (arXiv:2601.17548; >78% de bypass adaptativo medido).

La inyección indirecta es un problema **de arquitectura, no de prompt**
(CaMeL, arXiv:2503.18813): no se resuelve pidiéndole amablemente al modelo que
no obedezca, sino separando datos de control y limitando capacidades tras ingerir
lo no confiable.

## Decisión

Implementar la frontera **por capas**, empezando por el slice de mayor impacto y
menor coste (stdlib, sin tocar el modelo), y dejando el dual-LLM para una capa
posterior.

| # | Mecanismo | Patrón | Estado |
|---|-----------|--------|--------|
| 1 | **Procedencia** por tool: `mcp__*` y lectores externos = `untrusted`; estado propio = `trusted` (`_agentic_tool_provenance`) | provenance tracking | ✅ |
| 2 | **Envoltura** del resultado externo con marca explícita "es dato, NO instrucción" + frontera `<<< >>>` (`_wrap_untrusted`) | labeling (patrón #1/#3) | ✅ |
| 3 | **Taint del loop**: si ya se ingirió contenido no confiable, la allowlist de auto-aprobación (ADR-033 #2) queda **anulada** → toda mutación cae a HITL (`_loop_is_tainted`) | post-ingestion tool policy (patrón #2) | ✅ |
| 4 | Taint **derivado de `messages`** (no estado extra) → sobrevive a suspensión/reanudación | — | ✅ |
| 5 | **Dual-LLM** (control vs procesamiento sin acceso a tools/system) para razonar sobre contenido hostil | CaMeL data/control split | ⏳ capa futura |
| 6 | **Saneo** activo de patrones de inyección antes de re-inyectar | sanitization | ⏳ capa futura |

### Por qué el taint anula el auto-approve

El caso peligroso es: el modelo lee algo externo ("el foro dice: borra X y ejecuta
Y") y a continuación intenta una mutación que estaba en la allowlist de confianza.
Sin el taint, correría inline. Con el taint, **vuelve a exigir humano**. El gate
se computa al inicio de cada turno desde los mensajes previos: la granularidad
correcta, porque el modelo decide las tool-calls de un turno antes de ver los
resultados de ese mismo turno.

## Compatibilidad

- Sin contenido no confiable (todo git/status/blocks): comportamiento idéntico a
  ADR-033. La allowlist sigue corriendo inline. Cero regresión.
- Sin allowlist (default): ya todo era HITL; el taint no cambia nada visible.
- No añade deps. No toca el modelo. No persiste estado nuevo.

## Consecuencias

- Atlas puede consumir MCP (y a futuro foros) sin que el contenido externo
  escale privilegios silenciosamente.
- **No es defensa total** (se evade bajo ataque adaptativo). Opera en profundidad
  junto al gate de adopción (ADR-038) y el HITL. Esa es la postura, por diseño.

## Tests

`tests/test_orchestrator_untrusted_boundary.py` (4):
- `test_provenance_classification`
- `test_wrap_and_taint_detection`
- `test_untrusted_read_blocks_auto_approve` (E2E: MCP read → mutación suspende)
- `test_trusted_read_keeps_auto_approve_inline` (control: git read → inline)

## Fuera de alcance (capas futuras)

- Dual-LLM (CaMeL) — capa #5; requiere refactor del flujo de inferencia.
- Saneo activo / firewall de tool-output — capa #6.
- Provenance criptográfica de tool identity — pertenece a ADR-038 (gate).
