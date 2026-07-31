<!-- GENERADO por atlas handoff 2026-07-31T23:26:00.750432+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-01 — Hermes ya se diagnostica y Atlas por fin le escucha. Y el
  lifecycle de lecciones NO se cableó, a propósito: el cimiento está roto.**
  **Hermes (HECHO, `55b13a2`)**: el operador pidió *"haz que Hermes corrija y
  se autocorrija"*. Al medirlo, el hallazgo fue que **Hermes ya traía las dos
  mitades y Atlas nunca las llamaba** — `diagnostics --json` (detecta tareas
  varadas/atascadas/con fallos repetidos, con acciones sugeridas) y `repair
  --json` (`PRAGMA integrity_check`, auto-repara SÓLO índices tras cuarentena,
  fail-closed de fábrica). Ninguna estaba en `ALLOWED_KANBAN_ACTIONS`.
  **Lo que el tablero real llevaba 23 días diciendo sin que nadie escuchara**:
  1 `critical` (`stranded_in_ready`, 564 h sin worker), 2 `error`
  (`repeated_failures`, crash ×2 — uno es *monitoriza servidor C*), 2 `warning`
  (`stuck_in_blocked`, 198 h — servidores A y B). **Eso CONTESTA el F2.2**: las
  tres tareas de servidor del operador no estaban "en cola", dos llevan 198 h
  atascadas y la tercera ha petado dos veces.
  También: `list_tasks()` no pasaba `--json`, así que `parsed` quedaba `None` y
  quien quisiera RAZONAR sobre tareas recibía None en silencio; y `_run_local`
  llamaba a `_default_runner` en vez de `self._runner`, ignorando el runner
  inyectado (un test "aislado" acababa invocando el Hermes REAL). Aviso vía la
  sonda `hermes_probe` del watchdog —NO un tick nuevo: ya corre cada 15 min,
  ya tiene Telegram verificado y anti-repetición de 12 h— y sólo para
  `critical`/`error`: los dos `warning` de 198 h no despiertan a nadie.
  Las acciones que MUTAN (`unblock`/`edit`/`reassign`) quedan FUERA: entran por
  ADR con el decider delante (decisión del operador, pendiente de escribir).
  **Lecciones (PARADO CON RAZÓN)**: iba a cablear
  `apply_lifecycle_transitions()` y la medición lo desaconsejó. Las 17 lecciones
  reales tienen `recall_count = 0` y ninguna `last_recalled_at`. **Corrijo una
  afirmación mía de esta misma sesión**: dije que "Atlas lleva semanas contando
  el uso de cada lección" — falso, no ha contado ni uno.
  **La causa está aguas arriba**: `orchestrator.py:1612` construye
  `LessonStore(~/atlas/memory/lessons)` → **0 ficheros**, mientras
  `atlas_coder`/`tool_coder`/`maintenance_facade`/`trunk_server` usan
  `<repo>/workspace/lessons` → **17 lecciones**. El `LessonRecaller` del daemon
  lee un almacén VACÍO, así que no puede recordar nada nunca. Cablear el
  envejecido encima habría **archivado las 17 por "nunca usadas"**, que es
  falso: nunca han tenido oportunidad. Primero se unifica la ruta.
  (La memoria `memory-lessons-disconnection-2026-07-03` daba esto por "arreglado
  en su mayoría" — no lo estaba.)
