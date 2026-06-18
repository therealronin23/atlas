# OSM-028 — Inspección por causa: metadata-monitor-first

Fecha: 2026-06-17 · Estado: **En membrana** (`AttestedInspector` + `cause=` en gateway implementados; metadata-monitor-first completo pendiente) · Origen: `idea avance 3.md` ·
Contexto: ADR-053 (causa registrada), ADR-054 (capa 1), `src/atlas/transparency/attestation.py`
(`AttestedInspector`), [[OSM-001]] (métrica de campaña), [[OSM-024]].

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

## Límites honestos

- **Falsos negativos del monitor barato**: ataques sutiles pasan la compuerta de causa. Por
  diseño; lo cubre la métrica de campaña, no la detección por intento.
- **Coste de embeddings en todas las peticiones**: no nulo aunque sea ligero; es parte del
  coste que asume el proveedor ([[OSM-024]]).
- **Definir "causa" es político**: el umbral y la lista cerrada son decisiones gobernadas;
  un umbral mal puesto reintroduce inspección masiva encubierta.
