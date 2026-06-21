# Graveyard — 2026-06-21

Cuarentena, NO borrado: estos elementos salieron de `src/`/raíz por inservibles o no-cableados.
Reversible (git + aquí). Veredicto en el próximo ciclo de saneamiento: RESCATAR o `git rm`.

## Volcados de conversación / scratch (raíz) — motivo: no son artefactos del proyecto

| Fichero | Motivo | Veredicto |
|---|---|---|
| `idea.md` | volcado de ideación | pendiente |
| `idea avance.md` | volcado de conversación | pendiente |
| `idea avance 2.md` | volcado de conversación | pendiente |
| `idea avance 3.md` | volcado de conversación | pendiente |
| `AUDITORIA GROK.md` | auditoría externa pegada, ya destilada en memoria | pendiente |
| `Gemini-Auditoría Técnica y Regulatoria de Atlas.md` | ídem | pendiente |
| `gpt.md` | volcado externo | pendiente |

## Módulos no-cableados (0 importadores no-test) — motivo: vapor de sistema (regla wire-before-claim)

| Módulo + test | Qué era | Veredicto |
|---|---|---|
| `transparency/witness_server.py` + test | WitnessServer anti-split-view HTTP (RFC 9162); rescatar si se ensambla red ≥2 witnesses | pendiente |
| `security/log_behavioral.py` + test | LogBehavioralAuditor (OSM-031, same-input→distinto-output) | pendiente |
| `security/kyc_binding.py` + test | KycBinding (operator KYC, EU AI Act GAP-4) | pendiente |

Estado registrado también en `docs/governance/CAPABILITIES.md`.
