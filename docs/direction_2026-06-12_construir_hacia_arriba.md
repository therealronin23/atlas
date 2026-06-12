# Dirección 2026-06-12 — Sellar la base, construir hacia arriba

Sesión estratégica (Tomás + Claude). La base defensiva queda sellada; lo que
sigue es capacidad. Este doc captura el porqué y el orden, no el cómo — el
cómo se decide ADR a ADR cuando toque construir cada pieza.

## Tesis

Atlas no compite con los labs en razonamiento bruto: se apalanca sobre sus
modelos y construye lo que un lab no tiene permiso ni incentivo para dar:

1. **Memoria que es del usuario** — contexto verificado que compone con el
   tiempo, no sesiones amnésicas.
2. **Autonomía gobernada real** — operar días sin supervisión bajo evidencia
   y auditoría, el régimen que los productos de lab tienen vedado.
3. **Profundidad vertical** — optimizado para un usuario y sus dominios, no
   para el percentil 50 de millones.

"Modo dios" = **máxima capacidad verificada** (postmortem 2026-06-12), nunca
ejecución ilimitada. Un sistema que miente sobre su readiness es más débil
que uno que dice "unknown".

## Base sellada (criterios cumplidos hoy)

- `atlas reality --strict` como gate de arranque (verdad generada, no afirmada).
- Matcher de corroboración sin hueco de tokens genéricos.
- CI de browser/computer-use requerido.
- Audit de 24h sobre `ATLAS_HOME` aislado, con abort si apunta al vivo.
- Single-writer guard sobre la cadena Merkle (ROADMAP §7, `MerkleWriterLock`).

Desde aquí, la base solo se refuerza **por evidencia de incidente**, no por
ansiedad. La proporción de esfuerzo se invierte: de ~80% inmune / 20%
capacidad a lo contrario.

## Las cuatro capas (orden de construcción, cada una usable antes de la siguiente)

1. **Verificador universal** — un seam `verify(artifact) → evidencia` que
   unifica lo que ya existe (sandbox, suite, ValidationRunner, proof
   artifacts). Principio rector: **ningún resultado sube sin un verificador
   más barato que su productor** (verificación asimétrica). Todo lo demás se
   construye encima.
2. **Cascada con routing** — el decider clasifica cada tarea por dificultad y
   verificabilidad: lo mecánico-verificable baja a modelos pequeños/locales,
   lo difícil sube a frontier vía API. Nada sube sin pasar por la capa 1.
   Métrica de éxito: coste por resultado verificado.
3. **Enjambre sobre blackboard** — N workers en worktrees aislados,
   coordinados por artefactos verificables (`reality` + repo + cola de
   propuestas), nunca por contexto compartido. El decider asigna **envelopes**
   (presupuesto, dominio, duración) y audita por muestreo + Merkle — decide
   políticas, no acciones, o se convierte en el cuello de botella (HITL con
   otro nombre). Primer enjambre: el más aburrido posible — 3 workers de
   mantenimiento del propio repo, una semana sin intervención.
4. **LessonStore** — cada postmortem, fallo de tick o patch rechazado se
   convierte en entrada tipada (heurística de detección + test de regresión +
   patrón a evitar) que el Analyst y el codegen cargan como contexto. Es la
   capa que convierte tiempo en ventaja compuesta. Ejemplos ya vividos: el
   matcher que nunca corroboraba (primer tick), el doble escritor Merkle
   (hoy), la suite recursiva (hoy).

## Principios transversales

- **Disenso calibrado como función principal**: Atlas debe quitarle la razón
  al usuario — con evidencia, alternativa y grado de confianza explícito.
  Generalización del gate de corroboración a toda recomendación.
- **Scout de obsolescencia, no fork-everything**: vigilar papers/releases/
  consensos como *señal* que entra por el gate de corroboración. Una
  migración solo se propone con benchmark reproducible contra el código
  actual bajo la restricción del usuario, y blast radius declarado. Ante
  empate de evidencia, no se toca lo que funciona: la carga de la prueba
  recae en lo nuevo.
- **El humano conserva criterio**: el agente quita la razón, pero el usuario
  debe poder quitársela al agente. Si no puede, no hay copiloto sino piloto
  sin supervisar.

## El listón (falsable)

Atlas deja de ser "prometedor" el día que produzca de forma autónoma un
resultado objetivamente mejor que el que el usuario + un frontier harían en
una sesión: un bug real que nadie habría visto, un patch que pasa review sin
retoques, una semana de mantenimiento sin tocar nada. Si tras ~6 meses de
construir hacia arriba no ocurre, esa también es una respuesta — el
experimento es honesto porque se deja falsar.
