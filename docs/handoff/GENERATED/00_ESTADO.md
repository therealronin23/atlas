<!-- GENERADO por atlas handoff 2026-08-01T07:03:30.309308+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-01 (continuación) — canal twin activado, lifecycle de lecciones
  por fin cableado en el CALLER real (no donde parecía), cron de Hermes
  medido, gap D2 de Hermes encontrado y documentado (latente, no arreglado
  a propósito).**
  **Canal twin (respuesta a la pregunta del operador "¿está activado el modo
  twins?")**: estaba a medias. El lado Atlas (`/api/exec/*`, ADR-026/027) ya
  funcionaba — verificado con `curl` ANTES de tocar nada: `401 invalid
  timestamp`, no 404. El lado Hermes nunca se instaló para transporte local
  (sólo se pensó para el VPS, de baja): `~/.hermes/.env` no tenía ni
  `ATLAS_DASHBOARD_URL` ni `HERMES_API_KEY`. Explica 2 tareas reales del
  kanban atascadas. Arreglado: skill `atlas-twin` instalada, credenciales
  copiadas, verificado en vivo (`health`→`ok:true` con datos reales del
  orquestador; `shell` respeta su propia allowlist; `intent` agota timeout
  de cliente, esperable).
  **Lifecycle de lecciones — el hallazgo fue el CALLER, no el tick**:
  `AtlasServiceRunner.tick()` sólo barre TTLs (ADR-033) — NINGÚN
  `maintenance_*_tick` corre desde ahí. El caller real de TODOS ellos es
  `MaintenanceScheduler._extra_cycles`, un hilo daemon propio arrancado por
  `service_runner.py:108`. Sin trazar hasta ahí, mi tick nuevo habría
  quedado tan huérfano como `apply_lifecycle_transitions` desde el 18-jul.
  Añadido a la tupla real, `ATLAS_LESSON_LIFECYCLE=1` activado (mismo
  patrón que sus hermanos), daemon reiniciado. **Ejecutado una vez en vivo**:
  5 de 17 lecciones reales marcadas `stale` (30-35 días, nunca usadas), 0
  archivadas, 0 borradas.
  **Cron de Hermes medido**: 8287 líneas, capacidad genuina sin equivalente
  en Atlas (scheduling de usuario/agente vs el interno fijo de Atlas).
  Cierra el flag "unverified" de la auditoría de julio. Extraer técnica, no
  el paquete — no implementado, tamaño propio de tanda dedicada.
  **Gap D2 de Hermes, medido con precisión**: su nivel "hardline" YA bloquea
  incondicionalmente antes del yolo (mismo principio que D2) — bien
  diseñado. El hueco real es más estrecho: en el nivel "dangerous", con
  `approvals.mode: smart`, un LLM auxiliar puede autoaprobar sin humano.
  **Verificado que NO está activo aquí** (`manual` por defecto, sin
  overrides). Latente, no explotado. Delegado como tarea acotada — tocar
  3928 líneas de seguridad de un repo que no mantenemos, al final de una
  sesión ya enorme, es la prisa que esta sesión entera ha corregido en
  otros. **Hallazgo de paso importante**: el clon de disección
  (`atlas-forks/hermes-agent`, 0.18.2) NO es la instalación real
  (`~/.hermes/hermes-agent`, 0.19.1) — tocar el equivocado no tiene efecto.
  **Estado**: suite 5019 passed · 6 skipped · check_canon PASS (2106) ·
  mypy limpio.
