# Auditoría MCP del tronco — los 6 primitivos (2026-06-25)

Disparador: el usuario sospecha que infrautilizamos el MCP ("lo hemos usado solo para skills/prompts").
Objetivo: mapear lo que el tronco realmente expone a los **6 primitivos de servidor** del spec MCP, hallar
los huecos reales con su valor/coste, y proponer un diseño priorizado. **NO implementa** — alimenta un
brainstorming. Manías: `decide-with-facts`, `internal-prior-art-first`, `wire-before-claim`.

Fuentes externas: modelcontextprotocol.io (spec), workos.com/blog/mcp-features-guide,
bentoml.com/blog/a-guide-to-open-source-embedding-models.

## Hechos (grep sobre `src/atlas/mcp/`, no asunción)

| Primitivo MCP | Para qué sirve | ¿Lo usa el tronco? | Evidencia |
|---|---|---|---|
| **Tools** | acciones que el modelo invoca | ✅ a fondo | memory/knowledge/operating/trunk_server: decenas de `@server.tool()` |
| **Resources** | contexto estático/semi-estático que el modelo LEE sin tool-call | 🟡 apenas 2 | `operating_server.py:31,36` → `operating://agents`, `operating://ledger` (markdown) |
| **Prompts** | plantillas de instrucción reutilizables | ❌ cero | NO hay `@server.prompt()`. Los skills se sirven como TOOLS (`trunk_server.py:196,201` `list_skills`/`get_skill`) |
| **Sampling** | el servidor pide un completion AL CLIENTE (offload de razonamiento sin pagar modelo) | ❌ | sin `create_message`/`ctx.sample` |
| **Roots** | fronteras de filesystem que el cliente concede | ❌ | `RootSpec`/`native_roots` son nombre INTERNO nuestro (colisión léxica), no el primitivo Roots |
| **Elicitation** | el servidor pide input ESTRUCTURADO al humano a mitad de llamada | ❌ | sin `ctx.elicit` |

**Recuento honesto: 2 de 6** (Tools a fondo; Resources apenas para 2 docs operativos). Corrige la
impresión "skills/prompts": el primitivo **Prompts no se usa** — los skills van por Tools.

Dependencia: `pyproject.toml:41` fija `mcp>=1.2`. Elicitation entró en el spec 2025-06 / SDK ~1.9+;
Sampling es antiguo. Verificar el floor real antes de diseñar con Elicitation (posible subir el pin).

## Huecos reales, por valor/coste

### 1. Resources para el catálogo/manifest — VALOR ALTO, coste bajo  ← candidato #1
Hoy el catálogo (sectores/kinds/skills/find) se navega SOLO por tool-calls (`trunk_sectors`, `trunk_find`,
`trunk_catalog`, `get_skill`…). Cada consulta quema un turno del modelo. La idea del usuario de **"un JSON
índice para todo el MCP"** = exactamente el primitivo **Resources**. Exponer el manifest/catálogo (y los
skills) como Resources legibles da la "mesa de trabajo" (SP-A): el agente lee el índice de capacidades UNA
vez, con etiqueta de estado, sin gastar turnos. Prior-art interno: ya sabemos servir Resources
(operating_server) y ya tenemos el catálogo cargado (`catalog.py`, taxonomía v3). Es cablear, no inventar.

### 2. Prompts para skills — VALOR MEDIO, coste bajo
Los skills son plantillas de instrucción reutilizables = la definición literal de **Prompts**. Servirlos
también como Prompts (no solo como tool `get_skill`) los hace descubribles por el cliente de forma nativa
(slash-commands, autocompletado) sin un tool-call. No sustituye `get_skill`; lo complementa.

### 3. Elicitation = el hook nativo de HITL — VALOR ESTRATÉGICO, coste medio
"El servidor pausa y pide input estructurado al humano." Es el primitivo que la visión de **reducir HITL /
copia-digital (SP-D)** necesita conocer ANTES de diseñar: en vez de un HITL ad-hoc, el punto de decisión
humana se modela como Elicitation estructurada → más adelante una "copia digital" puede responderla con
esquema. Manía `no-deepen-hitl-coupling`: NO se construye hasta tener el mecanismo seguro; pero el diseño
de SP-D debe partir de aquí.

### 4. Sampling — VALOR (ahorro) MEDIO, coste medio
Permite que una tool del tronco pida razonamiento al cliente sin integrar/pagar un modelo propio. Encaja con
el **regulador de tokens (SP-B)**: el tronco delega el "pensar" al modelo del cliente cuando aplica. Medir
antes (`wire-before-claim`): ¿hay una tool del tronco que hoy necesita un LLM y lo resuelve mal/caro?

### 5. Roots (primitivo) — VALOR BAJO hoy
Útil si el cliente debe conceder ámbitos de filesystem al tronco. Hoy el tronco no opera sobre el FS del
cliente. Diferir (anti-vapor). Nota: renombrar nuestro `RootSpec` evitaría la colisión léxica si algún día
se adopta el primitivo.

## Más allá de los 6: utilidades + EXTENSIONES (investigación 2026-06-25)

Respuesta a "¿hay más primitivos y se pueden expandir?" — **sí, en dos niveles**. Fuentes:
modelcontextprotocol.io/specification/draft, blog.modelcontextprotocol.io/posts/2026-03-11-understanding-mcp-extensions,
workos.com/blog/mcp-2025-11-25-spec-update.

**Utilidades del core (más allá de Tools/Resources/Prompts):**
- **Completion** — autocompletado de argumentos para prompts y URIs de resources (experiencia tipo-IDE).
- **Resource templates** — resources parametrizados por URI (`catalog://sector/{sector}`), no N resources fijos.
- **Resource subscriptions + Notifications** (`resources/subscribe`, list-changed/updated) — el resource avisa
  cuando cambia.
- **Logging, Progress, Cancellation, Ping** — utilidades para operaciones largas.

**Los primitivos SÍ se expanden — framework de EXTENSIONS (spec 2026-03):**
- Opt-in, negociadas en el handshake `initialize` (campo `extensions` en client/server capabilities).
  Identificador `{vendor-prefix}/{extension-name}` (oficiales: `io.modelcontextprotocol`). **Estrictamente
  aditivas**: quien no reconoce una extensión la ignora, nada rompe. → podríamos definir extensiones `atlas/...`.
- Extensiones oficiales notables: **Tasks** (trabajo async/largo; de core experimental → extensión en 2025-11-25)
  y **MCP Apps** (el server sirve UI HTML interactiva en iframe sandboxed; las tools declaran su template de UI).

**Implicaciones para Atlas (estratégicas, registradas; NO construir aún):**
- **Tasks** = primitivo nativo de trabajo largo → encaja con el loop autónomo (autobuild/Dynamic Workflows)
  mejor que el caveat DW; reabrir al diseñar SP-E.
- **MCP Apps** = posible UI real de la "mesa de trabajo" (SP-A) / dashboards de estado.
- **Resource templates + subscriptions + Completion** = CÓMO exponer el catálogo (#1) bien: navegable por
  URI, con etiqueta de estado VIVA (el sync diario `mcp-catalog-sync` empuja updates) y autocompletado.
- **Extensions `atlas/...`** = vía nativa para lo que el core no cubre (p.ej. routing por sector, manifest con
  estado) sin romper clientes ajenos. Medir necesidad antes (`wire-before-claim`); no inventar extensión por
  inventarla.

## Recomendación priorizada (para brainstorming, no implementación)

1. **Resources del catálogo/manifest** (#1) — el ladrillo de la "mesa de trabajo" (SP-A) y respuesta directa
   al "JSON índice" del usuario. Internal-prior-art, coste bajo. **Empezar aquí.**
2. **Prompts para skills** (#2) — complemento barato, mejora descubribilidad.
3. **Elicitation** (#3) — NO construir aún; es el marco que SP-D (HITL) debe heredar. Verificar floor `mcp`.
4. **Sampling** (#4) — medir necesidad real (SP-B) antes.
5. **Roots** (#5) — diferido.

Embeddings (`memory-mcp-local-embedder`): el embedder local aterriza DENTRO de este marco — la memoria
semántica es una capacidad que el catálogo-como-Resource debe reflejar con su etiqueta de estado.

## Definition of done de esta auditoría
Documento factual (grep, no asunción) + huecos priorizados + próxima acción = brainstorming de Resources
(#1). No declara nada "hecho": es input de diseño. Estado vivo en `WORK_LEDGER.md`
(`mcp-audit-six-primitives`), memoria en `mcp-deepening-and-local-embeddings.md`.
