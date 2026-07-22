<!-- GENERADO por atlas handoff 2026-07-22T19:57:27.068581+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

---
status: vigente
fecha: 2026-07-15
---

# Actor Roles — quién es quién cuando un modelo trabaja sobre Atlas

`WORK_LEDGER.md`, `docs/continuation/` y las memorias nombran actores
("Fable", "Sonnet", "Opus") sin definirlos en ningún sitio central. Este doc
es esa definición. Motivo: **sucesión de modelo** — los modelos SOTA entran y
salen como proveedores; la inteligencia de Atlas vive en el sustrato
(memoria, ledger, grafo, gates, misiones), no en el driver de turno. Cualquier
modelo que lea esto debe poder operar Atlas siguiendo `AGENTS.md` sin conocer
a sus predecesores.

## Los actores

| Actor | Qué es | Rol en Atlas |
| --- | --- | --- |
| **Fable** (Fable 5) | Modelo frontier de Anthropic (Claude), driver principal de las sesiones interactivas en 2026-07 | Solo criterio: diseño, auditoría de diffs, reconciliación, decisiones, commits. NO implementa a mano lo delegable |
| **Sonnet** (Claude Sonnet) | Modelo medio de Anthropic, más barato que Fable/Opus | Implementa y revisa: tareas sustanciales con TDD, exploración de código, informes. Subagente típico del harness y de `/autobuild` |
| **Haiku** (Claude Haiku) | Modelo pequeño de Anthropic, el más barato | Lo mecánico: renames, formato, edits de una línea, comandos de verificación |
| **Opus** (Claude Opus) | Modelo grande de Anthropic, caro | Planificación y auditoría en el lazo `/autobuild` (planner/auditor); veredictos de calidad sobre diff agregado |
| **GPT / Codex / Gemini / etc.** | Modelos de otros proveedores | Sustituibles en cualquier rol si el proveedor está en la cadena verificada del InferenceHub; mismas reglas de `AGENTS.md` |

"Fable"/"Sonnet"/"Opus" en el ledger y las memorias = el modelo que condujo
esa sesión, no un componente de Atlas. Atlas ≠ ninguno de ellos.

## Política de delegación (operador, 2026-07-15 — permanente)

> Fable solo criterio; Sonnet implementa; Haiku lo mecánico.

Reglas operativas (fuente: memoria `feedback-delegate-to-cheaper-models.md`):

1. El modelo caro de la sesión (hoy Fable) NO implementa: diseña el prompt
   autocontenido, audita el diff del subagente y commitea.
2. Los prompts de subagente son autocontenidos (rutas absolutas, contexto
   completo): los subagentes del harness NO heredan MCP ni hooks (límite
   conocido, memoria 2026-07-03).
3. No delegar colas cortas: si la tarea es más corta que escribir el prompt,
   se hace directamente.
4. Un commit por fase; ledger + design note + memoria en el mismo commit
   (`AGENTS.md` OPERATING LOOP §6).

## Sucesión: qué hace un modelo nuevo en frío

1. Sigue `AGENTS.md` (el protocolo vigente; `docs/continuation/
   NEXT_AI_INSTRUCTIONS.md` está SUPERSEDED como protocolo, es histórico
   F15/F16).
2. `atlas reality --json` → grafo (MCP trunk) → `WORK_LEDGER.md` →
   `docs/design/atlas_ecosystem_map.md` → design doc del nodo activo.
3. Los invariantes de `AGENTS.md` (governance.json intocable, no push, no
   `git add -A`, aprobación humana en sensitivity=high) aplican a CUALQUIER
   modelo, en cualquier rol.
4. Para cambios de autoconstrucción usa la ruta dorada (`GoldenRoute`,
   ADR-069): aprobación humana registrada en Merkle antes de actuar — nunca
   edición directa fuera de ceremonia para lo que la ruta cubre.

