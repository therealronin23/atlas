# Gates A–I — documento de cierre (roll-up)

Condensa los Gates históricos del runtime Atlas en un solo sitio (antes: 14 ficheros sueltos).
**Estado: todos CERRADOS/sellados.** El proyecto **pivotó** del runtime Atlas al filtro de
cumplimiento verificable (Osmosis) — ver `AGENTS.md §Current Direction`. Estos Gates son
**históricos**: no se reabren; se conservan como evidencia. Detalle en cada `gate_*_seal.md`.

| Gate | Tema | Estado | Sello |
|---|---|---|---|
| C | EventBus / arranque núcleo | cerrado | `gate_c_seal.md` |
| D | pipeline cableado opt-in | cerrado | `gate_d_seal.md` |
| E | ADR-002 + dashboard + voz | cerrado | `gate_e_seal.md` |
| F | readiness mundo real (browser) | cerrado | `gate_f_seal.md` (+ `gate_f_plan.md`, `gate_f_real_world_readiness.md`) |
| G | readiness operacional | cerrado | `gate_g_seal.md` (+ `gate_g_operational_readiness.md`) |
| H | resiliencia / MVP | cerrado | `gate_h_seal.md` (+ `gate_h_mvp_scope.md`, `gate_h_action_plan.md`, `gate_h_resilience_plan.md`) |
| I | servicio / endurecimiento | cerrado | `gate_i_seal.md` (+ `gate_i_plan.md`) |

(A y B son anteriores al esquema de sellos; absorbidos en C.)

## Patrón de cierre con roll-up (estándar, para Gates futuros)

Al cerrar un nodo `Tipo→Fase→ADR→Gate`, su auditoría/nota se **condensa hacia arriba**:
tipo→fase→ADR→Gate. El Gate cierra con UN documento de cierre (como este) que condensa la
cadena; lo granular se archiva (git + `docs/archive/`), no se borra. Ejemplo vivo de este
patrón aplicado a la gobernanza: `docs/decisions/gates/CLOSURE_governance_2026-06-21.md`.
