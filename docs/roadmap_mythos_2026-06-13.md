# Roadmap Mythos — del arnés verificable al constructor (2026-06-13)

Sesión estratégica (Tomás + Claude). Este documento ordena la ambición
original de Atlas ("rey del enjambre", "exoesqueleto que multiplica cualquier
IA", "mythos en potencia") contra la arquitectura real de hoy, y traza el
orden de construcción. No duplica counts ni claims vivos — para eso,
`atlas reality --json`.

## Tesis del orden

Atlas no se "convirtió" en auditor. Construyó primero **lo que hace posible
al constructor**: un generador que no sabe distinguir un buen artefacto de
uno malo no es un rey, es ruido a escala. La verificación es la parte difícil;
la generación, la fácil. La mayoría de proyectos lo hacen al revés y mueren
ahogados en output no verificable. El orden de Atlas es el correcto.

El exoesqueleto dibujado **ya existe**: es la capa 2 (`router/cascade.py`,
ADR-042) sobre el seam de capa 1 (`core/verify.py`, ADR-041). "Multiplicar
cualquier IA, local o vía API" es la cascada de productores. Lo que falta no
es arquitectura nueva: es **densidad** sobre la base que ya está.

## Dónde estamos (verificable, no narrado)

- Base sellada 2026-06-12 (`docs/direction_2026-06-12_construir_hacia_arriba.md`).
- Capa 1 — verificador universal `verify(artifact) → Evidence` (ADR-041).
- Capa 2 — cascada con routing por dificultad/verificabilidad (ADR-042),
  cableada al codegen con evidencia en Merkle.
- Estado vivo siempre por `atlas reality`; nada se declara "listo/sellado/
  live" sin evidencia local.

## Eje A — Densidad sobre la base (corto plazo, sin arquitectura nueva)

Cada capacidad nueva es un `ArtifactKind` + su verificador más barato que el
productor. No son sistemas nuevos; son entradas en el registro existente.

| Artefacto | Verificador barato | Estado |
|---|---|---|
| `CODE` | ASTGuard (STATIC) + sandbox (SANDBOX) | hecho |
| `PATCH` | UnifiedDiffVerifier (STATIC) + suite (SUITE) | hecho |
| `WASM` | validación del módulo (wasmtime/wasm-validate) + ejecución en sandbox WASI | pendiente |
| `BINARY` | comprobaciones estáticas (formato, símbolos) + ejecución contenida | pendiente |
| `CONFIG` | schema/lint declarativo (STATIC) | pendiente |
| `PROOF` | re-chequeo del proof (más barato que generarlo) | pendiente (puente a seL4) |
| `SECURITY_FINDING` | reproducción del PoC en sandbox (ADR-043) | propuesto |

"Software líquido" = uno o varios de estos `ArtifactKind` con su verificador.
No requiere reescribir nada.

## Eje B — Vertical de seguridad ofensivo-defensiva (ADR-043)

Principio: **para defender hay que saber atacar.** Atlas custodia datos de
máxima sensibilidad (bufetes, clínicas, gestorías) y no puede tapar un vector
que no sabe que existe. El conocimiento es ilimitado (todo CVE, paper de
exploitation, writeup de CTF, técnica conocida). Lo que se gobierna no es el
*saber*, es el *disparar*.

Distinción de diseño (no solo ética — propiedad de ingeniería):

- **Sin límite**: análisis estático/dinámico, fuzzing dirigido, reproducción
  de exploits en laboratorio, modelado de amenazas, anticipación de vectores
  futuros — contra targets **propios o con autorización explícita**.
- **Gobernado**: toda acción ofensiva *activa* contra un target porta una
  **prueba de autorización verificable** (scope firmado: rango de IPs propio,
  consentimiento de cliente, dominio controlado). Sin grant válido, no se
  dispara. Mismo patrón que el decider/PDP: no es "humano dice no", es "no hay
  evidencia de autorización".

Por qué el límite no resta poder: un Atlas que ataca *cualquier* máquina sin
gobierno deja de ser caja fuerte y pasa a ser ganzúa universal con los
secretos del usuario dentro. Comprometerlo heredaría esa capacidad apuntando
al propio usuario y a sus clientes. La contención es la armadura que lo hace
confiable para datos sensibles, no la jaula que lo limita.

Piezas (detalle en ADR-043):

1. `AuthorizationGrant` — scope firmado y verificable (target × clase de
   capacidad × expiración).
2. `AuthorizationVerifier` — gate sobre acciones ofensivas activas; deniega
   sin grant que cubra (target, capacidad). Loguea a Merkle.
3. `SECURITY_FINDING` ArtifactKind — hallazgo + reproducción del PoC en
   `LayeredIsolationSandbox` como su propio verificador (reproducir es más
   barato que descubrir: verificación asimétrica aplicada a seguridad).
4. Harness de fuzzing/PoC en sandbox contra targets autorizados.

## Eje C — Las capas 3 y 4 ya en el rumbo

- **Capa 3 — Enjambre sobre blackboard**: N workers en worktrees aislados,
  coordinados por artefactos verificables, no por contexto compartido. El
  decider asigna envelopes (presupuesto, dominio, duración), audita por
  muestreo + Merkle. Primer enjambre: el más aburrido posible (3 workers de
  mantenimiento del repo, una semana sin intervención) — porque ahí lo que se
  prueba es la **maquinaria de coordinación**, no la inteligencia de los
  workers; todo fallo es señal limpia de coordinación. Reto técnico abierto:
  N escritores vs `MerkleWriterLock` (single-writer).
- **Capa 4 — LessonStore**: cada postmortem/fallo de tick/patch rechazado →
  entrada tipada (heurística + test de regresión + patrón a evitar). Convierte
  tiempo en ventaja compuesta. Es pequeña y alimenta a la 3.

## Horizonte largo — seL4 y artefactos con prueba

seL4 no es el final del mismo camino: es un **cambio de naturaleza**. Hoy la
frontera de confianza de Atlas es defensa en profundidad (process_hardening,
sandbox, Sentinel) sobre un kernel que no controla. Un microkernel con
verificación formal daría garantías **demostradas**, no testeadas.

El puente no es reescribir Atlas en C sobre seL4. Es que la capa 1
(verificación asimétrica, evidencia tipada) es conceptualmente el mismo
principio que la prueba formal: una verificación más barata que lo que
verifica. Si Atlas aprende a emitir y consumir `PROOF` (no solo tests), el
salto a un sustrato formal pasa de rewrite a **cambio de backend**. Es a años,
y está bien que lo sea.

## El listón (falsable)

Atlas deja de ser "prometedor" el día que produzca de forma autónoma un
resultado objetivamente mejor que el usuario + un frontier en una sesión. El
"modo dios" no es omnipotencia: es **capacidad máxima verificada** — la única
forma de poder que sobrevive al escrutinio, capacidad afilada sin punto ciego.

## Orden propuesto

1. Cerrar lo operativo en vuelo (timeout de reality configurable, commit del
   bump `rich` autónomo huérfano, unidad systemd para la auditoría larga).
2. Capa 4 (LessonStore) — pequeña, alimenta a la 3.
3. Capa 3 (enjambre aburrido) — la semana falsable.
4. ADR-043 (autorización verificable + `SECURITY_FINDING`) — abre la vertical
   de seguridad sin romper nada.
5. Densidad de `ArtifactKind` (WASM/binarios/config/proof) según necesidad.
6. Horizonte: `PROOF` carrying → evaluación de sustrato formal.
