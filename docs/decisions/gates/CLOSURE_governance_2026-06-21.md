# Cierre — Gate de Gobernanza (2026-06-21)

Tipo-2 (fundacional: el orden es la base de todo). Roll-up condensado de las fases F0–F4.
Detalle en REPO_STANDARD.md, CAPABILITIES.md, el premortem y los WHY.md de cuarentena.

## Qué se cerró

| Fase | Resultado |
|---|---|
| **F0** Estándar | `REPO_STANDARD.md` (layout, ciclo de vida+roll-up, saneamiento) + `CAPABILITIES.md` (manifiesto de honestidad anti-overclaim) + OPERATING LOOP en AGENTS.md + hook SessionStart (inyecta WORK_LEDGER) + manías nuevas (operating-loop, debt-closure, verify-the-real-case, internal-prior-art-first, wire-before-claim) |
| **F1** Limpieza riesgo-bajo | artefactos LaTeX a .gitignore; volcados scratch de raíz → graveyard; carpeta vacía borrada; 3 huérfanos (witness_server, log_behavioral, kyc_binding) a cuarentena |
| **F2** Docs | `docs/` reorganizado a taxonomía (reference/governance/design + _graveyard); refs actualizadas, 0 stale |
| **F3** Código muerto | auditoría de cableado → clúster grande no-cableado a cuarentena (afinidad, split-view, red-team-en-src); **lazo auditable** y **mission** CABLEADOS+probados (no cuarentenados) |
| **F4** Cierre + ciclo | roll-up de Gates A–I (`gates/CLOSURE.md`); **ciclo de saneamiento** automatizado (`scripts/sanitation_audit.py`) |

## Hallazgos honestos (no se ocultan)
- Confirmado a escala: se construyó una capa inmune/membrana/knowledge MUY unit-testeada
  pero **sin cablear** (≈171 tests cayeron al cuarentenar el clúster). Vapor de sistema.
- `cli.py` tiene WIP del usuario con 13 errores mypy (comando completeness-demo) — NO es nuestro.
- `live_loop` queda "test-wired": probado, pero su único consumidor es el test (espera tráfico
  vivo). El radar de saneamiento lo seguirá marcando hasta que haya consumidor en producción.
- TPM = HMAC software (no hardware); ContentFilter = no existe; split-view exige operadores
  independientes que no hay. Todo declarado en CAPABILITIES.md.

## Ciclo de saneamiento (recurrente, establecido)
`python3 scripts/sanitation_audit.py` (read-only) cada ciclo (al cerrar un Gate o ~mensual):
reporta vapor de sistema, cuarentena vencida (grace 30d → `git rm` si no se rescató), carpetas
vacías y refs stale. El humano/agente decide KEEP/QUARANTINE/DELETE (REPO_STANDARD §3).

## Estado
Gate de gobernanza **CERRADO**. Suite 1875 verde. Cuarentena reversible (git + graveyard).
Próximo ciclo de saneamiento: revisar `_graveyard/2026-06-21*` cuando venza el grace (~2026-07-21).
