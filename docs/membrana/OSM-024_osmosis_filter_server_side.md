# OSM-024 — Osmosis Filter: capa de cumplimiento server-side obligatoria

Fecha: 2026-06-17 · Estado: **En membrana** (gateway implementado; enforcement no-bypass = política pendiente) ·
Origen: `idea avance 3.md` · Contexto: ADR-051 (Compliance Gateway), ADR-053 (completitud),
ADR-054 (defensa en profundidad), `src/atlas/transparency/`.

> OSM padre del chat 3. Las OSM-025..030 son sus mecanismos. Reencuadra el Compliance
> Gateway de "log externo opcional que adoptáis" a "capa de cumplimiento en el path".

---

## Contexto

ADR-051/053/054 describen el gateway como algo **externo y opcional** que un proveedor
podría adoptar. La carta lo dice explícitamente: "no propongo interponer un binario externo
en el path de vuestro modelo". El chat 3 da el giro contrario y deliberado: el cumplimiento
verificable solo es real si el filtro **está en el path y no se puede apagar**.

El argumento del usuario: *el que necesita la seguridad es la empresa, no el usuario*. Por
tanto el coste y la obligatoriedad recaen en el proveedor, no en el cliente. Un filtro que
el usuario instala y puede desactivar no protege a nadie ni defiende legalmente al
proveedor (ver [[OSM-030]]).

## La idea

**Osmosis Filter** = capa de cumplimiento que corre 100% en la infraestructura del
proveedor del modelo, **siempre encendida y obligatoria**:

- **Server-side**: no es un proxy del usuario. Corre donde corre el modelo.
- **Always-on / no-bypass**: modelo Secure Enclave del iPhone — *si no está el filtro, no
  hay servicio*. No es un modo que el operador active a discreción; es parte del arranque.
- **Coste asumido por el proveedor**: monitor ligero, embeddings, log. El usuario solo
  obtiene una clave (ver [[OSM-025]]) y la capacidad de verificar.
- **El path**: usuario → firma automática → Osmosis (polimorfismo → monitor por causa →
  inspección acotada → log Merkle) → modelo → respuesta + prueba de completitud.

No reemplaza el clasificador del proveedor (CC++). Lo envuelve con verificabilidad mutua:
el regulador ve cada abuso bloqueado; el usuario prueba que no fue inspeccionado sin causa.

## Encaje en Atlas

- **Capas (ADR-054)**: Osmosis es el empaquetado server-side de las 5 capas. Capa 1 (filtro)
  + Capa 2 (polimorfismo, [[OSM-028]] monitor por causa) + Capa 4 (log de campaña) + Capa 5
  (memoria inmune). El "modo obligatorio" es nuevo respecto al ADR-054.
- **Núcleo**: `src/atlas/transparency/` (log, merkle_tree, attestation) es el corazón ya
  construido. Osmosis lo expone como servicio en-path, no como librería opcional.
- **Invariantes**: respeta I2 (todo disparo se registra) e I3 (la memoria aprende de
  ataques, no del contenido del usuario legítimo). El "no-bypass" es una política nueva que
  habrá que volver invariante propio si cruza la membrana.

## Correcciones de verificación

- "Always-on / romper la cadena apaga el servicio" es una **decisión de enforcement de
  producto**, no una garantía criptográfica. Se sostiene por política + arquitectura, no
  por SHA-256. Documentarlo así evita el overclaim que ya señaló el premortem del propio
  chat 3.
- El giro a "en el path" **contradice la carta actual**. Si esta OSM cruza, la carta y
  ADR-051/053/054 se reescriben (fase posterior, decisión ya tomada: "Osmosis gana el pitch").

## Criterios de compuerta

1. **Verificable**: el mecanismo de completitud (ADR-053) ya está probado; lo nuevo es la
   postura, que es verificable como diseño, no como afirmación factual.
2. **Coherente**: respeta I2/I3; introduce la política no-bypass (candidata a invariante).
3. **Probado**: requiere una demo E2E del path completo (pendiente; bloqueante para cruzar).
4. **Mantenible**: reusa `transparency/`; no añade deps en el núcleo (Rust es [[OSM-029]]).
5. **Sancionado**: el reencuadre del pitch es decisión de producto del usuario, ya tomada.

## Límites honestos

- **Incentivo de adopción**: ningún proveedor mete hoy un filtro obligatorio en su path por
  iniciativa propia. El motor de adopción real es regulatorio (EU AI Act) + escudo legal
  ([[OSM-030]]), no técnico.
- **Latencia en el path**: inspección en todas las peticiones añade coste; mitigable con
  monitor-por-causa ([[OSM-028]]) y Rust ([[OSM-029]]), no eliminable.
- **Split-view sigue abierto** sin witnesses; la doble copia ([[OSM-026]]) lo mitiga
  parcialmente.
