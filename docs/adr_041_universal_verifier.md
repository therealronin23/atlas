# ADR-041 — Verificador universal (Capa 1)

Fecha: 2026-06-12 · Estado: aceptado · Contexto: `docs/direction_2026-06-12_construir_hacia_arriba.md`

## Decisión

Un seam único `UniversalVerifier.verify(Artifact) -> Evidence` en
`src/atlas/core/verify.py` que unifica los verificadores existentes
(ASTGuard, ResultAuditor, LayeredIsolationSandbox, ValidationRunner)
mediante adaptadores, sin modificarlos.

Regla rectora (**verificación asimétrica**): ningún resultado sube por la
cascada sin un verificador más barato que su productor. Si no existe,
`Evidence.verdict = UNKNOWN` con razón explícita — nunca se finge
verificación.

## Decisiones y porqués

| Decisión | Elegida | Porqué |
|---|---|---|
| Ubicación | fichero único `core/verify.py` | es un seam, no un subsistema; se parte si crece |
| Coste | ordinal (`CostTier` IntEnum: FREE<STATIC<SHAPE<SANDBOX<SUITE<MODEL) | la regla solo compara productor vs verificador; € o segundos serían falsa precisión hoy. La capa 2 puede mapear tiers→coste real |
| Sin verificador más barato | `UNKNOWN` + razón | postmortem 2026-06-12: no mentir sobre readiness; excepción rompería la cascada, pasar silencioso es el bug sellado ayer |
| Integración | adaptadores con deps por Protocol e inyección | base sellada: cero cambios en módulos existentes; tests sin red/subprocesos/GUI |
| Ejecución | barato→caro, cortocircuito en FAIL; UNKNOWN no bloquea pero queda en checks | la métrica de capa 2 es coste por resultado verificado |
| Merkle/CLI | NO cableado aquí | quién llama al seam es decisión de la capa 2 (routing); cablear hoy = acoplamiento prematuro y riesgo de doble escritor. `Evidence.to_dict()` es JSON-serializable y listo para el audit log |
| Proof artifacts | `Evidence` ES el tipo de proof artifact en adelante | el "proof artifact" del max capability roadmap nunca existió como tipo; ColdUpdate puede adjuntar `Evidence.to_dict()` vía `attach_evidence` |

## Consumidores previstos

- **Capa 2 (routing)**: decide qué modelo produce según verificabilidad;
  nada sube sin pasar por este seam. `total_cost` alimenta la métrica
  coste-por-resultado-verificado.
- **Capa 3 (enjambre)**: los workers publican artefactos; el blackboard
  solo acepta los que llegan con `Evidence` PASS.

## Notas

- `SuiteVerifier` hereda el guard anti-recursión de `ValidationRunner`;
  en tests siempre con runner fake.
- Verdicts: `PASS` / `FAIL` / `UNKNOWN`. UNKNOWN de un verificador
  individual no bloquea la cascada pero queda registrado como check.
