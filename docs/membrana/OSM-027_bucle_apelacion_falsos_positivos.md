# OSM-027 — Bucle de apelación de falsos positivos con aprendizaje

Fecha: 2026-06-17 · Estado: **Difusión** (ver [[OSM-000]]) · Origen: `idea avance 3.md` ·
Contexto: ADR-040 (Decider/PDP), ADR-044 (LessonStore), ADR-049 (organismo de conocimiento),
`src/atlas/immunity/`, [[OSM-024]].

---

## Contexto

Un filtro obligatorio en el path ([[OSM-024]]) que bloquea por causa genera **falsos
positivos**: escritores de ficción, investigadores, roleplay legítimo. Sin una vía de
reparación rápida, el filtro es inaceptable para el usuario y un riesgo legal para el
proveedor. El usuario lo planteó como: el usuario reporta → un filtro IA verifica → si es
falso positivo real, recupera la cuenta automáticamente; si no, escala a un humano; con el
tiempo aprende y los falsos positivos disminuyen.

## La idea

Un lazo de apelación con cuatro pasos, todos registrados en el log:

1. **Reporte**: el usuario marca un bloqueo como falso positivo. El reporte queda atado a la
   secuencia firmada ([[OSM-025]]) de la petición bloqueada.
2. **Filtro IA**: un verificador automático re-evalúa el caso contra la lista cerrada de
   abusos ([[OSM-028]]). Si claramente fue falso positivo → **auto-restauración** inmediata.
3. **Escalado al PDP**: si hay duda, escala a un decisor (ADR-040). El humano es *una*
   implementación del PDP, no el path fijo — coherente con el rumbo del proyecto.
4. **Aprendizaje**: el resultado alimenta el LessonStore (ADR-044). Patrones de falso
   positivo confirmados ajustan el monitor por causa; el organismo (ADR-049) inyecta el
   patrón. Con el tiempo, menos falsos positivos.

## Encaje en Atlas

- **PDP (ADR-040)**: el escalado usa el Decider existente (`Allow | Deny | RequiresHuman`).
  La auto-restauración es un `Allow` del filtro IA bajo política; el escalado es `RequiresHuman`
  con decisor intercambiable.
- **LessonStore (ADR-044) + organismo (ADR-049)**: el lazo de aprendizaje ya existe; esta OSM
  lo conecta a la señal de falso positivo, que hoy no se captura.
- **Invariante I3**: el aprendizaje es sobre *patrones de decisión* (falso positivo), no sobre
  el contenido del usuario legítimo — hay que diseñarlo para no violar I3 (ver corrección).

## Correcciones de verificación

- **Riesgo de violar I3.** "Aprender de falsos positivos" no puede significar almacenar el
  contenido legítimo del usuario para entrenar. La lección debe ser sobre el *patrón de
  causa que disparó mal* (la heurística), no sobre el prompt del usuario. El contenido se
  referencia por hash, no se retiene. Diseñar la lección a nivel de heurística, igual que la
  afinidad maduración ya hace con patrones de defensa.
- "Recupera la cuenta automáticamente" debe tener **límite anti-abuso**: un atacante real
  apelará en masa. El filtro IA necesita su propia métrica de campaña (I4) sobre las
  apelaciones, no solo sobre las peticiones.

## Criterios de compuerta

1. **Verificable**: el lazo reusa PDP + LessonStore probados; la novedad es el cableado.
2. **Coherente**: respeta I3 (aprender de heurística, no de contenido) e I5 (promoción de
   ajuste vía PDP). El humano sigue siendo PDP intercambiable, no acople fijo.
3. **Probado**: requiere test de los cuatro caminos (auto-restaura / escala / aprende / abuso).
4. **Mantenible**: sin deps nuevas; usa immunity + governance existentes.
5. **Sancionado**: cada ajuste del monitor por causa pasa por el PDP (I5).

## Límites honestos

- **Latencia de reparación**: el escalado humano puede ser lento; la promesa "auto-restaura
  si es falso positivo claro" solo cubre los casos obvios.
- **Equilibrio FP/FN**: bajar falsos positivos sube el riesgo de falsos negativos. El lazo
  optimiza, no resuelve, esa tensión.
- **Carga del humano**: en volumen, el escalado puede saturar; depende de que el filtro IA
  resuelva la mayoría.
