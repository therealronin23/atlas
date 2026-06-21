# MCP Trunk portable — sistema de agente ordenado, accesible e instalable en cualquier sitio

<!-- Diseño (2026-06-21). Fuente original: volcado de exploración con Grok en
docs/archive/_graveyard/2026-06-21/scratch/mcp grok.md (crudo, se conserva como fuente). -->

## Qué es (y qué NO es)

**Es:** un MCP primario local ("tronco") que agrupa, ordena y expone como raíces MCP todo el
trabajo del usuario (memoria verificable, disciplina operativa, fuentes de conocimiento,
herramientas), de modo que con **una sola conexión** Claude/Codex/cualquier cliente MCP lo tenga,
**en cualquier proyecto y plataforma**. Objetivo declarado por el usuario: **orden + accesibilidad +
portabilidad** ("para ahora y el futuro, fácil de instalar en cualquier plataforma").

**NO es:** una arquitectura novedosa. El patrón tronco+raíces (agregador MCP) ya existe
(magg, 1mcp, mcgravity, StormMCP — *a verificar antes de adoptar*). **El moat no es la arquitectura;
es el CONTENIDO** que metemos dentro (sustrato verificable + disciplina) y la portabilidad de TODO
junto. Honesto: esto es packaging/distribución de lo ya construido, no una invención.

## Arquitectura: tronco + raíces

```
TRONCO (MCP primario local, una conexión)
  · franken-prompt modular por OBJETIVO → enruta a un subconjunto PEQUEÑO de raíces (anti-overload)
  · routing / aprobación / permisos centralizados
  └── RAÍCES (MCP independientes, catalogados por objetivo):
      1. memory        → NUESTRO sustrato verificable (SqliteMemoryIndex + procedencia Merkle +
                          abstracción + validez temporal/tiers). NO un knowledge-graph genérico.
      2. knowledge-src → APIs autoritativas libres (Wikipedia, NASA, datasets, bibliotecas…) como
                          tools → más rápido/barato que el navegador; alimenta el pipeline de Atlas.
      3. operating     → OPERATING LOOP + manías + WORK_LEDGER (advisory) + sanitation_audit (tool).
      4. governance    → REPO_STANDARD / CAPABILITIES como recursos.
      5. commodity     → filesystem, git, browser (off-the-shelf, no reinventar).
```

## La pieza fuerte (idea del usuario): knowledge-src → ingestión de Atlas

Una raíz de **fuentes de conocimiento verificable** (cientos de APIs libres: Wikipedia, NASA,
bibliotecas con millones de archivos…) como tools MCP. Ventaja real: **más rápido y barato que el
navegador**, con **procedencia** (sabemos de qué fuente y cuándo vino). Y el bucle que lo hace
único: ese conocimiento **lo absorbe Atlas** vía el pipeline que YA cableamos hoy
(`atlas.knowledge.run.run_mission` → `MissionRunner` → ingestión+verificación → sustrato). O sea:
knowledge-src (raíz MCP) → `run_mission` → memoria verificable. Es el organismo de conocimiento
(ADR-049) alimentado por MCP en vez de por scraping.
HONESTO: "conocimiento verificable" = **procedencia** (fuente+fecha), NO prueba de verdad; una
respuesta de API es una fuente con trazabilidad, no un hecho probado. El gate de verificación
(`KnowledgeVerifier`) ya filtra.

## El "franken-prompt" modular (system prompt por objetivo)

System prompt compuesto de módulos; cada módulo se asocia a un objetivo y a su subconjunto de
raíces/skills. Esto es a la vez la UX ("modo frontend", "modo research") y el **mecanismo
anti-overload**: el modelo ve pocas tools relevantes, no 200 de golpe (responde a la duda #5: el
problema del kitchen-sink no es el almacenamiento ni la velocidad de vectores, es **cuántas tools ve
el modelo a la vez**; routing por objetivo + lazy-loading lo resuelve).
LÍMITE DURO (mismo muro que el OPERATING LOOP): **MCP no puede IMPONER un system prompt.** Los
prompts MCP son plantillas que el cliente invoca, no system prompts obligatorios. El franken-prompt
debe entregarse por un canal de system-prompt REAL (wrapper/CLI/--append-system-prompt/hook del
cliente), no por la primitiva prompt de MCP. Si se vende como "control central del comportamiento"
sin ese canal, es overclaim.

## Lenguaje: Python ahora, Rust por-raíz después (sin big-bang)

El usuario quiere Rust pero tiene casi todo en Python. **Clave liberadora:** como cada raíz es un
**proceso MCP independiente**, el sistema es POLÍGLOTA — un tronco Python (FastMCP, reutiliza directo
nuestro sustrato Python) puede agregar raíces en Rust más adelante, **una a una** (reescribir solo
las raíces calientes en `rmcp`). No hay "llorar sangre": no es una migración big-bang, es incremental
por raíz. Recomendación: **Python primero** (máximo reuso de lo de hoy); Rust cuando una raíz
concreta lo justifique por performance.

## Límites honestos (declarar siempre)

- Arquitectura = commodity; el valor es contenido + portabilidad.
- System prompt NO imponible vía MCP (necesita canal real de system-prompt).
- "Conocimiento verificable" = procedencia, no verdad.
- Fuentes del transcript Grok = búsqueda real, pero los TOOLS nombrados (magg, etc.) se verifican
  ejecutándolos una vez antes de depender de ellos (prove-it, igual que con nuestro código).
- Anti-bloat: cada raíz se gana su sitio (`wire-before-claim`); el tronco expone superficie PEQUEÑA
  enrutada por objetivo, no todo a la vez.

## Fases falsables (cuando se construya)

- **F1** — Tronco Python mínimo (FastMCP) + 1 raíz: nuestro sustrato de memoria como tools MCP
  (`recall`, `add`, `supersede`…). Prueba de portabilidad: instalarlo y usarlo desde OTRO proyecto.
- **F2** — Raíz operating (manías/ledger como recursos + sanitation_audit como tool) + franken-prompt
  por objetivo entregado por el canal real (probar enforcement honesto).
- **F3** — Raíz knowledge-src (empezar con 1-2 APIs libres: Wikipedia + una dataset) → cablear a
  `run_mission` → verificar que el conocimiento entra al sustrato con procedencia.
- **F4** — Agregación de raíces commodity (filesystem/git) + catálogo (`docs/design/mcp_catalog.md`)
  + **instalador automático** (script que verifica+instala lo marcado; ley del mínimo esfuerzo, el
  agente decide qué, el código lo descarga); medir overhead de contexto.
- **F5** — (si procede) reescritura por-raíz en Rust de lo que lo justifique.
Criterio de éxito por fase: instalable de una, superficie enrutada pequeña, contenido con procedencia.
