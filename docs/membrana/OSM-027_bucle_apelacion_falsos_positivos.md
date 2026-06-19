# OSM-027 — Bucle de apelación de falsos positivos con aprendizaje

Fecha: 2026-06-17 · Estado: **En membrana** (módulo `transparency/appeal.py` + 8 tests, 2026-06-19; wiring al gateway pendiente) · Origen: `idea avance 3.md` ·
Contexto: ADR-040 (Decider/PDP), ADR-044 (LessonStore), ADR-049 (organismo de conocimiento),
`src/atlas/immunity/`, [[OSM-024]], [[OSM-025]], [[OSM-028]].

---

## Contexto

Un filtro obligatorio en el path ([[OSM-024]]) que bloquea por causa genera **falsos
positivos**: escritores de ficción, investigadores, roleplay legítimo. Sin una vía de
reparación rápida, el filtro es inaceptable para el usuario y un riesgo legal para el
proveedor. El usuario lo planteó como: el usuario reporta → un filtro IA verifica → si es
falso positivo real, recupera la cuenta automáticamente; si no, escala a un humano; con el
tiempo aprende y los falsos positivos disminuyen.

## La idea

Un lazo de apelación con cuatro pasos, todos registrados en el log Merkle:

1. **Reporte**: el usuario marca un bloqueo como falso positivo. El reporte queda atado a la
   secuencia firmada ([[OSM-025]]) de la petición bloqueada — `seq` + `payload_hash` + firma.
2. **Filtro IA**: un verificador automático re-evalúa el caso contra la lista cerrada de
   abusos ([[OSM-028]]). Si claramente fue falso positivo → **auto-restauración** inmediata.
3. **Escalado al PDP**: si hay duda, escala a un decisor (ADR-040). El humano es *una*
   implementación del PDP, no el path fijo — coherente con el rumbo del proyecto.
4. **Aprendizaje**: el resultado alimenta el LessonStore (ADR-044). Patrones de falso
   positivo confirmados ajustan el monitor por causa; el organismo (ADR-049) inyecta el
   patrón actualizado.

## Interfaz propuesta

```python
@dataclass
class AppealRecord:
    seq: int                  # seq de la petición bloqueada
    payload_hash: str         # SHA-256(prompt) — enlaza al InspectionRecord original
    subject_sig: str          # firma del sujeto sobre (seq, payload_hash, "appeal")
    appeal_ts_ns: int         # timestamp del reporte
    reason: str               # texto libre del sujeto (no se almacena; solo el hash)
    reason_hash: str          # SHA-256(reason) — lo que va al log

@dataclass
class AppealVerdict:
    appeal_seq: int
    verdict: Literal["auto_restored", "escalated", "denied"]
    cause: str                # heurística que cambió / confirmó / rechazó
    lesson_id: str | None     # ID en LessonStore si generó aprendizaje
    committed_leaf: int       # índice en el log Merkle

class FalsePositiveApealer:
    def __init__(
        self,
        inspector,          # AttestedInspector — re-evalúa la causa original
        pdp,                # Decider (ADR-040) — para escalados
        lesson_store,       # LessonStore (ADR-044) — para aprendizaje
        log,                # TransparencyLog — todo queda en la cadena
        *,
        appeal_rate_limit: int = 5,   # max apelaciones por sujeto/hora
    ) -> None: ...

    def submit(self, record: AppealRecord) -> AppealVerdict:
        """Punto de entrada. Ejecuta los 4 pasos y retorna el veredicto."""

    def _auto_evaluate(self, record: AppealRecord) -> Literal["clear_fp", "unclear"]:
        """Paso 2: re-evalúa la causa contra la lista cerrada. Sin retener contenido."""

    def _escalate(self, record: AppealRecord) -> AppealVerdict:
        """Paso 3: delega al PDP. Bloquea hasta decisión o timeout."""

    def _learn(self, record: AppealRecord, verdict: AppealVerdict) -> None:
        """Paso 4: si veredicto confirmed, inserta lección en LessonStore.
        Lección = {cause_pattern_that_misfired, corrected_threshold} — nunca el prompt."""
```

**Anti-abuso**: `appeal_rate_limit` limita apelaciones por sujeto/hora. Si supera el umbral,
la apelación se deniega automáticamente y se registra como señal de campaña en el log
(métrica I4 sobre apelaciones, no solo sobre peticiones originales).

**Invariante I3**: `AppealRecord.reason` no se almacena — solo su hash. La lección en
LessonStore referencia el *patrón de causa* que disparó mal (`cause_pattern_that_misfired`),
nunca el contenido del usuario. El contenido legítimo nunca entra en el organismo.

## Encaje en Atlas

- **PDP (ADR-040)**: escalado usa `Decider.decide(sensitivity="medium")`. La auto-restauración
  es un `DecisionResult.ALLOW` del filtro IA bajo política; el escalado es `REQUIRES_HUMAN`
  con decisor intercambiable.
- **LessonStore (ADR-044)**: hoy recibe lecciones de auto-mejora (ADR-039) y conocimiento
  externo (ADR-049). Esta OSM añade una tercera fuente: falsos positivos confirmados. La
  interfaz de inserción es la misma; cambia el origen.
- **TransparencyGateway**: `AppealRecord` y `AppealVerdict` se commitean al log antes de
  actuar — misma garantía de completitud que las peticiones normales.

## Correcciones de verificación

- **Riesgo de violar I3**: resuelto por diseño — `reason_hash` en lugar de `reason`;
  lección a nivel de heurística, no de prompt. Verificable: `FalsePositiveApealer._learn`
  no tiene acceso al texto del prompt original en ningún camino.
- **Anti-abuso de apelaciones**: un atacante real apelará en masa para degradar el filtro.
  `appeal_rate_limit` + señal de campaña cierran el vector. El umbral es configurable, no
  hardcodeado.
- **El PDP no es humano obligatorio**: `Decider` con `ATLAS_DECIDER=autonomous` resuelve
  escalados sin humano cuando la política lo permite. No hardcodear espera humana.

## Escenarios de test (compuerta #3)

| Escenario | Entrada | Resultado esperado |
|---|---|---|
| T1 — FP claro | Bloqueo por causa "violence" en prompt de novela histórica | `auto_restored`; lección sobre umbral de "violence" en ficción |
| T2 — Duda / escala | Bloqueo por causa ambigua; PDP stub devuelve `Allow` | `escalated` → `auto_restored`; lección si PDP confirma FP |
| T3 — Abuso de apelación | 6 apelaciones en 1h del mismo sujeto | 6ª denegada; señal de campaña en log |
| T4 — FP rechazado (TP real) | Re-evaluación confirma el bloqueo | `denied`; sin lección; causa original reforzada |
| T5 — Log commitment | Cualquier veredicto | `AppealVerdict.committed_leaf` es un índice válido en el TransparencyLog |

## Path de implementación

1. `src/atlas/transparency/appeal.py` — `AppealRecord`, `AppealVerdict`, `FalsePositiveApealer`
2. `src/atlas/core/decider/` — ningún cambio; reusar `Decider.decide()` existente
3. `src/atlas/core/lesson_store.py` — añadir `LessonKind.FALSE_POSITIVE_CORRECTION` si no existe
4. `tests/test_appeal.py` — 5 escenarios de arriba
5. Wiring al gateway: `TransparencyGateway` acepta `appealer` opt-in, igual que acepta `shadow_router`

## Criterios de compuerta

1. **Verificable**: reusar PDP + LessonStore probados; la novedad (cableado + anti-abuso) es nueva.
2. **Coherente**: respeta I3 (heurística, no contenido) e I5 (ajustes vía PDP). PDP intercambiable.
3. **Probado**: 5 escenarios de test; todos deben pasar antes de cruzar.
4. **Mantenible**: 1 módulo nuevo (`appeal.py`), 0 deps externas.
5. **Sancionado**: cada ajuste del monitor por causa pasa por el PDP (I5).

## Límites honestos

- **Latencia de reparación**: el escalado al PDP puede ser lento si hay humano en el bucle.
  La promesa "auto-restaura si es FP claro" solo cubre los casos donde `_auto_evaluate`
  devuelve `clear_fp` con alta confianza.
- **Equilibrio FP/FN**: bajar falsos positivos sube el riesgo de falsos negativos. El lazo
  optimiza, no resuelve, esa tensión estructural.
- **Carga del PDP en volumen**: si el filtro IA no resuelve la mayoría, el escalado satura.
  El `appeal_rate_limit` es el primer cortafuegos; en producción habría cuotas por tier.
- **La lección no es inmediata**: LessonStore → organismo → ajuste del monitor es un ciclo
  asíncrono. El FP se restaura inmediatamente; el aprendizaje tarda un ciclo.
