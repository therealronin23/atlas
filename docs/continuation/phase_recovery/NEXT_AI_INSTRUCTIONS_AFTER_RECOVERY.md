# NEXT_AI_INSTRUCTIONS_AFTER_RECOVERY

Prompt listo para pegar a la siguiente sesión/IA que continúe Atlas OS.

---

Estás continuando Atlas OS. Antes de escribir nada, lee en orden:

1. `AGENTS.md` (raíz del repo).
2. `docs/continuation/phase_recovery/PHASE_RECOVERY_FINAL_VERDICT.md` —
   veredicto completo de si las fases 1-16 están hechas (spoiler: F0-F4 y
   F7-F10 sí, F5/F6 parkeadas por ADR-066, F11-14 nunca existieron, F15/F16
   sanas).
3. `docs/continuation/CONTINUATION_STATE.md` y `KNOWN_RISKS.md` (#14 es el
   hallazgo de esta auditoría).
4. `PYTHONPATH=src atlas reality --json` para confirmar el estado real
   antes de asumir nada de lo escrito arriba sigue siendo cierto.

## Qué NO hacer

- No vuelvas a auditar "¿existen las fases 11-14?" — ya está cerrado con
  evidencia en `docs/continuation/phase_recovery/PHASE_SOURCE_INDEX.md`.
- No implementes Visual Orchestrator Territory ni Coding+Research
  Territories sin que el operador reabra explícitamente ADR-066.
- No pulas `ui/atlas-shell` como producto final — sigue siendo arnés
  (D11/ADR-059), confirmado de nuevo por esta auditoría.
- No actives un token real de Gmail ni pruebes la llamada viva sin que el
  operador lo pida explícitamente.
- No toques `WORK_LEDGER.md`, `config/governance.json`, `AGENTS.md`,
  `docs/backlog.yaml`, ni la carpeta `1/` — son del operador, propone diff
  en chat.

## Candidatos de trabajo (ninguno obligatorio — pregunta al operador cuál)

1. Generalizar el Gate Engine (`src/atlas/fabric/gates.py`) más allá de
   Business Core activation, a toda acción `require_gate` del PolicyEngine.
2. Convergencia total PolicyEngine↔evaluador v1 (hoy solo capabilities
   conocidas, ver ADR-062).
3. Reclasificar en `docs/INDEX.yaml` las ~26 entradas de pack cuyo
   contenido SÍ tiene código real, de `status: propuesto` a algo más
   preciso — requiere juicio caso por caso, no hacerlo en bloque.
4. Si el operador aporta un `GMAIL_OAUTH_TOKEN` real: ejercitar
   `GmailReadOnlyConnector.list_messages()` en vivo por primera vez.
5. Cualquiera de los 14 gaps restantes de `tasks/GAP_DETECTION_REGISTER.md`
   del pack 3 (multi-user roles, offline queues, backup/restore, etc.) —
   trabajo de producto F17+, no de recuperación.

## Verificación estándar antes de cerrar cualquier sesión futura

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas reality --json
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q
MYPYPATH=src python -m mypy src/atlas/fabric/ src/atlas/business/ src/atlas/api/ src/atlas/interfaces/cli.py
PYTHONPATH=src python scripts/docs_index_audit.py --strict
```
