# Graveyard F3 — 2026-06-21 — por qué está aquí cada cosa

Cuarentena REVERSIBLE (git + aquí), NO borrado. Motivo común: **vapor de sistema** — código
real, unit-testeado, pero con **0 importadores no-test** (nadie lo usa en un camino vivo).
Regla `wire-before-claim`. Revisión en el próximo ciclo: RESCATAR (si se cablea) o `git rm`.

## Módulos (en `orphan_modules/`) + por qué

| Módulo | Qué era | Por qué a cuarentena |
|---|---|---|
| `immunity/affinity_maturation.py` | motor de maduración por afinidad (ADR-054 capa 5) | 0 consumidores vivos; es la capa de DETECCIÓN que 1c midió que reconoce TEMA, no intención (FP fronterizo ~33%). Cablearla = poner en vivo algo medido-que-no-funciona |
| `immunity/scorers.py` (`RecallAffinityScorer`) | scorer de afinidad para el motor anterior | hoja del mismo sub-clúster; 0 consumidores |
| `immunity/llm_scorer.py` | scorer/mutador vía LLM | solo lo re-exportaba `__init__`; 0 consumidores reales |
| `core/security_worker.py` | SecurityWorker/SecurityTask | 0 referencias en todo el repo; propósito sin uso |
| `security/fuzzing.py` | FuzzResult/FuzzReport | red-team en `src/` → viola ADR-056 (red-team es dev-only) |
| `security/red_team.py` | RedTeamRunner/AttackSignatureStore | ídem ADR-056; el paper evalúa con `scripts/redteam/` (vivo) |
| `transparency/gossip.py` | gossip RFC 9162 (split-view) | 0 consumidores tras quitar `witness_server`; la garantía exige ≥2 operadores INDEPENDIENTES (no existen operando en solitario) |
| `transparency/witness.py` | Witness/observe split-view | mismo motivo; quedó huérfano al caer witness_server |

## Tests (en `orphan_tests/`)
`test_red_team`, `test_fuzzing`, `test_security_worker`, `test_gossip`, `test_transparency_witness`,
y `test_immunity_mutators_scorers` (la parte de scorers+afinidad; los tests de `mutators` —que SÍ se
usa— se extrajeron a `tests/test_mutators.py`).

## NO cuarentenado (se queda + se cablea)
`immunity/live_loop.py` + `immunity/teacher_debate.py` (lazo de aprendizaje AUDITABLE, eje ganador) y
`knowledge/mission.py` (ingesta+verificación, funcional de verdad). Ver CAPABILITIES.md.
