# PROPUESTA — APLICADA 2026-07-23 — notificación F2.6 en AGENTS.md

**Estado: APLICADA.** El operador aceptó esta propuesta el 2026-07-23 y el diff de
abajo ya está en `AGENTS.md` §OPERATING LOOP (paso 1b), tal cual como se propuso. Este
fichero queda como registro histórico de la propuesta original, no como pendiente.

## Contexto (por qué esta propuesta existe)

T4 de la cadena F2.6 (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md,
punto 4 del diseño) construyó `f26_gate_notification()` en
`src/atlas/core/self_maintenance/f26_gate.py`: cuando el gate F2.6 está
`"due"` (ADRs nuevos desde el último run registrado), esa función devuelve un
dict `{"title", "tldr", "prompt"}` con los mismos nombres de campo que espera
la tool MCP `spawn_task` (`mcp__ccd_session__spawn_task`). Este dict ya viaja
en `atlas f26 status --json` (campo `notification`) y en
`atlas reality --json` (bajo `f26_gate.notification`).

**Restricción real, no rodeable**: `spawn_task` solo existe dentro de una
sesión agente de Claude Code con esa tool cableada. Un proceso headless
(`atlas f26 status`, un cron, `self_build_runner.py`) NO puede invocarla por
sí mismo — no hay SDK ni API HTTP para "crear un chip spawn_task" desde
fuera de una sesión agente. Por eso el código no dispara nada: solo prepara
el contenido. Falta la última pieza, que es puramente instruccional: decirle
a CUALQUIER sesión agente que vea `f26_gate.status == "due"` (algo que ya
ocurre de forma rutinaria — el Operating Loop, paso 1, ya manda correr
`atlas reality --json` al arrancar cualquier sesión) que debe llamar a
`spawn_task` ella misma con ese contenido.

## Dónde iría (sección exacta)

En `AGENTS.md`, dentro de `## OPERATING LOOP`, inmediatamente después del
paso 1 (que ya manda correr `atlas reality --json`). Se propone como un nuevo
paso `1b` (mismo patrón que el `4b` ya existente en ese bloque, que también
inserta una regla intermedia sin renumerar todo lo siguiente).

## Texto exacto propuesto (diff conceptual)

Insertar entre la línea 10 (`1. Run \`PYTHONPATH=src atlas reality --json\`
before making claims about Atlas state.`) y la línea 11 (`2. Structure =
graph first...`):

```diff
 1. Run `PYTHONPATH=src atlas reality --json` before making claims about Atlas state.
+1b. If that output shows `f26_gate.status == "due"` (or
+    `atlas f26 status --json` does), use the `f26_gate.notification` field
+    (or `atlas f26 status --json`'s own `notification` field — same shape)
+    to call `spawn_task` with that exact `title`/`tldr`/`prompt`. Do not run
+    `atlas f26 run` yourself without flagging it first — it dispatches a
+    real, expensive LLM session (a cold Sonnet run of the succession
+    rubric), not a cheap deterministic check. `spawn_task` puts a visible
+    chip in front of a human instead of silently burning a session or
+    silently doing nothing.
 2. Structure = graph first: answer "who imports X / blast radius / churn /
```

## Notas para quien revise esto

- El campo `notification` es `null` cuando el gate no está `due` — no hay
  nada que hacer en ese caso, y el texto propuesto no lo menciona porque
  `spawn_task` simplemente no se llamaría (dict es `None`).
- El texto deja explícito que NO se debe correr `atlas f26 run` sin más: es
  el error que T3/T4 querían evitar (repetir el patrón de "hacerlo barato y
  automático" para algo que el diseño marca deliberadamente caro y manual).
- Si el operador prefiere otra redacción, otro punto de inserción, o fusionar
  esto con el punto 4b existente (que también habla de golden route), este
  fichero es solo la propuesta de partida — no la versión final.
