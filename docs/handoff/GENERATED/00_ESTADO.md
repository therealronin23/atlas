<!-- GENERADO por atlas handoff 2026-07-31T21:45:05.632401+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 — CIERRE DE SESIÓN. Todo empujado a `main`; el operador vuelve
  con una idea nueva.**
  **Qué se cerró hoy**: F0.2 (radar de código dormido regex→AST: veía 2 de 16),
  F1 completo salvo `correction.py` (1.211 de 1.315 loc dormidos despertados),
  monitorización local con aviso por Telegram (verificada extremo a extremo en
  el móvil del operador), Cónclave con modelos de razonamiento, y el rediseño
  de `atlas reality`.
  **Estado medido al cierre**: suite **4955 passed · 6 skipped**, `check_canon`
  PASS (2105), `mypy` limpio, daemon `active`, watchdog `active`, Hermes
  `live_verified: true`, `.env` en 600 y fuera de git.
  **DECISIONES ABIERTAS del operador** (no re-litigar sin ellas):
  1. **`correction.py`** (104 loc, dormido) — aparcado en frío tras Cónclave
     FAIL unánime. Archivar o revisar ADR-069 explícitamente.
  2. **El prompt hostil del Cónclave** — Gemini calificó `BLOCKING` un cambio
     de timeout de 30s a 60s. Si el prompt empuja a objetar SIEMPRE, la
     unanimidad vale menos de lo que le atribuimos. Cambiarlo afecta a TODAS
     las deliberaciones futuras: es diseño del operador.
  3. **F2.2 Hermes** — las 3 tareas "monitoriza servidor A/B/C" son intención
     real del operador, no basura de cola. No mezclarlas con el smoke.
  4. **"Que reality se actualice habitualmente"** — falta decidir QUIÉN
     consume un registro periódico antes de construirlo.
  **Frentes sin empezar**: dossier de Osmosis (F2.1), replanteo de alcance de
  UI (F3.1), e investigar+planificar `business/extract.py` y
  `mcp/adapter_registry.py` (los 2 dormidos que el radar nuevo destapó).
