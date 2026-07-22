# T4.2 — Pipeline candidata→diseccionada→absorbida (industrializado)

Cierra `docs/design/atlas_master_plan.md` §5 T4.2: *"Pipeline candidata→diseccionada→
absorbida industrializado (T0.4 da el mapa; esto da el músculo). Primera víctima: cipher
(rol aún sin decidir — disección adopt-real y veredicto). Evidencia: informe de
disección + entrada en el mapa con estado."*

Estado: **v1, aplicado de verdad** contra el lote real de 33 documentos que T0.5b paso 3
clasificó `candidata` (`docs/design/2026-07-22-t05b-paso3-sintesis.md` §0,
`docs/knowledge/t05b_paso3/corpus_digest_consolidated.json`). No es un diseño en el
vacío — la §2 de este documento ES la aplicación, con veredicto de una línea por cada
uno de los 33 y disección completa de los 2 que resultaron ser candidatas reales.

## 0. Qué NO es este pipeline (límites explícitos, ya decididos antes de hoy)

Dos decisiones previas de esta misma sesión maratón acotan el diseño y evitan
reinventar vocabulario que ya existe:

1. **No introduce una taxonomía/ciclo-de-vida nuevo.**
   `docs/superpowers/specs/2026-07-15-succession-ecosystem-design.md` §5 ya evaluó y
   **descartó formalmente** una columna `Tramo` y el ciclo `candidata→diseccionada→
   absorbida→vigente→aparcada` propuesto en la spec original de T4.2, con la razón
   correcta: duplica casi 1:1 el `State` que `atlas_ecosystem_map.md` ya usa
   (`PENDIENTE`≈candidata/diseccionada, `ACTIVO`≈vigente, `PARK`≈aparcada,
   `SELLADO`≈absorbida-cerrada). Este pipeline reutiliza el `State` real; "candidata",
   "diseccionada" y "absorbida" son aquí **verbos de proceso** (qué hace el pipeline en
   cada fase), no columnas nuevas del mapa.
2. **No es la membrana OSM (`docs/membrana/OSM-000_membrana.md`).** La auditoría cruzada
   de T0.5b (`docs/knowledge/t05b_paso3/audit_D.json`, nota sobre T4.2/cipher) marcó el
   riesgo real de que este pipeline duplicase OSM-000 sin citarlo. Distinción de alcance,
   explícita para que no vuelva a pasar: OSM-000 disciplina **ideas/técnicas/papers** que
   aspiran a convertirse en un ADR del núcleo (ciclo Suspensión→Difusión→En
   membrana→Absorbida/Rechazada, con compuerta de 5 criterios). T4.2 disciplina
   **software externo concreto** (repo real, licencia real, binario o proceso que se
   puede clonar/ejecutar) que aspira a una fila en `atlas_ecosystem_map.md` con Taxonomy
   `Capability`/`Adapter`/`External Service`/`Absorbed Pattern`. Si algún día un
   candidato de software necesita además una decisión de arquitectura, cruza a OSM/ADR
   por el mecanismo ya existente — T4.2 no lo sustituye.

## 1. Las 4 fases

### Fase 1 — Intake

Entrada: cualquier documento marcado `candidata` por la digestión T0.5b (o, en
adelante, cualquier documento nuevo que entre por `docs/inbox/` y que el triage de
`AGENTS.md`/T0.5.c no resuelva como `alimenta_item`/`historico`/`gap`). No se inventan
candidatas fuera de este flujo — el maestro §6 ya es claro: "las ideas nuevas... entran
SIEMPRE por `docs/inbox/` → triage".

### Fase 2 — Triage (barato, determinista donde se pueda)

Cuatro preguntas, en orden, cada una resuelve la mayoría del lote sin necesitar lectura
profunda ni disección:

- **Q1 — ¿Describe software externo real** (repo, paquete, servicio, binario — algo con
  licencia propia y ciclo de vida fuera de este repo) **o es contenido propio de Atlas**
  (gobernanza, producto, visión, ADR, protocolo interno, nota de investigación *sobre*
  algo, no el algo mismo)? La inmensa mayoría de los "candidata" de T0.5b son lo
  segundo — el clasificador de T0.5b usó "candidata" en un sentido más amplio
  ("posible entrada nueva a algún tramo") que el sentido estricto de T4.2 ("pieza de
  software para disección adopt-real"). Si NO → **veredicto: sin acción, referencia o
  gobernanza**, fin del triage para ese doc.
- **Q2 — Si Q1 es sí: ¿es un "reference dossier" plantilla** (mismo texto boilerplate
  repetido, apunta a una matriz de asimilación compartida, sin contenido único) **que ya
  fue consumido** (informó una decisión pasada, verificable por grep contra el texto de
  esa decisión)? Determinista: mismo hash de estructura en varios ficheros del mismo
  directorio (`research/references/*.md`) es la señal barata. Si sí → **veredicto: ya
  consumida, sin acción** (evidencia: dónde se usó).
- **Q3 — ¿Ya tiene fila en `atlas_ecosystem_map.md`** (grep por nombre) **o el trabajo
  de disección ya vive en otro documento vigente** (p.ej. otro ADR, otro pack de
  absorción)? Determinista por grep. Si sí → **veredicto: ya diseccionada/mapeada, sin
  fila nueva** (evidencia: fila o ADR existente; si la fila está desactualizada, eso es
  una corrección mecánica, no una disección nueva).
- **Q4 — Si sobrevive Q1-Q3: ¿hay evidencia verificable en disco** (repo clonado con
  `git remote`, commits reales, no solo un nombre mencionado de pasada) **de intención
  de absorción real**? Si sí → pasa a Fase 3 (disección completa). Si no (se menciona el
  nombre de una herramienta pero no hay ni intención de clonarla ni repo) → **veredicto:
  candidata nominal, aparcada sin disección** (se registra el nombre, no se inventa
  esfuerzo de integración que no existe).

Coste: Q1-Q3 se resuelven con `head`/`grep` sobre el propio documento y sobre el mapa —
sin LLM de por medio salvo para juzgar Q1 en el puñado de casos ambiguos. Esto es
deliberado: barato y determinista donde se puede, igual que `sanitation_audit.py` y
`ecosystem_drift.py`.

### Fase 3 — Disección (adopt-real, solo para lo que sobrevive el triage)

Plantilla fija, mismas preguntas que ya se usaron para Hermes/Crawl4AI/Stirling
(`docs/design/absorption_master_plan.md`), formalizadas aquí:

1. **Qué es** — una frase, qué problema resuelve, quién lo mantiene.
2. **Licencia** — identificador SPDX real, verificado leyendo el fichero `LICENSE*` del
   repo clonado, no memorizado ni asumido.
3. **Evidencia en disco** — ruta del clon/fork, `git remote -v`, commits/ramas propias de
   Atlas encima del upstream (si las hay), estado de compilación si se probó.
4. **Coste de integración** — líneas/ficheros ya tocados, tests reales que lo cubren, lo
   que falta para pasar de "compila y arranca" a "vigente en el producto".
5. **Rol propuesto** — Taxonomy de `atlas_ecosystem_map.md` que le correspondería
   (`Capability`, `Adapter`, `External Service`, `Absorbed Pattern`...).
6. **Riesgos** — licencia (copyleft fuerte vs permisiva), mantenimiento del upstream
   (¿vivo o congelado?), deriva de versión.

### Fase 4 — Veredicto → entrada en el mapa

El veredicto de la disección es siempre uno de los `State` **ya existentes** del mapa
(`SELLADO`, `ACTIVO`, `PENDIENTE`, `PARK`, `VAPOR`, `MURO`) — nunca un estado nuevo. La
fila que se añade sigue exactamente el formato de columnas ya vigente (`Item | Taxonomy
| State | Evidence | Authority | Relationship to Atlas | Next action`), igual que la fila
de referencia de Crawl4AI/Stirling PDF. Esto cierra el ciclo: intake → triage → disección
→ veredicto → fila real, sin inventar aparato nuevo, cumpliendo la "Operating Rule" ya
escrita al pie del propio mapa ("New work must add or update one row here before adding
another roadmap item").

## 2. Aplicación real contra el lote de 33 `candidata` de T0.5b

Resultado del triage (Fase 2) sobre los 33 documentos. Detalle completo (razón de una
línea por documento) en el informe de esta sesión — aquí el resumen accionable:

- **31/33 → sin acción** (Q1 = no, o Q2/Q3 resuelven que ya está consumido/mapeado).
  Desglose: 7 son "reference dossiers" plantilla ya consumidos (Q2) —
  hugginggpt_jarvis, jarvis_desktop, langgraph, n8n, obsidian_skills, odysseus,
  openjarvis; el resto son gobernanza/producto/visión/ADR/operación propios de Atlas
  (Q1 = no) — manifiesto y non-goals del build_pack, constitución/CRM/software líquido
  del pack Product OS, ADR-051/054, política AGPL, USAGE.md, disciplina de código,
  Cónclave portable, auditorías internas (postmortem memoria, self-audit loop),
  OPEN_QUESTIONS, product_strategy_notes, project_needs_inventory (inventario de
  gobernanza que ya apunta a herramientas cubiertas por ADR-056, no una pieza única),
  CONTROL_PLANE, plan MCP/murallas (ciclo ya cerrado), sector Investigación, visión
  microkernel (idea de producto, no software).
- **2/33 → candidatas reales, pasan a disección** (Q4 = sí, evidencia verificable en
  disco): el fork de **Void** y el fork de **Zed** para "Atlas IDE", ambos descritos en
  `docs/design/ui/void_fork_ux_fusion_inventory_2026-07-18.md`. Es el único de los 33
  documentos que describe software externo con repo real clonado, commits propios de
  Atlas encima, y ausencia confirmada de fila en el mapa (drift real, no falso positivo:
  `docs/design/absorption_master_plan.md` línea ~142 ya cita el precedente "Void... y
  Zed... para el Atlas IDE" sin que ninguno tenga fila).

Tabla de triage completa (33/33) y disección completa (2/2) en el resumen final de esta
sesión (mismo texto, no se duplica aquí para no desincronizar dos copias).

## 3. Cómo se reusa este pipeline

Este documento es el proceso repetible que pedía T4.2 — el próximo lote `candidata` que
salga de una digestión T0.5.c (o cualquier documento nuevo de `docs/inbox/` que el
triage marque como posible pieza de software) se procesa con las Fases 1-4 de arriba sin
rediseñar nada. La "primera víctima" nombrada en el plan maestro era `cipher`, pero
`cipher` no aparece en ninguno de los 33 documentos de este lote (confirmado por grep) —
sigue pendiente de intake propio cuando el operador decida traerlo a disección; este
documento deja el músculo listo para cuando llegue.
