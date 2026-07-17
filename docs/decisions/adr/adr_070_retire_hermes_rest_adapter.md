# ADR-070 — Retirada del canal REST legado de Hermes (HermesRestAdapter, ADR-011)

- **Estado**: aceptado (decisión bootstrap 2026-07-17, N2 decidida por el driver
  con recomendación escrita — revisable por el operador; ejecuta el ítem 5
  [bootstrap] de `docs/design/audit_addendum_2026-07-17.md` §4)
- **Fecha**: 2026-07-17
- **Contexto previo**: ADR-011 (REST+HMAC), ADR-028 (twin kanban), audit Codex
  2026-07-16 hallazgo 16 ("`atlas-twin` es el cliente canónico… las rutas
  antiguas fallan cerradas o quedan marcadas como compatibilidad REST").

## Decisión

Se elimina `HermesRestAdapter` (y su smoke operacional REST) del árbol. El
canal canónico hacia Hermes es el **Kanban bridge** (`HermesKanbanAdapter`,
ADR-028) operado por las skills `atlas-twin`/`atlas-audit`. `HermesMockAdapter`
y la `OfflineQueue` (ADR-012) se conservan intactos.

## Evidencia de cero callers (2026-07-17)

1. **Grafo vivo (FRESH en 3f807b0c)**: único importer de `atlas.hermes.hermes`
   = `atlas.core.orchestrator`.
2. **Precedencia en runtime**: `Orchestrator` elige Kanban si
   `HERMES_KANBAN_TRANSPORT` está definido (lo está en `.env`: `local`) — la
   rama REST era código muerto bajo la configuración real.
3. **El VPS Hermes está dado de baja desde mayo 2026** (decisión de alcance,
   ver playbook); no existe endpoint REST vivo que llamar.
4. Los únicos constructores restantes eran sus propios tests
   (`test_hermes_rest_adapter.py`), el stub de test
   (`scripts/hermes_agent_stub/`) y los smokes REST
   (`scripts/hermes_smoke.py`, `scripts/operational_smoke.py`).

## Consecuencias

- Menos superficie: cliente HTTP+HMAC sin uso deja de mantenerse/auditarse.
- `HERMES_BASE_URL`/`HERMES_API_KEY` en `.env` quedan INERTES (el `.env` es
  del operador y no se toca; puede borrarlas cuando quiera).
- `reality`/`doctor` dejan de sugerir el "legacy REST smoke": configuración
  REST sin kanban pasa a reportarse como no-soportada con referencia a este ADR.
- Un re-despliegue de Hermes (T6, decisión N3) usa el canal Kanban/twin; si
  algún día hiciera falta REST de nuevo, se recupera de git (`git log` de
  `src/atlas/hermes/hermes.py` hasta este commit) y se re-audita el HMAC.

## Reversión

`git revert` del commit de retirada (atómico) o rescate selectivo desde el
commit padre. No hay migración de datos: el adapter no persistía estado
(la OfflineQueue se conserva).
