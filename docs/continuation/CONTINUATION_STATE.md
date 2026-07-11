# CONTINUATION_STATE — Atlas OS

Actualizado: 2026-07-11 (sesión Fable 5/Opus, Fase 15 + Fase 16 — Product OS).

## Current Status

Sobre la base final-compatible del 2026-07-10 (Event Kernel, Backend
Bridge, UI shell, governance inicial), Fase 15 construyó el sustrato de
producto exigido por `atlas_product_os_liquid_ui_pack_v1` (Integration
Fabric, PolicyEngine, Business Core, Question Engine). Fase 16 (misma
sesión, más tarde) cerró los 8 gaps priorizados en
`docs/continuation/phase15/RECOMMENDED_PHASE_16.md`: convergencia de
evaluadores, Gate Engine real, persistencia, Sector/Objective Registry,
Legal registry, invariante estructural, primer conector real (Gmail),
arnés UI. **26 schemas, 190 tests OS.** Detalle: `docs/continuation/
phase15/PHASE_15_COMPLETION_REPORT.md` (Fase 15) + este fichero (Fase 16).

## What Is Real

- Todo lo de Fase 15 (Integration Fabric, PolicyEngine, Business Core
  draft-first, Question Engine — ver entrada anterior de este fichero).
- **Gate Engine**: `request_activation` abre un `GateTicket` real
  (`open→approved|rejected`), `approve_activation` lo aprueba, nuevo
  `reject_activation`. "Gated" es un objeto auditable, no un flag.
  `GET /gates/open`, `atlas gates list`.
- **PolicyEngine converge con `/permissions/evaluate`** para toda acción
  que sea una capability del catálogo (ADR-062); legacy intacto para el
  resto.
- **Sesiones de onboarding persisten a disco** (sobreviven reinicio del
  bridge, probado con dos apps sobre el mismo path).
- **Sector Registry + Objective Registry**: `GET /sectors`, `/objectives`;
  test de drift real contra los packs existentes.
- **Legal/ToS registry**: `recipes_missing_terms` audita que toda receta
  de riesgo legal tiene su entrada.
- **`personal_channel` estructural**: el invariante de canal personal ya
  no depende del nombre del conector, es un campo del schema chequeado
  en código.
- **Primer conector real**: `GmailReadOnlyConnector` (stdlib `urllib`,
  cero dependencia nueva). Real solo si `env:GMAIL_OAUTH_TOKEN` existe;
  si no, `BLOCKED_BY_MISSING_DEPENDENCY` honesto. `email.send` ausente.
- **Arnés UI real**: vista "⚑ Harness" en `ui/atlas-shell` conduce
  `/connections`, `/business`, `/gates` reales — verificado con
  navegador real (no solo build).

## What Is Simulated

- Todo lo de Fase 15 sigue simulado igual (intent pipeline, conectores
  Fase 4-9 mock, /graph fixture).
- Gmail sigue en `mode=mock` de facto hasta que el operador aporte
  `GMAIL_OAUTH_TOKEN`; el seam es real, la llamada viva está gateada a
  la credencial.
- `BusinessCore.activation.gate_ticket_id` referencia un ticket real,
  pero el Gate Engine todavía solo cubre activaciones de Business Core,
  no toda acción `require_gate` del PolicyEngine (Fase 17).

## What Was Changed (Fase 16)

8 commits en `main` (sin push): `51c57c77`→`847a18c2`. Todo aditivo salvo
`fixtures/governance/gates.json` (+8 gates, ya en Fase 15) y el rename del
invariante whatsapp→`pol_hard_personal_channel_send`. Un título de commit
corregido con `amend` (copy-paste, cuerpo ya era correcto — no se cambió
contenido, solo el título).

**Hallazgo relevante**: el daemon de autoconstrucción del repo
(`ATLAS_SELF_BUILD=1`, proceso vivo) implementó F16-6 (HarnessPanel) de
forma autónoma, en paralelo, usando los endpoints reales según se
commiteaban esta sesión. Verificado y aceptado tras auditoría completa
(build+bridge real+navegador real). Ver IMPLEMENTATION_LOG para el detalle.

## Architecture Decisions Made (Fase 16)

- ADR-062 (convergencia PolicyEngine ↔ evaluador v1).
- ADR-063 (Gate Engine real).
- ADR-065 (primer conector real Gmail, cliente propio stdlib — el
  Cónclave descartó la ruta MCP-del-tronco por hecho: el bridge no puede
  llamar MCP).

## Risks

Ver `docs/risks/RISK_REGISTER.md`. Nuevo: el daemon de autoconstrucción
corre en paralelo contra el mismo repo sin coordinación explícita con la
sesión interactiva — funcionó bien esta vez (cero colisión de ficheros)
pero es un riesgo de coordinación a vigilar si crece el paralelismo.

## Next Best Tasks

`docs/continuation/phase15/RECOMMENDED_PHASE_16.md` queda con sus 8 ítems
todos cerrados. Próximos candidatos (sin backlog formal todavía):
generalizar el Gate Engine a toda acción `require_gate` (no solo
activación de Business Core); credencial Gmail real del operador para
probar la llamada viva; convergencia total PolicyEngine↔v1 (hoy solo
capabilities conocidas).

## How To Run

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas os-bridge          # bridge en 127.0.0.1:7341
cd ui/atlas-shell && npm install && npm run dev   # shell en 127.0.0.1:5173 (ARNÉS, ver su README)
```

## How To Test

```bash
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q   # 190 passed
MYPYPATH=src python -m mypy src/atlas/api/ src/atlas/events/ src/atlas/fabric/ src/atlas/business/ src/atlas/interfaces/cli.py
cd ui/atlas-shell && npm run build      # tsc strict + vite
```

## Known Failures

Ninguno en los 190 tests OS al cierre de Fase 16.

## Where To Continue

Leer EN ORDEN: este doc → `docs/continuation/IMPLEMENTATION_LOG.md`
(entrada Fase 16) → ADR-062/063/065 → el código de `src/atlas/fabric/gates.py`,
`src/atlas/business/registries.py`, `src/atlas/fabric/connectors/gmail.py`.

## Warning To Next AI

Todo lo de Fase 15 sigue aplicando (ver entrada anterior de este fichero:
NO Orchestrator, NO tocar ficheros del operador, NO `git add -A`, NO
importar `atlas.api.*` a nivel de módulo desde `fabric/`/`business/`,
motores nuevos con `path` explícito en tests). Añadido en Fase 16: **hay
un daemon de autoconstrucción vivo contra este repo** — antes de escribir
código nuevo, comprueba `ps aux | grep ATLAS_SELF_BUILD` y `git status`
por si ya hizo el trabajo; verifícalo (build+tests+smoke real) en vez de
descartarlo o sobrescribirlo a ciegas.
