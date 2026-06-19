# OSM-028 — Inspección por causa: metadata-monitor-first

Fecha: 2026-06-17 (actualizado 2026-06-19) · Estado: **En membrana** (`AttestedInspector` + `cause=` en gateway implementados; **compuerta de causa = `DriftTripwire` implementada 2026-06-19**, ver más abajo) · Origen: `idea avance 3.md` ·
Contexto: ADR-053 (causa registrada), ADR-054 (capa 1), `src/atlas/transparency/attestation.py`
(`AttestedInspector`), `src/atlas/security/drift.py` (compuerta de causa), [[OSM-001]] (métrica de campaña), [[OSM-024]], [[OSM-042]] (shadow router que consume el confidence).

---

## Contexto

La promesa central del gateway al usuario es: *tu contenido solo se inspecciona cuando hay
causa, y la causa queda registrada*. Para que eso sea barato y honesto en un filtro
obligatorio en el path ([[OSM-024]]), la inspección no puede leer el contenido de todas las
peticiones. El chat 3 propone un esquema de dos niveles: primero metadata (barato), y solo
si hay causa se inspecciona el contenido contra una lista cerrada.

## La idea

1. **Metadata-monitor-first (barato, siempre)**: analiza solo señales de bajo coste —
   embeddings ligeros del prompt + reglas deterministas (volumen, cambio de IP, similitud
   con patrones de ataque conocidos). No lee el contenido como tal; computa una señal.
2. **Causa registrada**: si el monitor supera umbral, se registra **el motivo** en el log
   Merkle (`inspected=true, cause=...`) antes de mirar contenido. Sin causa → `inspected=false`
   y pasa directo al modelo.
3. **Inspección acotada (solo con causa)**: un inspector revisa el contenido **contra una
   lista cerrada y gobernada de abusos** (jailbreak, exfiltración…), nunca construyendo
   perfil del usuario. Todo lo inspeccionado queda atado a la secuencia firmada.

## Encaje en Atlas

- **`AttestedInspector`** (`attestation.py`) es el inspector real de Atlas — el "ScopedInspector"
  del chat es ese, renombrado. Esta OSM le antepone el monitor de metadata como compuerta de
  causa.
- **Capa 1 (ADR-054)**: el monitor por causa es el front-end barato de la capa de filtro.
- **[[OSM-001]] (métrica de campaña)**: las señales del monitor (similitud, volumen) son la
  materia prima de C_attempts / K_attribution. Las dos OSM comparten el cómputo de similitud.
- **Invariantes I2** (la causa se registra) e **I3** (no perfilar al usuario legítimo).

## Correcciones de verificación

- **Embeddings ligeros NO son "inspección de contenido sin leer contenido".** Calcular un
  embedding del prompt *es* procesar el contenido. La honestidad correcta: el metadata-monitor
  procesa el prompt para una señal de causa, pero **no lo retiene ni lo perfila**; el
  contenido se referencia por hash en el log. La distinción real no es "metadata vs
  contenido" sino "señal efímera no retenida vs inspección registrada contra lista cerrada".
  Redactar la promesa al usuario en esos términos, no como "no miramos tu contenido".
- La evasión por prompts sutiles (que el propio chat detectó como fallo) es inherente: el
  monitor barato tiene falsos negativos. Es aceptable porque el eje no es detección perfecta
  sino **causa registrada y campaña encarecida** (I4), no muro.

## Criterios de compuerta

1. **Verificable**: corregida la promesa "metadata vs contenido"; el esquema de dos niveles
   es estándar y honesto si se redacta bien.
2. **Coherente**: I2 (causa registrada) + I3 (no perfilar); comparte cómputo con [[OSM-001]].
3. **Probado**: test de que sin causa no hay entrada `inspected=true` y de que la causa
   siempre precede a la inspección de contenido.
4. **Mantenible**: embeddings ligeros podrían ir en Rust ([[OSM-029]]); la lista cerrada es
   gobernada, no un modelo opaco.
5. **Sancionado**: cambios en la lista cerrada de abusos pasan por PDP (I5).

## Compuerta de causa implementada (2026-06-19) — `DriftTripwire`

El "metadata-monitor-first" de esta OSM se realiza como **tripwire de deriva de sesión**
(`src/atlas/security/drift.py`), no como un clasificador de ataques. Decisión: NO se abre OSM
nueva; este componente ES la compuerta de causa que esta OSM presuponía y el productor del
`confidence` que [[OSM-042]] (ShadowRouter) consumía a 0.0.

- **Qué hace**: por turno extrae 4 features baratos (entropía de Shannon, distancia coseno al
  centroide rodante de la *propia* sesión, densidad de triggers de jailbreak, delta de
  longitud), agrega con EWMA + change-point z-score, y emite `confidence∈[0,1]` + `cause`.
  Compara la sesión consigo misma (no con un modelo global de ataques → sortea "cada uno
  ataca distinto").
- **2 en 1 (estadístico + embedding)**: el embedding es un `Embedder` inyectable (Protocol de
  `atlas.memory.embeddings`); v0 usa `StubEmbedder` (cero deps nuevas, regla 6); swap a
  `LiteLLMEmbedder` da más señal sin cambiar interfaz.
- **I3 (no perfilar)**: `DriftSessionState` es 100% numérico; nunca retiene el texto del turno.
  Testeado con marcador único.
- **I2 (causa registrada)**: al cruzar umbral, `cause` nombra la feature + z-score, lista para
  que el gateway la registre en el log.
- **Cold-start fail-open**: < N turnos → `confidence=0.0` → NORMAL. Es un tripwire que GATEA
  escalada, no un bloqueador.
- **Desacople**: `gateway.py` NO importa `drift.py`; el wiring es opt-in (el caller deriva el
  confidence y lo pasa a `gateway.call(confidence=...)`).

**Postmortem (corrección de calibración, 2026-06-19):** la primera versión saturaba
`confidence=1.0` en el primer turno puntuado de CUALQUIER sesión benigna — la varianza EWMA
casi-cero del arranque hacía explotar el z-score (suelo `1e-9`). Los unit tests no lo
cogieron porque el test de estabilidad usaba turnos *idénticos* (varianza 0 irreal). Un smoke
en runtime con variación benigna natural lo destapó. Fix: suelo de std físico `_MIN_STD=0.05`
(las features están en [0,1]). Tras el fix, separación limpia verificada en smoke: benigno
≤0.43, variación natural ≤0.28, homogéneo 0.02, giro adversarial 0.88–0.95. Regresión añadida
(`test_benign_natural_variation_does_not_false_positive`).

**Cause→log cableado (2026-06-19) — nivel 2 cerrado.** `gateway.call()` acepta ahora
`monitor_cause: str` (además de `confidence`). Cuando la señal escala la sesión, la causa
feature-level del monitor se COMPONE en `InspectionRecord.cause` (`"{routing.cause}; monitor=..."`)
y se commitea al log Merkle ANTES de la llamada al modelo (I2: causa registrada y precede a la
inspección). El gateway sigue SIN importar `drift.py` (recibe la string ya computada por el
caller; test `test_gateway_does_not_import_drift` verifica las líneas de import). Tests:
`test_monitor_cause_recorded_in_log` (la causa aparece en el leaf del log) y
`test_monitor_cause_ignored_when_no_escalation` (sin escalada no se inyecta causa espuria).

**Sigue pendiente (nivel 3, no bloqueante)**: la *inspección de contenido acotada contra lista
cerrada* tras registrar la causa (`AttestedInspector` enchufado a este flujo). Hoy la causa
escala a shadow/honeypot; la inspección gobernada contra lista cerrada es trabajo posterior.

## Límites honestos

- **Falsos negativos del monitor barato**: ataques sutiles pasan la compuerta de causa. Por
  diseño; lo cubre la métrica de campaña, no la detección por intento.
- **Coste de embeddings en todas las peticiones**: no nulo aunque sea ligero; es parte del
  coste que asume el proveedor ([[OSM-024]]).
- **Definir "causa" es político**: el umbral y la lista cerrada son decisiones gobernadas;
  un umbral mal puesto reintroduce inspección masiva encubierta.
