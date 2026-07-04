# ATLAS — Síntesis completa para planificación externa

> Generado: 2026-06-26. Autor del proyecto: Tomás Asín González.
> Propósito de este documento: llevar a otro LLM para pedir un plan cerrado.
> Este doc NO duplica estado vivo. Para estado real: `atlas reality --json` en el repo.

## CONTEXTO HUMANO — leer antes que cualquier otra cosa

**Quién**: Tomás, una persona sola. Desarrollador, no empresa.

**Estado de ánimo real al escribir esto**: cansado. Meses construyendo sin norte claro. Llegó a "ya no me acuerdo por qué lo construía". Eso no es fracaso — es la señal de que el scope creció más que el porqué.

**Restricciones reales y no negociables**:
- **Sin presupuesto para suscripciones** (ese es el porqué original: evitar pagar Cursor/Claude Code cada mes).
- **Una sola persona** — sin equipo, sin financiación, sin CI/CD externa, sin infraestructura cloud propia más allá de lo gratuito.
- **Modelos gratuitos disponibles hoy** (verificados en vivo): Groq (llama3, qwen), Gemini Free (gemini-2.5-flash), OpenRouter (nemotron, liquid), NVIDIA NIM (con cuentas gratuitas). Todos responden sub-segundo. Rate limits existen pero son manejables para uso personal.
- **Hardware local**: máquina Linux propia. El sandbox bwrap funciona. fastembed/ONNX corre local sin GPU.
- **Tiempo**: limitado. El plan que salga de este doc debe ser ejecutable en sesiones de trabajo reales, no en sprints de equipo.

**Lo que NO necesita el plan**:
- Ganar a Cursor o Claude Code en capacidad bruta — imposible y no es el objetivo.
- Competir con equipos de 500 desarrolladores — no es el tablero.
- Ser el primero en nada a escala mundial.

**Lo que SÍ necesita**:
- Que Tomás lo use cada día para trabajar.
- Que le ahorre la suscripción.
- Que con el tiempo lo conozca mejor que ninguna otra herramienta.

**Nota sobre la dispersión**: el proyecto pivotó al menos 3 veces (agente de código → OS multiagente → gateway de cumplimiento). Hay 3 roadmaps distintos en el repo. Hay ~14 subsistemas durmientes detrás de flags apagados. El plan que salga de aquí debe elegir UN norte primario y relegar lo demás explícitamente — no "hacer todo en paralelo".

---

## 1. QUÉ ES ATLAS — definición honesta y porqué del autor

### Definición técnica

Atlas es un **runtime local de IA** con tres funciones superpuestas:

1. **Agente de código local** — asistente de desarrollo que corre en la máquina del usuario, con memoria persistente, herramientas auditadas y sin suscripción mensual. El porqué original: tener algo como Cursor/Claude Code pero tuyo, gratuito después de la inversión inicial, que te conozca con el tiempo y opere días sin que lo mires.

2. **Orquestador multi-agente gobernado** — un runtime que puede lanzar enjambres de workers en worktrees aislados, verificar sus artefactos criptográficamente, y aplicar solo los cambios que pasan los tests. Toda decisión de ejecución pasa por un decisor central intercambiable (ADR-040).

3. **Gateway de cumplimiento / Osmosis** — una capa de compliance para modelos frontier restringidos que aplica transparencia mutua verificable sobre un log Merkle único. Nació del apagón de Fable 5/Mythos 5 (junio 2026, directiva de exportación de EEUU). Tiene un núcleo criptográfico sólido y ya fue formalizado en un paper académico (completitud verificable, referenciando RFC 9162 y RFC 9334).

### El porqué del autor — honesto

Tomás es **una sola persona**. Construyó Atlas durante meses, con energía y sin norte claro. El porqué original recuperado en la sesión que generó este documento:

- **Porqué real**: un asistente de código local y gratis, como Cursor pero tuyo. Sin suscripción. Que aprenda quién eres.
- **Porqué derivado (el que lo consumió)**: querer ser "el primer OS multiagente que lo hace todo". Ese scope fue el que dispersó el esfuerzo.

Hoy Atlas tiene **mucho más** de lo que necesita el porqué original (el agente de código), y también tiene la semilla de algo distinto con valor propio (el gateway de compliance). El problema no es falta de código. Es falta de norte.

### Lo que no es

- No es un producto. Es un prototipo técnico poderoso que requiere instalación manual.
- No compite con los labs en razonamiento. Se apalanca sobre sus modelos y añade lo que un lab no puede dar: memoria del usuario, autonomía gobernada, profundidad vertical.
- No es un sistema agnóstico de modelo — usa Claude, Gemini, Kimi, Mistral, pero vía APIs con fallback.

---

## 2. VISIÓN: las 6 gotas del software líquido

El concepto capturado en la sesión de hoy: software líquido = sistema que se mimetiza con la intención del usuario. Seis ingredientes. Tres existen. Tres faltan.

### Gota 1 — Modelo del usuario (FALTA — es el alma)

**Qué es**: una representación viva de quién es el usuario — sus proyectos, sus hábitos, sus preferencias, su vocabulario técnico, cómo decide, qué le importa. No un perfil estático: un modelo que se actualiza con cada sesión.

**Qué hay**: el `SqliteMemoryIndex` (Fase 1 completa, 0.934 R@5 en LongMemEval_S híbrido), embeddings semánticos locales (fastembed/ONNX, sin torch), recuperación híbrida (FTS5 léxico + coseno semántico + temporal). Hay sustrato. No hay el "modelo de usuario" como concepto unificado — no hay nada que aprenda "Tomás prefiere X", "cuando Tomás dice esto quiere decir aquello".

**Qué falta**: la capa de modelado de usuario encima del sustrato de memoria. El `RecordingDecider` (Slice 1b completo) ya graba decisiones para construir el corpus. El `TwinDecider` (Slice 3, no construido) aprendería del corpus. La conexión entre "qué recuerdo" y "qué modelo de persona construyo" no existe.

**Por qué es el alma**: sin modelo del usuario, Atlas no puede anticipar intención. Es una caja de herramientas, no un asistente.

### Gota 2 — Captura de intención ambiente (FALTA)

**Qué es**: detectar qué quiere el usuario sin que lo diga explícitamente. Leer el contexto del editor, el repo, las conversaciones recientes, y proponer la siguiente acción relevante.

**Qué hay**: el `exec_api.py` (ADR-027, `/api/exec/intent`) acepta intenciones explícitas. El orquestador las procesa. No hay captura proactiva.

**Qué falta**: el hook de captura ambiente — algo que observe el estado del sistema (qué archivo está abierto, qué error acaba de aparecer, qué commit acaba de fallar) y lo convierta en intención. Esto requiere el modelo de usuario (Gota 1) para saber qué es relevante para este usuario en este contexto.

### Gota 3 — Sustrato de capacidades (YA CONSTRUIDO)

**Qué hay**: el tronco MCP (`atlas-trunk`, una sola conexión), 700+ herramientas catalogadas en 9 dominios y 11 líneas (mcp/api/skill/tool/prompt/command/hook/subagent/plugin/rule/workflow), skills servidos (atlas-coding-discipline, web-design-guidelines, writing-guidelines, vercel-react-best-practices), 4 APIs propias vivas (Wikipedia, World Bank, Open-Meteo, Frankfurter), MCPs verificados externos (sequential-thinking, mcp-memory, everything), Google Workspace (45 tools), automatización periódica del catálogo (cron diario + agente programado).

**Estado real**: sustrato rico. El problema es que Atlas **no lo usa de forma estructural** — la autoselección es probabilística (el modelo elige), no determinista (un router lo fuerza). La Pieza 3 de la línea "capacidades usables" (routing hook `UserPromptSubmit`) lo cierra, pero aún no está construida.

### Gota 4 — Composición por contexto (YA CONSTRUIDO)

**Qué hay**: el orquestador central, la cascada con routing por dificultad (ADR-042), el decisor central con invariantes deterministas (ADR-040), el loop agéntico suspendible con HITL (ADR-031/032/033), la membrana de gestión de ideas externas (OSM-000).

**Estado real**: la cascada existe pero su único consumidor real es el `maintenance_codegen_proposer`. El path conversacional no pasa por la cascada (los artefactos son CLAIMs sin verificador barato). El loop agéntico funciona. La composición dinámica por contexto no está cerrada.

### Gota 5 — Acción segura y reversible (YA CONSTRUIDO)

**Qué hay**: `ColdUpdateManager` (worktree aislado → validate pytest+mypy → apply con rollback), enjambre sobre blackboard (ADR-045/046, vivo y gated), `BwrapJail` (jail OS-level, rootfs mínimo), Merkle append-only como log de auditoría inmutable, `RevertRegistry` (`revert(action_hash)`), invariantes deterministas en `AutonomousDecider` (IOC→Deny, sensitivity=high→Deny, sin anclaje de intención→Deny, sin undo→Deny).

**Estado real**: sólido. El ASTGuard fue degradado a lint (la auditoría demostró que era bypasseable). El jail de BwrapJail existe. El enjambre solo propone (auto-apply OFF). La acción es segura y reversible para operaciones de código; para operaciones de IA (loop agéntico) el HITL sigue siendo el humano.

### Gota 6 — Adaptación continua (FALTA)

**Qué es**: el sistema aprende de sus errores y mejora sin intervención humana. Cada fallo se convierte en lección, cada lección mejora al productor, cada mejora se verifica antes de aplicarse.

**Qué hay**: `LessonStore` (ADR-044, núcleo sin consumidores), `SwarmCycle` (vivo y gated, propuesta-solo), `KnowledgeOrganism` (ADR-049, slice 1 completo: adquiere y verifica conocimiento externo), `SelfImprovementBridge` (detecta CVEs en deps propias).

**Qué falta**: el lazo cerrado. El enjambre propone pero no aplica. El LessonStore tiene núcleo pero no consumidores (Analyst/codegen no lo cargan). El `SelfImprovementBridge` no está cableado al loop de auto-mejora. El `TwinDecider` (que aprendería del corpus de decisiones) no existe.

---

## 3. LO QUE EXISTE HOY — estado verificado

### Mediciones reales (no afirmadas)

- **Tests**: 2364 verdes (suite completa, mypy strict, 2026-06-26)
- **Memoria semántica**: LongMemEval_S n=500 k=5: cosine=0.294, hybrid=0.356, temporal=0.294 — híbrido +21% sobre coseno solo, knowledge-update +100%; R@5=0.934 con fastembed
- **Merkle**: ~2323 records (cadena de auditoría inmutable desde Gates A-I)
- **Proveedores de inferencia**: Groq, OpenRouter, Together, Gemini, NVIDIA (L2 frontier: llama-3.1-405b con account_pool de 2 cuentas)
- **Cónclave (deliberación multi-voz)**: v2.0 estable, 3/3 voces útiles en smoke vivo (Gemini-2.5-flash, Kimi, Mistral-Large-3)
- **Catálogo MCP**: 724+ candidatos clasificados en 9 dominios; 12 instalados, 3+ verificados; E2E completo demostrado
- **Tronco MCP**: `atlas-trunk` desplegado, 1 conexión, 6 hijos (3 raíces nativas + 3 externos verificados)

### Capacidades cableadas y funcionales (real)

| Capacidad | Estado real |
|---|---|
| Cadena Merkle / log de transparencia | real — consumido por gateway/store |
| SqliteMemoryIndex + olvido (Fase 1) | real — motor cableado al inquilino de seguridad |
| Embeddings semánticos locales (fastembed) | real — opt-in `ATLAS_EMBEDDER=fastembed` |
| Recuperación híbrida (FTS5 + coseno + temporal) | real — andamiaje de ablación en `eval_memory_benchmark` |
| Drift tripwire | real — alimenta `confidence` del gateway |
| ScopedInspector | real — cableado al gateway |
| Cónclave v2.0 (deliberación multi-voz) | real — 3/3 voces útiles en vivo |
| RecordingDecider + MemoryDecisionSink | real — grabación opt-in de decisiones con Fernet+shred+merkle |
| Tronco MCP + catálogo v2 | real — desplegado, 1 conexión, 700+ catalogados, E2E verificado |
| Knowledge organism slice 1 | real — adquiere+verifica+ingesta con procedencia |
| Lazo de aprendizaje auditable | real — gateway→LessonStore→Merkle (camino feliz y rechazo probados) |
| Compliance Gateway (núcleo) | real — log RFC 9162, co-firma continua, crypto-shredding GDPR |
| Swarm + blackboard (enjambre) | real, gated (`ATLAS_SWARM_SCHEDULER`) — propuesta-only |
| ColdUpdateManager | real — worktree→validate→apply→rollback |
| AutonomousDecider + invariantes | real — IOC/sensitivity/undo/intención deterministas |
| BwrapJail (jail OS-level) | real — rootfs mínimo (`bwrap_jail.py:159-185`) |
| InferenceHub con fallback | real — Groq→OpenRouter→Together→Gemini→local |

### Capacidades construidas pero no cableadas (no-cableado)

- `cascade.py` (ADR-042): solo consumidor real = `maintenance_codegen_proposer`. Sin CLI, sin trigger autónomo.
- `LessonStore` (ADR-044): núcleo sin consumidores (Analyst/codegen no lo cargan).
- `WitnessServer`: cuarentena. Requiere ≥2 operadores independientes (no existen).
- `KycBinding`: cuarentena. Construido + testeado, 0 consumidores.
- `LogBehavioralAuditor`: cuarentena.
- `SelfImprovementBridge` → loop de auto-mejora: no cableado.
- `record_synthesis` del Cónclave → LessonStore real: no cableado.
- Routing hook `UserPromptSubmit` (Pieza 3 de capacidades usables): no construido.

### Cómo leer los números de tests

Los 2364 tests cubren: sustrato de memoria (Fases 1+2), tronco MCP completo (raíces + agregador + catálogo + skills + capabilities), RecordingDecider + MemoryDecisionSink, Cónclave v2.0, compliance gateway (transparencia + crypto-shred + shadow model), auto-mantenimiento (scouts, analyst, ColdUpdate, enjambre), y más. Todos corren con `pytest` + `mypy --strict`. La suite es la red de seguridad que permite cambios sin regresión.

El número importa menos que la cobertura real. Hay módulos con cobertura alta (todo lo cableado) y módulos con cobertura solo en unit tests (LessonStore, Cascada) porque no tienen consumidor real. Los módulos en cuarentena tienen sus propios tests pero están fuera de la suite principal.

### Lo que está en el graveyard (cuarentena/archivado)

`affinity_maturation`, `scorers`, `llm_scorer`, `security_worker`, `fuzzing`, `red_team`, `gossip`, `witness`, `log_behavioral`, `kyc_binding` — todos en `_graveyard/2026-06-21-f3/`. Grace period expira ~2026-07-21.

---

## 4. DIRECCIÓN 1: Agente de código local

### Qué hay

El sustrato está construido. El tronco MCP expone memoria, conocimiento y skills en una sola conexión. El orquestador acepta intenciones y las procesa. El loop agéntico con tool-calls funciona (suspendible, reversible, con HITL). El `RecordingDecider` graba cada decisión.

La demo técnica funciona: Atlas puede editar código, correr tests, hacer commits, buscar en su memoria, consultar APIs externas, deliberar con el Cónclave, proponer parches a su propio código.

### Qué falta para ser un asistente de código real

**1. Modelo del usuario (la gota que falta)**

El asistente de código que se comporta como Cursor/Claude Code no es solo una caja de herramientas. Es un sistema que sabe qué haces, cómo trabajas y anticipa la siguiente acción. Atlas tiene el sustrato de memoria (fastembed + FTS5 + temporal), pero no tiene el "conocimiento de persona" encima. Falta:
- Un `UserModel` que acumule preferencias, hábitos, proyectos activos, vocabulario técnico del usuario.
- Inferencia de intención a partir del contexto del editor/repo (captura ambiente, Gota 2).
- El `TwinDecider` que aprende del corpus de decisiones grabadas por el `RecordingDecider`.

**2. El routing determinista de capacidades (Pieza 3)**

Hoy las 700+ herramientas del catálogo son solo nombres. El modelo las selecciona probabilísticamente. Falta el hook `UserPromptSubmit` que consume el catálogo enriquecido/verificado y hace la selección determinista. Sin esto, Atlas no "usa lo propio" de forma fiable.

La secuencia correcta: Pieza 1 (enriquecer catálogo, HECHO) → Pieza 2 (trial-en-jaula + escáneres adoptados, PENDIENTE) → Pieza 3 (routing hook, PENDIENTE).

**3. El entrypoint de usuario**

Atlas no tiene una UI comprensible para no-desarrolladores. La demo técnica requiere CLI y conocimiento del sistema. Para que Tomás lo use como "su Cursor": necesita al menos un flujo conversacional que arranque fácil, muestre en qué está pensando, y pida confirmación cuando toca.

**4. El lazo de auto-mejora completo**

El enjambre (ADR-045/046) propone patches de mantenimiento mecánico (whitespace, normalización). El ColdUpdateManager los valida. Pero el auto-apply está OFF. Para que Atlas se "mantenga solo", falta: (a) auditoría de muestra suficiente para habilitar auto-apply en tipo-1 reversible, (b) el LessonStore cargado por Analyst/codegen, (c) la capa Lesson→LLMProducer que convierte fallos pasados en restricciones futuras.

### El camino mínimo para el porqué original

Si el objetivo es "un asistente de código local y gratis que te conozca", la secuencia mínima es:
1. Cablear el `RecordingDecider` al corpus acumulado y empezar a poblar el modelo de usuario.
2. Pieza 2 del catálogo (verificación en jaula) + Pieza 3 (routing hook).
3. Un flujo de CLI/chat que use el sustrato que ya existe.

El resto (enjambre, LessonStore, auto-apply) son capas encima que vienen después.

### Estado de la copia digital (RecordingDecider)

La copia digital es el nombre interno del programa que construye un modelo del usuario a partir de sus decisiones. El estado actual:

- **Slice 1 (hecho)**: `RecordingDecider` — wrapper transparente del Decider Protocol. Graba cada decisión con features (acción, contexto, intención sancionada) y rationale separados. Fernet+crypto-shred: el rationale es borrable (GDPR), las features permanecen para el corpus. Firewall D por construcción: el RecordingDecider no lee el log, solo escribe (no hay API de lectura). `ATLAS_DECISION_LOG=memory:<db>` para activarlo.

- **Slice 1b (hecho)**: `MemoryDecisionSink` — sink de producción. Integra Fernet + shred + Merkle + `ProvenanceWriteGate`. Split A verificado: shred del rationale deja las features intactas (el Merkle sobrevive al borrado del rationale).

- **Slice 2 (pendiente)**: Shadow eval — capturar el veredicto humano real al resolver `RequiresHuman`. Métrica de divergencia: TwinDecider predice vs. humano decide. Sin este slice, no hay señal de aprendizaje.

- **Slice 3 (pendiente)**: `TwinDecider` — aprende del corpus del Slice 1b. Primero en shadow (predice, no decide). Solo se convierte en decisor real cuando la divergencia es suficientemente baja en shadow.

La secuencia Slice 1b→2→3 es el camino hacia "human-ON-the-loop" real: el sistema decide solo en lo que sabe hacer bien, y escala en lo que no.

### Lo que separa Atlas de Cursor/Claude Code

Para Tomás, la comparación relevante es práctica: ¿por qué usar Atlas en vez de simplemente pagar la suscripción de Cursor o Claude Code?

**Lo que Cursor/Claude Code no pueden dar (por diseño):**
1. **Memoria persistente entre proyectos**: los servicios cloud resetean contexto. Atlas acumula con Merkle — la procedencia de cada memoria es auditable, no alucinada.
2. **Autonomía gobernada**: Cursor no puede ejecutar una semana de mantenimiento mecánico solo. Atlas tiene el enjambre + ColdUpdate + decisor — cuando esté encendido, puede.
3. **Profundidad vertical**: Atlas puede aprender los patrones específicos de Tomás (su forma de nombrar, sus preferencias de arquitectura, sus proyectos activos) y usarlos al deliberar con el Cónclave.
4. **Sin vendor lock-in de modelo**: si Anthropic apaga Claude (ya ocurrió con Fable 5), Atlas puede cambiar a Gemini o Mistral sin perder el contexto ni la memoria.
5. **Coste a largo plazo**: después de la inversión de construcción, el coste marginal es solo la inferencia (APIs con tiers gratuitos + fallback local eventual).

**Lo que Cursor/Claude Code SÍ tienen y Atlas no tiene todavía:**
- UX pulida y documentación para no-desarrolladores.
- Integración directa con el editor (LSP, inline suggestions).
- Fiabilidad demostrada en producción (miles de usuarios, bugs encontrados y resueltos).
- Velocidad de iteración de un equipo dedicado.

La respuesta honesta: Atlas ya tiene el sustrato técnico que lo hace diferenciable. Le falta el pulido para que Tomás lo use todos los días en vez de abrir Claude Code.

---

## 5. DIRECCIÓN 2: Gateway de cumplimiento / Osmosis

### Qué hay (el núcleo criptográfico es sólido)

El núcleo del compliance gateway es código real, testeado y con paper académico publicable:

- **TransparencyGateway** (`src/atlas/transparency/`): log append-only RFC 9162, co-firma monótona cliente, crypto-shredding GDPR Art. 17 (salt por petición, borrable sin romper la cadena), detección de omisión (laguna en la secuencia del cliente), detección de vista partida (STH inconsistentes).
- **Paper "Subject-Enforced Completeness"**: 17 páginas, citas verificadas, listo para arXiv (pendiente de endorsement en cs.CR). Contribución central: el sujeto puede verificar por sí mismo que no fue espiado más allá de la causa — transparencia mutua, no unilateral.
- **Demo reproducible**: sesión legítima (cero inspecciones), sesión con abuso catalogado (causa→bloqueo→log sellado), `MutualAuditView` que muestra el mismo log a "regulador" y a "usuario" con distintos lentes.
- **Crypto-shredding (GDPR GAP-1 cerrado)**: `salted_hash` erasable; `payload_hash` permanente (binding). 12 tests.
- **Shadow model + honeypot** (OSM-042): `ShadowRouter` + `ShadowMode` cableados al gateway. Tests de integración.
- **Behavioral drift detection** (OSM-054): `BehavioralMonitor` con canary prompts. En membrana (no promovida a Absorbida hasta que el paper cierre los límites formalmente).

### Qué falta para que sea un producto standalone

**Entrypoint HTTP** (GAP-2): no existe. El núcleo es una librería sólida sin servidor HTTP. Para que un desplegador lo use, necesita:
```
GET /api/v1/log/entries?session_id=<id>&from_seq=0&to_seq=100
GET /api/v1/log/inclusion_proof?leaf_index=<n>
GET /api/v1/log/sth/latest
```

**Verificador cliente distribuible**: el valor del sistema requiere que el cliente (el usuario final) tenga un verificador ligero que coteje su secuencia contra el STH publicado. Hoy el mecanismo existe en código de test; falta empaquetarlo como herramienta standalone.

**Persistencia de log durable** (OSM-032, diferido): el log existe en SQLite. Sin persistencia con backups verificados y compactación auditada, no es producción.

**Technical File Anexo IV** (GAP-3): los ADRs no son el Technical File del EU AI Act. Falta `docs/technical_file_annex_iv.md` con la estructura que exige el regulador (descripción funcional, métricas de rendimiento, limitaciones conocidas, proceso de supervisión).

**Canal de transparencia al usuario** (OSM-041, Suspensión): criptografía en backend ≠ transparencia regulatoria. Falta la UI/notificación que surface el veredicto de `detect_omission()` al humano (Art. 13 EU AI Act).

### La demo de Osmosis: qué demuestra hoy, sin permiso de nadie

La demo construible hoy (sin servidor externo, contra key propia o modelo local):

1. **Sesión legítima**: el usuario trabaja con normalidad. El log Merkle al final de la sesión prueba **cero inspecciones de contenido**. El usuario verifica que su secuencia monótona no tiene lagunas.

2. **Sesión con abuso catalogado**: p.ej. intento ofuscado de exfiltración de pesos del modelo. La capa L1 (metadata) dispara una señal. El `ScopedInspector` confirma contra `AbuseList`. `GradedResponder` bloquea y reporta. Todo sellado con consistencia proof.

3. **MutualAuditView**: mismo log, dos lentes. Al "regulador": los abusos detectados. Al "usuario": la prueba de que cada inspección de contenido estuvo precedida por un disparo de metadata registrado. Sin ese disparo en el log, la inspección no ocurrió.

Lo que hace esto no-trivial: el log es **único**. No hay dos versiones del log. Un operador no puede mostrar al regulador un log "limpio" y al usuario un log "completo" — son el mismo árbol Merkle, con STH que el usuario puede verificar de forma independiente.

La demo cabe en ~2 minutos de video. No convence a un gobierno. Demuestra que el razonamiento sobre el problema de Anthropic (el apagón de Fable 5) es técnicamente serio y construible.

### Posicionamiento EU AI Act

Atlas es el único sistema conocido que implementa completitud verificable **desde el lado del sujeto** (el usuario verifica que no fue espiado más allá de la causa, sin depender del operador). Los gaps regulatorios identificados:

| Gap | Artículo | Estado |
|---|---|---|
| GDPR Art. 17 (derecho al olvido vs. Merkle) | GDPR | **CERRADO** — crypto-shredding implementado |
| Art. 26 (deployers necesitan Read-API) | EU AI Act | **ABIERTO** — no existe entrypoint HTTP |
| Art. 11 + Anexo IV (Technical File) | EU AI Act | **ABIERTO** — ADRs ≠ Technical File |
| KYC Interface (export controls) | OFAC/sanciones | diferido (low-pri) |

### ¿Osmosis como producto independiente o capa de Atlas?

Esta es una pregunta abierta (ver Sección 10). Lo que está claro:
- El núcleo criptográfico es independizable. No depende de nada del orquestador.
- El paper va a cs.CR, no a multiagent systems.
- El posicionamiento ("verifícalo, no confíes") es diferente al del agente de código.
- Una persona sola no puede mantener dos productos de forma sostenible.

---

## 6. CAPACIDADES DURMIENTES

Todo lo construido pero sin consumidor real, por si hay que despertarlo.

### Enjambre sobre blackboard (ADR-045/046, `ATLAS_SWARM_SCHEDULER`)

Estado: construido, gated, propuesta-only. `SwarmCycle` produce diffs → `ColdUpdateReconciler` → `ColdUpdate.propose(origin=swarm)`. Auto-apply OFF. El humo aislado funciona. Falta: auditoría de muestra suficiente para encender auto-apply; transforms adicionales (orden de imports, imports muertos); envolver por-worker para contener workers tóxicos.

Para encenderlo: `ATLAS_SWARM_SCHEDULER=1`. Riesgo: el techo de cadencia no es la suite sino el tope de propuestas abiertas sin un decisor que las drene.

### Cascada con routing (ADR-042, `cascade.py`)

Estado: construida, un solo consumidor real (`maintenance_codegen_proposer`), sin CLI, sin trigger autónomo. El path conversacional no pasa por aquí (los artefactos son CLAIMs sin verificador barato). El rung FRONTIER está preparado pero sin provider L2 que lo use. Para despertar: cablearla a un segundo consumidor real (p.ej. el `handle_intent` principal).

### Verified Producer (ADR-048)

Estado: lazo completo A-F (panel adversarial, lazo, arnés determinista, LLMProducer, scout, composición). Falta: cablear `WorktreeWorker.produce_diff` real en el coordinador vivo. Hasta que esté cableado, es librería sin uso en producción.

### Self-maintenance agent (ADR-039)

Estado: scouts (registry/dep), analyst dual-LLM + gate de corroboración, proposer, adopter, `MaintenanceScheduler`. Vivo y gated (`ATLAS_SELF_AUDIT_SCHEDULER`). Falta: el `SelfImprovementBridge` → loop de auto-mejora (cableado CVE→propuesta ColdUpdate); daemon hacia afuera (`ATLAS_KNOWLEDGE_SCHEDULER`); reporte por Telegram.

### LessonStore (ADR-044)

Estado: núcleo verificable (sin consumidores). Las 3 lecciones reales (matcher, doble escritor Merkle, suite recursiva) no están sembradas porque el `ProveItResult` se inyecta manualmente (no hay runner real de prove-it). Falta: runner real (worktree en `fix_commit^` + pytest), sembrado de las 3 lecciones reales, cableado `ErrorRegistry` → `LessonPromoter`, consumidores (Analyst/codegen cargan `avoid_pattern`).

### Inference Hub detrás de Gate-D

Estado: cableado, L0/L1 funcionales, L2 (FRONTIER) preparado pero sin consumidor que lo use en producción. NVIDIA L2 (llama-3.1-405b) configurado con account_pool de 2 cuentas. El Cónclave usa el hub directamente; la cascada no llega al FRONTIER en ningún path vivo.

### Multi-hop memory (Fase 2.1)

Estado: SIGUIENTE en la línea de memoria. El sustrato está listo (FTS5 + embeddings + temporal). Falta: recuperación multi-hop (cadena de memorias relacionadas). Bloqueado por prioridades.

### PII / Crypto-shredding de memoria (Fase 2.2)

Estado: GAP-1 EU AI Act. El crypto-shredding del compliance gateway está implementado. El mismo patrón no está aplicado a la memoria del usuario (SqliteMemoryIndex). Falta: aplicar `SaltStore` a los registros de memoria con contenido de usuario.

### Behavioral drift detection (OSM-054)

Estado: código existe y funciona (`BehavioralMonitor`, canary prompts). En membrana (no promovida). Falta: que el paper cierre formalmente los límites (no hay garantía de detección, solo señal).

---

## 7. IDEAS Y FUTURO

Todo lo planteado que no tiene código. Etiquetado por valor y costo de ejecución.

### Nota sobre las ideas: cuándo entran en el sistema

Las ideas externas no entran directamente en el código. La membrana (OSM-000) es el mecanismo de admisión: toda idea pasa por `docs/membrana/OSM-XXX` antes de convertirse en ADR. Los estados son: Suspensión → Difusión → En membrana → Absorbida/Rechazada. Un rechazo también es conocimiento — se documenta el motivo.

De los ~54 OSM registrados: ~8 Absorbidos (nuclear implementados), ~6 En membrana (diseño completo, cero código o parcialmente), ~35 Suspensión (registrados, sin desarrollar), ~5 Rechazados (con motivo). La disciplina de la membrana evita que las ideas interesantes se conviertan en deuda técnica sin justificación.

### Alto valor, viable en solitario

**COSE/SCITT interop** (future_work #1): codificar los registros como COSE Signed Statements → interoperar con el ecosistema SCITT (IETF emergente). Dep real necesaria (ADR). Alto valor estratégico: pasa de "citamos a SCITT" a "interoperamos".

**Completitud en cadenas de agentes** (future_work #2): counter-firma del receptor en cada salto de una cadena multi-agente. Extiende la completitud del par sujeto↔operador a flujos multi-hop. Encaja directamente con el gateway.

**Métricas de campaña (OSM-001)**: C_attempts/K_attribution — cuántos intentos de abuso detectados, cuántos atribuidos. La demo de cifras que da credibilidad al gateway. Construible con Garak/PyRIT como atacante en harness aislado.

**SessionSalt + PPA (OSM-003, OSM-002)**: randomización de hiperparámetros por sesión + polimorfismo del system prompt. Defensa activa barata. Alta viabilidad, sin deps exóticas.

**Anti-replay en co-firmas (OSM-010)**: ya absorbido parcialmente (`ReplayError` + `_committed` en gateway). Verificar completitud.

### Medio valor, requiere decisión previa

**Dynamic Workflows (SP-E)**: el primitivo nativo del SDK para loops autónomos. Permite que el plan del orquestador persista como workflow (survives compactions). Probado en concepto (CLI 2.1.177+). Bloqueado: requiere que el usuario lance `ultracode:` desde su lado; el runtime no es drivable desde el asistente.

**MCP Tasks extension**: async largo → loop autónomo. Existe como tipos en el SDK pero sin soporte de implementación. Follow-up de las primitivas MCP.

**Watcher automático de subscriptions de catálogo**: `mcp-subscriptions-auto-watcher`. Necesita el low-level loop del server. Diferido.

**Modelo de usuario completo (SP-C)**: trust-scoring de memorias, grafo temporal tipado (kuzu ya instalado), recall verbatim sin resumen (anti-alucinación), user-modeling real. La infraestructura de grafo ya existe (`kuzu>=0.11`). Falta el diseño y la implementación encima.

**TwinDecider (SP-D Slice 3)**: aprende del corpus del RecordingDecider. Primero en shadow (predice, no decide). Requiere Slice 2 (shadow eval: capturar veredicto humano al resolver RequiresHuman).

### Ideas de horizonte (no construir ahora)

**Flota segura**: multi-nodo Atlas con identidad por nodo, comandos firmados, governance state sync. Diseñado en `docs/design/fleet_security_plan.md`. Sin código.

**Regulador de tokens (SP-B)**: conoce el gasto por tarea, sube/baja consumo según dificultad. Concepto, sin spec.

**ZK layers (OSM-015–019, 031)**: Halo2/Nova/PIRANHAS para probar propiedades del log sin revelar contenido. Horizonte de meses cada uno. Diferidos por diseño.

**Hardware attestation (OSM-020)**: AMD SEV-SNP / AWS Nitro para receipts atestados por hardware. Requiere infra de nube confidencial.

**RLAIF / Constitutional AI**: fine-tuning del clasificador con feedback de API (DPO/GRPO). Dep grande. Solo si el scope pasa de "filtro verificable" a "filtro que aprende a clasificar". Riesgo real de scope-creep.

**Fuzzing + red-team (Garak/PyRIT)**: NVIDIA Garak ("Nmap para LLMs"), Microsoft PyRIT (campañas multi-turn). Excelentes herramientas para validar el gateway. No construirlos: adoptarlos como tooling de dev en venv aislado.

**Eje B de seguridad ofensiva (ADR-043)**: análisis estático (taint tracking, SSRF, path traversal), fuzzing dirigido, labs desechables, disclosure responsable. Roadmap en `atlas_max_capability_roadmap.md`. Potente pero requiere aislamiento real (ADR-055 bwrap jail ya resuelve parte).

---

## 8. DECISIONES TOMADAS — ADRs y sus estados

### Cableados (implementados y en uso en producción)

| ADR | Nombre | Estado real |
|---|---|---|
| ADR-024 | Observabilidad v2, MerkleLogger, WAL | Cableado — cadena Merkle viva |
| ADR-025 | ColdUpdateManager | Cableado — propuesta→worktree→validate→apply→rollback |
| ADR-029 | Búsqueda full-text + reverse audit | Cableado |
| ADR-030 | Block memory (Letta/MemGPT) | Cableado — KuzuVectorStore + error_registry |
| ADR-031/032/033 | Loop agéntico suspendible, HITL inline, TTL | Cableado |
| ADR-034/035/036/037/038 | Hardening, cliente MCP, threat model, frontera no-confiable, SentinelGate | Cableado |
| ADR-039 | Self-maintenance agent | Cableado, gated (`ATLAS_SELF_AUDIT_SCHEDULER`) |
| ADR-040 | Decisor central human-ON-the-loop | Cableado — `AutonomousDecider` + `HumanDecider` |
| ADR-041 | Verificador universal `verify(artifact)→Evidence` | Cableado |
| ADR-047 | Panel adversarial (pieza 1) | Cableado — `AdversarialPanel` |
| ADR-048 | VerifiedProducer (fases A-F) | Núcleo completo, sin cableado al worker vivo |
| ADR-053 | Compliance Gateway trust model (núcleo) | Cableado — log RFC 9162 + co-firma + crypto-shred |

### Durmientes (construidos, sin consumidor real o gated-off)

| ADR | Nombre | Estado |
|---|---|---|
| ADR-042 | Cascada con routing (Capa 2) | Construido, 1 consumidor real, sin CLI/trigger autónomo |
| ADR-044 | LessonStore (Capa 4) | Núcleo sin consumidores |
| ADR-045/046 | Enjambre sobre blackboard | Vivo y gated (`ATLAS_SWARM_SCHEDULER`), propuesta-only |
| ADR-049 | Organismo de conocimiento (slice 1) | Slice 1 completo; slices 2-6 pendientes |

### Propuestos (sin implementación)

| ADR/OSM | Nombre | Estado |
|---|---|---|
| ADR-043 | Autorización verificable + SECURITY_FINDING | Propuesto, sin código |
| ADR-051 | Compliance Gateway (capa completa con entrypoint) | Propuesto — núcleo en ADR-053 |
| ADR-052 | Asimilación de Odysseus (chat UI, deep research, etc.) | Propuesto — sin código |
| ADR-054 | Defensa en profundidad por engaño (shadow model) | Parcialmente en OSM-042 Absorbida |
| ADR-055 | Jail OS-level (seccomp + namespaces + seccomp-bpf) | Propuesto — mitigación parcial SEC-5 hecha |
| ADR-056 | (referenciado) dev-only para red-team | Propuesto |

---

## 9. DEUDAS TÉCNICAS REALES

Estas son las encontradas en auditorías, no estimadas. Algunas críticas, otras conocidas y acotadas.

### Hallazgos verificados en auditoría enjambre 2026-06-26 (con evidencia archivo:línea)

Estas son las grietas encontradas leyendo código real, no los docs. **Verificadas en vivo.**

**[CRÍTICO] Log in-path efímero — no persiste** (`orchestrator.py:1090`): `TransparencyLog` se construye sin `path=`. Todas las pruebas, STHs e InspectionRecords se evaporan al cerrar el proceso. Un comprador no puede auditar nada de ayer. El soporte de persistencia existe (`log.py:111-149`) pero no está cableado.

**[CRÍTICO] No existe verificador de tercero ejecutable**: las 6 comprobaciones de `APIResponse` (`client_cosign.py:254-300`) no las corre ningún CLI ni cliente enviado. La propiedad "verificable por un tercero" es teórica. Falta: `atlas verify` o equivalente.

**[CRÍTICO] baseline LongMemEval medía `StubEmbedder`** (`eval_longmemeval.py:213`): el 0.356 no medía la memoria semántica real. **Medición real hoy (n=500, fastembed): 0.934 R@5** — a 2-3 pts del SOTA. El número del doc viejo es un artefacto de configuración. El `SqliteMemoryIndex` usa `StubEmbedder(dim=64)` por defecto (`memory_index.py:209`) — necesita corrección.

**[ALTO] InferenceHub no cableado al pipeline por defecto** (`pipeline_runner.py:408`): con Gate-D off (default), LOCAL_SAFE cae a passthrough fijo. El router de inferencia no enruta en el camino real.

**[ALTO] DNS rebinding en fetcher de Scouts** (`knowledge/sources.py:51-61`): `_urllib_fetcher` llama `urlopen(req)` con la URL original, descartando `decision.pinned_ip`. Re-resuelve DNS entre `check()` y la conexión — exactamente la ventana que el executor sí cierra. Todos los Scouts de contenido no-confiable usan este path.

**[ALTO] `execute_command` no usa jail** (`sandbox.py:122-156`): solo rlimits + `start_new_session`. Comandos shell de la allowlist corren con uid del usuario, FS completo, red abierta. El bwrap solo aplica a `cap.code is not None`.

**[MEDIO] `self-audit report` crashea al arrancar** (verificado en vivo hoy): `orchestrator.py:1060` intenta abrir `KuzuVectorStore` en `enable_gate_d_pipeline()` sin que exista la DB. Atlas no puede revisarse a sí mismo con este comando.

**[MEDIO] Coseno reescalado contamina ranking** (`lesson_recaller.py:83-90`): `(raw+1)/2` → vectores ortogonales puntúan 0.5, no 0. Items irrelevantes pero recientes sobreviven al ranking. Threshold 0.8 opera sobre escala comprimida (≈ coseno crudo 0.6).

**[MEDIO] seccomp ausente fuera de x86_64** (`bwrap_jail.py:240-241`): en ARM (Graviton, Apple Silicon) el jail corre sin seccomp — ptrace/unshare disponibles. Warning, no fail-closed.

**[MEDIO] Anti-replay solo en memoria** (`gateway.py:115`): el set `_committed` se pierde al reiniciar. Combinado con log efímero, tras reinicio se aceptan seqs ya vistos.

**[BAJA] `.pyc` huérfanos delatan erosión**: `red_team.pyc`, `kyc_binding.pyc`, `witness_server.pyc`, `gossip.pyc`, `fuzzing.pyc` — fuentes borradas, mencionadas en docs. Señal de capacidades reclamadas en docs pero sin código fuente.

**Ratio ADRs verificada hoy**: 8 CABLEADOS / 14 DURMIENTES / 1 PROPUESTO. Los cableados son la columna operativa mínima (agentic loop, decisor, hermes, block_memory, process_hardening, MCP client, cold_update). Todo lo de "ambición" (verificación universal, enjambre, producers, lesson_store, knowledge organism, InferenceHub con transparencia) está durmiente detrás de flags `ATLAS_*_SCHEDULER=1` apagados por defecto o detrás de Gate-D opt-in.

---

### Críticas previas (bloquean producción o seguridad real)

**ASTGuard bypasseable** (ADR-055, propuesto): PoC verificado en vivo (getattr + concatenación de strings evade el denylist). SEC-5 degradó ASTGuard a lint con docstring honesto. El bwrap jail existe pero no cubre todos los paths de ejecución de código generado (seccomp-bpf y namespaces completos están en ADR-055 Propuesto, no Implementado).

**Log sin persistencia durable y Rate-limit (OSM-032)**: el log existe en SQLite pero sin rate-limiting. Un atacante puede llenarlo (DoS del log). Diferido.

**PII en memoria de usuario (Fase 2.2)**: el crypto-shredding del gateway está implementado para el compliance gateway, pero la memoria del usuario (SqliteMemoryIndex) puede contener PII sin crypto-shred. GAP-1 GDPR para el caso de uso de agente.

### Conocidas y acotadas (no bloquean, pero hay que saber que existen)

**Self-audit crasheaba en el loop**: resuelto en la auditoría 2026-06-22. Hoy el lazo de aprendizaje auditable está cableado y probado.

**DNS rebinding en Scouts**: el SSRF bridge está en allowlist a nivel de conexión (TLS contra hostname). DNS rebinding entre lookup y conexión es un vector residual conocido.

**`execute_command` sin jail completo**: el bwrap jail existe, pero el path de `execute_command` en el orquestador no está garantizadamenteguardado detrás de él en todos los code paths.

**Coseno reescalado (resuelto)**: la deuda de tener dos implementaciones de coseno fue cerrada por autobuild (2026-06-22). La canónica está en `vector_store`, `lesson_recaller` delega.

**La eval medía stub (resuelto)**: el benchmark de memoria medía el `StubEmbedder` (hash, no semántico). Corregido al migrar a fastembed. Los números reales de LongMemEval_S son los citados.

**Git history con commit mal etiquetado**: existe `cd01791` con el mismo mensaje que el commit del RecordingDecider pero contenido = regeneración YAML de catálogo (confusión de `chore/mcp-sync`). Decisión tomada: NO reescribir historia (coste/beneficio pésimo con 426 commits, tags, ~30 ramas Hermes). Documentado y acotado.

**Starlette warning**: pendiente. Bajo impacto.

**Warning de `git apply` sin marcador `\ No newline at end of file`**: los transforms newline/EOF del arnés producen diffs que `git apply` rechaza. Robustecer antes de añadirlos al arnés.

**Snapshot integrity del ColdUpdate**: resuelto en `_commit_with_evidence` (commit con verdict/exits/origin/proposal_id). Los aplicados autónomos ya no quedan huérfanos.

**365 worktrees huérfanos**: limpiado el 2026-06-13. El bug raíz (secuestro por env git) fue cerrado con `_clean_git_env()` + test de regresión. No debería reaparecer.

---

## 10. PREGUNTAS ABIERTAS

Estas preguntas no tienen respuesta aún. Cada una bloquea o define una dirección.

### Q1: ¿Construir primero para Tomás o para mercado?

El porqué original es personal: Tomás quiere el asistente de código local. El mercado potencial del gateway de compliance es diferente y probablemente más grande (B2B, EU AI Act). Pero un producto B2B requiere multi-tenancy, SLAs, soporte — cosas que una persona sola no puede sostener.

**Hipótesis a probar**: si el asistente de código local funciona bien para Tomás, eso es el demo real del gateway (un usuario real usando el sistema, con log auditable). No son caminos distintos si se secuencian bien.

### Q2: ¿Osmosis como producto independiente o como capa de Atlas?

El núcleo criptográfico es independizable. El paper va a cs.CR. El posicionamiento es diferente. Pero "dos proyectos" para una persona sola es insostenible.

**Opciones**:
- A: Atlas es el producto; Osmosis es la capa de compliance interna (no se comercializa separado).
- B: Osmosis se publica como librería open-source / reference implementation; Atlas la usa como primera implementación de referencia.
- C: Se busca colaborador o empresa para llevar Osmosis al mercado mientras Tomás mantiene Atlas.

### Q3: ¿Modelo de usuario antes o gateway cableado antes?

El modelo de usuario (Gota 1) es lo que hace al agente de código útil para Tomás. El gateway cableado (entrypoint HTTP, verificador cliente) es lo que hace al compliance gateway comercializable. Son caminos ortogonales que compiten por el mismo tiempo.

**Criterio de desempate propuesto**: lo que desbloquea el uso diario de Tomás va antes. Si Tomás no usa Atlas todos los días, el modelo de usuario no aprende. Sin uso diario, el sistema no madura. La usabilidad personal es la condición necesaria del resto.

### Q4: ¿Cuándo encender el enjambre con auto-apply?

El enjambre propone parches de mantenimiento mecánico. Auto-apply está OFF. Para encenderlo:
- La auditoría de muestra (`reverify_swarm_proposals`) debe mostrar ≥N ciclos limpios (ningún patch aceptado que luego falle).
- El decisor debe tener suficiente historial en el `RecordingDecider` para que el `TwinDecider` pueda empezar.
- El operador (Tomás) debe estar cómodo con que el sistema toque el repo sin confirmación explícita.

**Posición actual**: no hay suficiente historial. Encender antes de tener evidencia sería vapor.

### Q5: ¿Publicar el paper ahora o después de más resultados?

El paper está listo y verificado. El endorsement en cs.CR está pendiente (requiere contactar investigadores de IMDEA u otros). La pregunta es si publicar ahora (antes de tener la entrypoint HTTP y el demo completo) o esperar.

**Argumento para publicar ahora**: el mecanismo es real y demostrable hoy. Esperar a tener más puede significar nunca publicar.
**Argumento para esperar**: el demo sin entrypoint HTTP no es un producto. Un revisor puede preguntar "¿dónde se despliega esto?". Tener la API lista refuerza la credibilidad.

**Decisión de desempate sugerida**: publicar el paper cuando el endorsement llegue, independientemente de la API. El mecanismo es correcto y demostrable hoy. La API es infraestructura de producto, no contribución académica. No hay beneficio en esperar.

### Q6: ¿Qué hacer con las ~30 ramas Hermes sin mergear?

Existe un backlog de ramas del proyecto Hermes (agente Telegram en VPS) que nunca se mergearon. Hermes VPS está dado de baja. Las ramas contienen trabajo potencialmente útil. La poda auditada fue diferida. Grace period para el graveyard F3 expira 2026-07-21.

**Acción necesaria**: decidir si hacer poda auditada antes del 2026-07-21, o diferir de nuevo. No es urgente pero sí es deuda de higiene.

### Q7: ¿Cómo medir si el asistente de código está funcionando?

Sin métrica de "está funcionando para Tomás" no hay forma de saber si el modelo de usuario está aprendiendo, si el routing determinista ayuda, o si el sistema es mejor que Claude Code sin Atlas. Las métricas candidatas:

- Frecuencia de uso diario (¿Tomás abre Atlas cada día o lo evita?).
- Número de confirmaciones HITL necesarias por sesión (debería bajar con el tiempo).
- Proporción de sugerencias aceptadas sin edición (proxy de que el modelo de usuario funciona).
- Tiempo hasta primera acción útil desde el arranque (UX).

Sin estas métricas, el desarrollo es a ciegas. El `RecordingDecider` ya graba las decisiones — las métricas son una capa de análisis encima.

### Q8: ¿En qué orden atacar las 6 gotas?

La intuición es lineal (1→2→3→4→5→6) pero las gotas no son independientes. El sustrato (3) ya existe. La acción segura (5) ya existe. La composición (4) parcialmente. Lo que falta tiene dependencias:

- La captura de intención ambiente (2) depende del modelo de usuario (1): sin saber quién es el usuario, cualquier señal ambiente es ruido.
- La adaptación continua (6) depende del modelo de usuario (1) y del lazo de auto-mejora (LessonStore + enjambre).

Por tanto la secuencia forzada es: **1 (modelo de usuario) → 2 (captura ambiente) → 6 (adaptación)**, con 3/4/5 ya disponibles como infraestructura.

El modelo de usuario (1) no requiere un sistema nuevo — requiere cablear lo que existe: `RecordingDecider` corpus → `TwinDecider` → routing que usa el modelo para personalizar la selección de herramientas.

---

## Apéndice A: inventario de ficheros clave

Los ficheros más relevantes para entender el sistema, con su propósito real.

### Código cableado y en uso

```
src/atlas/core/decider/
  __init__.py                   — make_decider(), ATLAS_DECISION_LOG, opt-in
  decision_record.py            — DecisionRecord, DecisionSink, JsonlDecisionSink
  recording_decider.py          — RecordingDecider (wrapper transparente)
  memory_decision_sink.py       — MemoryDecisionSink (Fernet+shred+merkle)

src/atlas/memory/
  sqlite_memory_index.py        — SqliteMemoryIndex (motor principal)
  fastembed_embedder.py         — FastEmbedEmbedder (ONNX, sin torch)
  hybrid_retrieval.py           — FTS5 léxico + RRF fusion
  temporal_retrieval.py         — recall_temporal, as_of

src/atlas/transparency/
  log.py                        — TransparencyLog (RFC 9162, append-only)
  client_cosign.py              — co-firma monótona, detección de omisión
  crypto_shred.py               — SaltStore, InspectionRecord.salted_hash
  gateway.py                    — TransparencyGateway (núcleo Osmosis)
  shadow_model.py               — ShadowRouter, ShadowMode (OSM-042)
  behavioral.py                 — BehavioralMonitor, BehavioralDelta (OSM-054)

src/atlas/mcp/
  trunk_server.py               — TrunkAggregator, build_trunk_server
  catalog.py                    — CatalogEntry, TaxonomyV3, load_taxonomy
  memory_server.py              — MemoryTrunk + shell FastMCP
  knowledge_server.py           — KnowledgeTrunk (Wikipedia, WorldBank, Open-Meteo, Frankfurter)
  operating_server.py           — OperatingTrunk (AGENTS.md + WORK_LEDGER como Resources)
  skill_store.py                — SkillStore (sirve docs/skills/*.md como Prompts MCP)
  trunk_capabilities.py         — Completion, Elicitation, Sampling, Roots, Subscriptions

src/atlas/core/
  verify.py                     — UniversalVerifier, Evidence, CostTier (Capa 1)
  swarm.py                      — Blackboard, coordinador, envelopes (Capa 3)
  swarm_cycle.py                — SwarmCycle, daemon in-process
  cold_update_manager.py        — ColdUpdateManager (ADR-025)
  adversarial_panel.py          — AdversarialPanel (ADR-047)
  verified_producer.py          — VerifiedProducer (ADR-048)
  lesson_store.py               — LessonStore (ADR-044, sin consumidores)

src/atlas/router/
  cascade.py                    — CascadeRouter, CostLedger (Capa 2, 1 consumidor)

src/atlas/core/self_maintenance/
  scheduler.py                  — MaintenanceScheduler (scouts + cron)
  registry_scout.py             — scoutea registros MCP
  dep_scout.py                  — detecta actualizaciones de deps
  self_improvement.py           — SelfImprovementBridge (CVE → propuesta ColdUpdate)

src/atlas/knowledge/
  mission.py                    — KnowledgeMission, run_mission()
  sources/                      — WikipediaSource, WorldBankSource, OpenMeteoSource, FrankfurterSource

src/atlas/immunity/             — sistema inmune (gateway de IA)
  gateway.py                    — TransparencyGateway (alt. path)
  drift.py                      — drift tripwire
  inspector.py                  — ScopedInspector

src/atlas/interfaces/
  cli.py                        — CLI principal (atlas reality, atlas capabilities, etc.)
  orchestrator.py               — Orquestador principal (~2029 LOC post-split)
  exec_api.py                   — /api/exec/intent (ADR-027)
```

### Documentos de diseño fundamentales

```
AGENTS.md                       — instrucciones completas para agentes (leer primero)
WORK_LEDGER.md                  — estado vivo de todas las líneas activas
ROADMAP.md                      — dirección y principios (no duplica counts)
docs/governance/CAPABILITIES.md — honestidad de cada capacidad declarada

docs/design/
  direction_2026-06-12_construir_hacia_arriba.md  — la tesis estratégica fundacional
  design_verifiable_memory.md   — diseño de memoria verificable (Fases 1-2)
  design_deliberation_council.md — Cónclave: protocolo, roles, profundidad adaptativa
  mcp_trunk_portable.md         — arquitectura del tronco MCP
  backlog.md                    — todo lo diferido explícitamente (con motivo)
  plan_orchestrator_decomposition.md — cómo se descompuso el god-object

docs/membrana/
  OSM-000_membrana.md           — mecanismo de ósmosis de conocimiento externo
  [OSM-024 a OSM-054]           — candidatos en distintos estados (Suspensión/Difusión/Membrana/Absorbida)

docs/reference/
  adr/adr_040_decider_*.md      — Decisor central (Implemented)
  adr/adr_051_compliance_*.md   — Compliance Gateway (Propuesto)
  adr/adr_053_gateway_trust_*.md — Confianza del gateway (Aceptado/núcleo)
  compliance/eu_ai_act_gaps_*.md — 4 gaps verificados (GAP-1 cerrado, 2-4 abiertos)
```

---

## Apéndice B: el Cónclave — mecanismo de deliberación

El Cónclave (`deliberation_council`) es el mecanismo de decisión multi-voz de Atlas. No es solo una herramienta — es la forma en que el proyecto toma decisiones difíciles de arquitectura.

### Protocolo (4 pasos, coste escalonado)

1. **Encuadre (juez solo, barato)**: reformula la decisión + criterios de éxito + qué manías del repo están en juego.
2. **Lentes (juez solo, barato)**: solo los Sombreros que la decisión necesita — normalmente Negro (riesgos) + Verde (alternativa quirúrgica); Blanco (hechos) y Amarillo (upside) cuando aplica. No seis secciones siempre — eso recrearía el bloat.
3. **Escalada (trío, caro — solo alto riesgo / irreversible)**: convoca `AdversarialPanel.verify` con los tres proveedores. Diversidad obligatoria: si no hay diversidad mínima viva → veredicto UNKNOWN (unknown > mentir).
4. **Síntesis honesta (juez)**: muestra el desacuerdo crudo del trío ANTES de resumir. Cierra con PASS / FAIL / UNKNOWN (tipo `Evidence` de la capa 1).

### Roles (slots pluggable)

| Rol | Implementación actual | Permanencia |
|---|---|---|
| Juez / Maestro (silla) | Claude (Anthropic, US) | slot pluggable |
| Voz 1 | Gemini (Google, US) | permanente |
| Voz 2 | Kimi (Moonshot, CN) | permanente |
| Voz 3 | Mistral-Large-3 (Mistral, EU) | permanente |

El trío = US + CN + EU, tres linajes ortogonales. La silla no vota. El valor está en ver dónde discrepan las voces — ahí está lo complejo del problema.

### Estado actual (2026-06-26)

- v2.0: 3/3 voces útiles en smoke vivo (post-fixes: `gemini_free`→`gemini-2.5-flash`, reintento ante transitorios, parseo anclado a 1ª línea).
- v2.0.5 pendiente: fallback de slot por-linaje (cura el fallo correlacionado NIM: Kimi+Mistral comparten infra NIM).
- Deuda menor: cablear `record_synthesis` al LessonStore real.
- v2.1 (debate por rondas) y v2.2 (puerta de reinicio de loop): diferidos.

### El Cónclave como instancia de la tesis Atlas

El Cónclave es la primera demostración concreta del principio "autonomía gobernada real": el sistema toma decisiones difíciles con deliberación multi-voz, sin depender del criterio único del autor, con trazabilidad (registro de la síntesis), y con diversidad geográfica obligatoria. No es vendor lock-in — es arquitectura anti-cámara-de-eco.

---

## Apéndice C: principios operativos del proyecto (anti-deriva)

Estos principios están formalizados en `AGENTS.md` y `docs/skills/atlas-coding-discipline.md`. Se reproducen aquí para que el plan externo los respete.

**wire-before-claim**: no se declara una capacidad hasta que hay código + test + consumidor real. Código sin importador no-test = vapor; cablear o cuarentena. Este principio eliminó claims vacíos que habían acumulado deuda.

**prove-it**: antes de depender de algo (librería, repo, API, tool externo), ejecutarlo una vez y verificar que funciona. Verificación antes que aserción. Aplica también a citas de papers (se verificaron con WebFetch antes de incluirlas en el paper).

**stdlib > deps**: cada dependencia nueva se gana su lugar. La mayoría de la funcionalidad usa stdlib Python. Las excepciones son explícitas (fastembed para embeddings, kuzu para grafos, mcp para el protocolo).

**honestidad de capacidades**: el fichero `docs/governance/CAPABILITIES.md` distingue "real" / "andamiaje-software" / "no-cableado" / "no-existe". Nunca mezclar tests verdes con funcionar en producción.

**adopt-real-not-shell**: descargar → aislar → diseccionar → envolver con mínimo código nuevo. Reimplementar desde cero deja un cascarón vacío. Pasó con Sentinel/Hermes: se reimplementaron conceptos en vez de adoptar las herramientas reales. El catálogo MCP sigue esta regla: adopta escáneres existentes (Invariant mcp-scan, Snyk agent-scan) en vez de construir un antivirus propio.

**research-before-deciding**: barrer SOTA (papers/productos/benchmarks) y compararlo con lo propio ANTES de decidir. El programa de memoria fue sentenciado así por el Cónclave: "MEDIR primero (LongMemEval_S), híbrido segundo, decay NO".

**estado en el ledger**: `WORK_LEDGER.md` es la fuente única del "¿dónde estamos?". Se actualiza en el mismo commit que el trabajo. Si no está en el ledger, no cuenta como hecho.

**capability routing estructural**: el uso de MCP/skills/prompts debe ser estructural (hook/router que consume un manifiesto), no discrecional del modelo. Un modelo elige probabilísticamente; un router fuerza determinísticamente.

**sustrato unificado**: el Cónclave, el decisor y el propio Claude comparten UNA memoria y las mismas reglas. Sin silos. Los invariantes de firewall-sensibilidad y anti-cámara-de-eco aplican a todos los generadores.

---

## Apéndice D: el paper de completitud verificable

El paper "Subject-Enforced Completeness in AI Transparency Logs" (17 páginas, cs.CR) es el artefacto académico del proyecto. Su contribución central:

> El sujeto (usuario) puede verificar por sí mismo — usando solo los datos que el sistema le entrega — que no fue inspeccionado más allá de la causa declarada. Esto es completitud verificable desde el lado del sujeto, no del operador.

Esto distingue a Atlas de los sistemas de transparencia unilateral: el operador no puede "inspeccionar y no apuntarlo" porque el cliente vigila su propia secuencia monótona (co-firma RFC 9162). Una laguna en la secuencia es evidencia de omisión.

**Estado del paper**:
- Texto: completo y verificado (17 páginas)
- Citas: 6 referencias 2025/2026, verificadas con WebFetch (CONIKS, CT v2, SCITT, Sello, Aegis, Auditable Agents)
- Sellado: OpenTimestamps (confirmación Bitcoin pendiente), firma GPG de autoría
- Backup: github.com/therealronin23/atlas (remoto privado)
- Publicación: pendiente de endorsement en cs.CR (necesita contactar IMDEA u otros)
- Demo reproducible: scripts en el repo, reproducibles sin infraestructura externa

**Lo que el paper NO afirma** (honestidad crítica):
- No afirma tasas de detección absolutas (dependen del clasificador, hoy básico)
- No afirma que el camuflaje semántico real sea fácil de detectar
- No afirma que el inspector que ve contenido en claro sea inexpugnable (es la mayor superficie de ataque)
- No afirma que el sistema escale a enterprise (eso requiere despliegue real, no opinión de tercero)

---

## Apéndice E: las manías del proyecto (anti-patrones identificados)

Estos son los patrones dañinos que el proyecto identificó en sí mismo y formalizó como manías en `MEMORY.md`. Un plan externo debe evitar reintroducirlos.

**Construir sin norte claro**: el porqué derivado ("ser el primer OS multiagente") consumió el porqué real ("asistente de código para Tomás"). Un plan que vuelva a ampliar el scope sin tener el porqué original satisfecho reproducirá el mismo error.

**Reimplementar en vez de adoptar**: el caso Sentinel/Hermes — se construyeron conceptos en vez de adoptar herramientas reales. Resultado: código propio que no tiene el battle-testing de las herramientas que inspira. La regla `adopt-real-not-shell` lo previene.

**Vapor / wire-before-claim violado**: declarar capacidades sin tenerlas cableadas. El fichero CAPABILITIES.md nació de este antipatrón. Un plan que añada items al roadmap sin código concreto reproduce el error.

**Deepening HITL coupling**: añadir más puntos de aprobación humana en vez de construir invariantes que los reemplacen. El principio `no-deepen-hitl-coupling` lo previene. El Decisor central (ADR-040) fue la respuesta arquitectónica.

**Sobre-afirmar en revisión**: el trío del Cónclave tiende a sobre-afirmar. La manía `challenge-the-trio` exige corregirles cuando lo hacen, especialmente a ellos para que memoricen (hoy son one-shot/sin estado — falta cablear store de correcciones).

**Correr el SOTA sin medir primero**: la memoria híbrida parecía mejor que la simple. El Cónclave forzó a medir con LongMemEval_S antes de afirmar. Los números reales: híbrido +21% sobre coseno, pero no el factor ×3 que algunos papers afirman sin baseline honesto.

---

## Apéndice: arquitectura de capas de referencia

```
USUARIO
   │
   ├── CLI / Telegram / exec_api (/api/exec/intent)
   │
   ▼
ORQUESTADOR (orchestrator.py, ya descompuesto)
   │
   ├── [Capa 0] Decider central (ADR-040) — Allow/Deny determinista
   │      └── AutonomousDecider (invariantes) / HumanDecider / híbrido
   │
   ├── [Capa 1] Verificador universal (ADR-041) — verify(artifact)→Evidence
   │
   ├── [Capa 2] Cascada routing (ADR-042) — DURMIENTE, 1 consumidor
   │
   ├── [Capa 3] Enjambre + blackboard (ADR-045/046) — GATED-OFF
   │      └── VerifiedProducer (ADR-048) — A-F construido, sin consumer vivo
   │
   ├── [Capa 4] LessonStore (ADR-044) — DURMIENTE, sin consumidores
   │
   ├── MCP Trunk (atlas-trunk, 1 conexión)
   │      └── 3 raíces: memoria + operating + knowledge-src
   │      └── 3+ externos: sequential-thinking, mcp-memory, everything
   │      └── Catálogo: 700+ en 9 dominios, 12 instalados
   │
   ├── InferenceHub — Groq→OpenRouter→Together→Gemini→NVIDIA L2
   │
   ├── Cónclave (deliberation_council) — 3/3 voces vivas (Gemini+Kimi+Mistral)
   │
   ├── Memoria (SqliteMemoryIndex + fastembed + FTS5 + temporal + Merkle)
   │      └── RecordingDecider + MemoryDecisionSink (corpus de decisiones)
   │
   └── Compliance Gateway (transparency/)
          └── Log RFC 9162 + co-firma + crypto-shred + shadow model
```

---

## Resumen ejecutivo en 10 bullets

Para el lector que no puede leer el documento completo antes de planificar:

1. **Atlas es un runtime local de IA** con tres capas superpuestas: agente de código, orquestador multi-agente gobernado, y gateway de compliance. Una persona lo construyó.
2. **El porqué original** (asistente de código local, gratis, que te conoce) fue oscurecido por el porqué derivado (OS multiagente que lo hace todo). El norte real sigue siendo el original.
3. **Lo que funciona hoy**: 2364 tests, memoria semántica con 0.934 R@5, tronco MCP desplegado (700+ herramientas), Cónclave deliberativo 3/3 voces, compliance gateway con núcleo criptográfico sólido (RFC 9162).
4. **Lo que falta para el asistente de código**: modelo de usuario (Gota 1), routing determinista de capacidades (Pieza 3 del catálogo), flujo de uso diario que use el sustrato.
5. **Lo que falta para el gateway de compliance**: entrypoint HTTP, verificador cliente distribuible, Technical File Anexo IV.
6. **Las capacidades durmientes más valiosas**: enjambre + ColdUpdate (auto-apply OFF, encendible con auditoría previa), cascada con routing (sin consumidor principal), LessonStore (sin consumidores), TwinDecider (no construido).
7. **Deudas técnicas críticas**: ASTGuard bypasseable (SEC-5 aplicado, ADR-055 propuesto), PII en memoria de usuario sin crypto-shred, entrypoint HTTP del gateway inexistente.
8. **El mecanismo de decisión más valioso**: el Cónclave. Tres linajes ortogonales (US+CN+EU) deliberan antes de decisiones difíciles. Anti-cámara-de-eco por diseño.
9. **ADRs clave**: ADR-040 (decisor central, Implemented), ADR-053 (gateway trust model, Aceptado/núcleo), ADR-042 (cascada, durmiente), ADR-044 (LessonStore, durmiente), ADR-051 (compliance gateway completo, Propuesto).
10. **La pregunta que define el plan**: ¿construir primero lo que Tomás usa todos los días (modelo de usuario + routing), o lo que tiene valor de mercado propio (gateway HTTP + API)? La respuesta correcta probablemente es: el uso diario primero, porque sin uso no hay datos para nada.

---

## PROMPT SUGERIDO PARA LLEVAR ESTE DOC A CLAUDE/GPT

```
Eres un consultor de producto y arquitectura. Te adjunto la síntesis completa
del proyecto Atlas. Lee todo. Tu trabajo: dado que el autor es una persona sola
con tiempo limitado, y conociendo el estado real del código, diseña UN PLAN
CERRADO con máximo 3 líneas de trabajo simultáneas, hitos concretos de 2 semanas,
y criterios de 'done' medibles. El plan debe poder seguirse sin perder el norte
aunque pasen meses. No me des opciones — dame el plan que tú ejecutarías.

Restricciones que debes respetar:
- Una persona sola. No hay equipo. No hay funding.
- El porqué original es personal: asistente de código local que te conoce, gratis.
- El gateway de compliance (Osmosis) tiene valor propio pero no puede ser dos proyectos.
- El sistema tiene 2364 tests pasando, MCP trunk desplegado, memoria con 0.934 R@5.
  No partir de cero: construir encima de lo que funciona.
- wire-before-claim: nada se declara hecho sin código + test + consumidor real.
- No añadir deps sin ADR. No construir lo que ya existe. No reinventar.
- El plan debe arrancar con lo que desbloquea el uso diario de Tomás (modelo de usuario
  + routing determinista de capacidades), no con lo que suena más impresionante.
```
