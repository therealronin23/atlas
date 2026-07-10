# NEXT_AI_INSTRUCTIONS — cómo continuar Atlas OS

Escrito para una IA menos potente. Sigue esto literalmente.

## Qué es Atlas

Una inteligencia personal persistente que sobrevive a las generaciones de
modelos: memoria, lecciones, herramientas e identidad en hardware propio; los
modelos SOTA entran y salen como proveedores. Atlas OS es su cara visible:
eventos → representación viva + plano de control. NO es un chatbot, ni un
dashboard, ni un wrapper de Claude, ni un clon de Cursor/n8n.

## Qué está construido (verificado, con tests)

- `schemas/` (12 contratos JSON) + espejos pydantic con test de paridad.
- `src/atlas/events/` — Event Kernel (ADR-058): store JSONL, player de
  fixtures, bridge del bus real.
- `src/atlas/api/` — Backend Bridge FastAPI en 127.0.0.1:7341 (read-only
  sobre el core) + import de conversaciones con provenance.
- `ui/atlas-shell/` — UI Vite+React (ADR-059): Cognitive Surface + Control
  Plane. Dominio en `src/core/*.ts`, React solo renderiza.
- `fixtures/` — eventos demo, grafo inicial, conectores mock, gates.

## Cómo ejecutar

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas os-bridge            # terminal 1
cd ui/atlas-shell && npm run dev          # terminal 2 → http://127.0.0.1:5173
```

## Cómo testear (SIEMPRE antes y después de tocar algo)

```bash
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q
MYPYPATH=src python -m mypy src/atlas/api/ src/atlas/events/
cd ui/atlas-shell && npm run build
```

Si `python` no existe, usa `.venv/bin/python`.

## Qué NO tocar jamás

1. `config/governance.json`, `AGENTS.md`, `WORK_LEDGER.md`, `docs/backlog.yaml`
   → son del operador; propón diffs en el chat.
2. La carpeta `1/` → cuarentena, ni leerla.
3. `src/atlas/core/contracts.py` y `core/event_bus.py` → el OS solo se
   SUSCRIBE; extender el mapping se hace en `events/core_bridge.py`.
4. Nada de `Orchestrator` en `src/atlas/api/` (hay un test que lo vigila; si
   te lo encuentras rojo, TU cambio es el problema).
5. Nunca `git add -A` (el operador tiene cambios sin commitear). Nunca push.

## Cómo tomar decisiones

- Orden de autoridad: repo real > evidencia verificada > docs/handoff/ >
  este prompt histórico. Los ADRs se revisan, no se obedecen a ciegas —
  pero documenta TODO cambio en docs/architecture/DECISION_REVIEW.md + ADR
  nuevo en docs/decisions/adr/ (numeración adr_NNN).
- Ante duda técnica: investiga y deja digest en docs/research/
  (RESEARCH_DIGEST_YYYYMMDD_slug.md); no decidas por vibras.
- Todo doc nuevo: `PYTHONPATH=src python scripts/docs_index_audit.py --write`
  antes de commitear.

## Errores que ya se cometieron (no los repitas)

- Doble Orchestrator → corrupción Merkle (por eso el bridge es read-only).
- Settings decorativas: si una configuración no cambia comportamiento
  observable, no la añadas.
- Guard de StrictMode que mataba el WS (App.tsx: el efecto WS va SIN guard).
- Fixtures con merkle_hash inventado: el player los rechaza; no lo "arregles"
  quitando el rechazo.
- `python` a pelo en scripts/tests: resuelve a sys.executable o .venv.

## Cómo actualizar continuidad (al final de CADA sesión)

1. Añade entrada arriba en docs/continuation/IMPLEMENTATION_LOG.md.
2. Actualiza CONTINUATION_STATE.md (What Is Real / Simulated / Next Tasks).
3. Actualiza RISK_REGISTER si abriste/cerraste riesgos.
4. Tests verdes + mypy + npm run build ANTES de decir que terminaste.
5. Propón la entrada de WORK_LEDGER.md en el chat (no la escribas tú).
