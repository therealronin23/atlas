# ATLAS — qué es hoy, de verdad, y qué le falta para ser mejor que Cursor/LangGraph

Escrito el 2026-07-11 tras cerrar los 3 ZIPs fuente + Fase 15/16, con el
operador sin tiempo para releer cientos de documentos. Este NO sustituye
`AGENTS.md` (identidad operativa) ni `docs/design/atlas_ecosystem_map.md`
(taxonomía) — los conecta con lo que Atlas OS añadió, en una página.

## Qué es Atlas hoy, de verdad (no aspiracional)

Un runtime de inteligencia LOCAL con tres capas reales:

1. **Sustrato** (preexistente, el núcleo): memoria (`atlas.memory`),
   auditoría Merkle inmutable, Tool Registry, InferenceHub (multi-
   proveedor con failover), cola de aprobaciones, y un lazo de
   **auto-mejora en frío** (`ColdUpdate`) que hoy mismo, sin supervisión,
   propone parches, los valida en un worktree aislado, y los mergea si
   pasan — verificado en vivo esta sesión (worktree de hoy ya mergeado
   limpio en `main`).
2. **Atlas OS** (nuevo, Fase 15/16): un Event Kernel real (bus de eventos
   con replay), un PolicyEngine con 7 invariantes duros en código (no en
   prompt), un Business Core draft-first, un Gate Engine con tickets
   auditables para decisiones humanas, y un primer conector real (Gmail,
   read-only). Todo esto comparte el MISMO sustrato Merkle del núcleo —
   no es un producto aparte.
3. **Arnés de validación** (`ui/atlas-shell`): una superficie web
   deliberadamente no-pulida para probar que lo de arriba funciona de
   punta a punta. No es la UX final — nunca se diseñó para serlo.

## En qué es genuinamente distinto de Cursor / LangGraph (verificado, no vendido)

- **Cursor** es un asistente de código dentro de un IDE: memoria y
  decisiones viven en la sesión, no hay auditoría estructural ni
  gobernanza de qué se le permite hacer a la herramienta.
- **LangGraph** es una librería para construir grafos de agentes: no
  tiene opinión propia sobre memoria persistente, gobernanza ni
  autoconstrucción — eso lo aportas tú por encima.
- **Atlas ya tiene, hoy, en código y probado**: (a) un único registro
  Merkle auditable compartido por TODO el trabajo (código, negocio,
  memoria, herramientas), no por sesión; (b) gobernanza como invariante
  de código (PolicyEngine, Gate Engine), no como prompt que se puede
  ignorar; (c) un lazo de autoconstrucción que ya mergea trabajo real sin
  supervisión, con validación aislada antes de aplicar; (d) una
  estrategia deliberada de NO reinventar lo que ya existe bien
  (Playwright, Crawl4AI, Stirling PDF, etc.) — absorber y envolver con las
  invariantes de Atlas, en vez de clonar.

Eso es una ventaja estructural real, no una promesa. **Lo que falta no es
más motor — es que se pueda VER, USAR y CONFIAR en ese motor.**

## Qué le falta para que se note (honesto, priorizado)

1. **Un frente único fácil.** Hoy Atlas se toca desde un CLI de 29
   comandos sin categorizar, un bridge FastAPI, y un shell web separado —
   tres puertas distintas. Se dio el primer paso hoy mismo (quick-start en
   `atlas --help`), pero falta una experiencia de entrada REAL de "aquí
   empiezas, esto es lo que puedo hacer por ti".
2. **Visibilidad del trabajo autónomo** (ADR-068: Dynamic Workflow Control
   Surface + Coding+Research Workbench). El motor de autoconstrucción
   funciona MECÁNICAMENTE — lo que no existe todavía es una vista donde
   el operador vea, sin leer logs ni worktrees a mano, qué está haciendo
   Atlas, por qué, y pueda pararlo o revertirlo con un clic.
3. **Confianza verificada en decisiones grandes.** Está probado que el
   lazo de autoconstrucción hace bien tareas pequeñas y mecánicas. No
   está probado (ni a favor ni en contra) que tome bien decisiones
   grandes sin supervisión — eso se audita con tiempo, no se asume.
4. **Menos documentos, más síntesis.** Este mismo repo es la prueba: hay
   cientos de ficheros de contexto/spec que documentan intención mejor de
   lo que documentan resultado. La disciplina que más ayudaría a partir de
   aquí no es escribir más — es que cada sesión nueva cierre algo antes de
   abrir algo nuevo (exactamente lo que esta sesión y la de Phase Recovery
   hicieron con los 3 ZIPs).

## Lo que NO haría falta para ser mejor

Más motores backend sin conector real que los use, más sectores
verticales sin demanda real, más ADRs de fases que nadie va a ejecutar en
semanas. La ambición de "ser mejor que Cursor y LangGraph" no se gana
añadiendo superficie — se gana haciendo que la superficie que YA existe
(sustrato + gobernanza + autoconstrucción real) sea fácil de tocar y fácil
de confiar. Ese es el criterio para decidir qué construir después, no el
tamaño de la lista de candidatos.
