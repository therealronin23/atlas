# Auditoría integral adversarial — pre-mortem y post-mortem

**Fecha:** 2026-07-16

**Checkout auditado inicialmente:** `f7c537a0` con trabajo previo sin commitear

**Autoridades:** evidencia viva, código y pruebas; los documentos históricos no
prevalecen sobre ellas.

## Veredicto ejecutivo

La auditoría encontró fallos reales de frontera, autenticación, persistencia,
operación y honestidad documental. Se repararon dentro del alcance y se
añadieron regresiones. El core local queda verificable y mucho más fail-closed,
pero **no se declara producción externa completa**:

- Hermes, su VPS, proveedor y Telegram no se probaron en vivo en este entorno.
- Neo4j no estaba activo ni había credenciales configuradas.
- La allowlist seccomp portable de ADR-055 no está terminada; el filtro actual
  es una denylist x86_64 sobre un jail de namespaces/montaje/red ya activo.
- Crawl4AI real quedó omitido porque `.venv-scraping` no está instalado; el
  resto del marcador browser/computer-use sí se ejecutó.
- Un proceso externo Claude/Google Workspace exponía un client secret OAuth en
  su línea de comandos. No estaba en `HEAD`; requiere rotación en Google y
  reinicio del conector, acciones que no pueden cerrarse solo desde este repo.

No se modificó `config/governance.json`, no se instaló software de terceros y
no se desplegó ni contactó un VPS.

## Método

1. `atlas reality --json`, integridad Merkle y presupuesto de proveedores.
2. Tronco MCP y grafo estructural antes de razonar sobre radio de impacto.
3. Graphify estructural y consulta semántica GraphRAG; export Neo4j inspeccionado
   sin asumir que una exportación equivale a una base viva.
4. Revisión por ejes: seguridad, corrección, arquitectura, rendimiento,
   operabilidad, supply chain, documentación y estado externo.
5. Investigación upstream de Hermes contra fuentes primarias y checkout exacto
   de la versión adoptada.
6. Pre-mortem, pruebas rojas para fallos nuevos, cambios pequeños/reversibles,
   suite dirigida y suite completa.
7. Post-mortem con límites y deuda residual explícitos.

El tronco informó que su proyecto Kuzu estaba `STALE`: snapshot
`08562bed…` frente a `HEAD f7c537a…`. Importadores, imports y blast radius
fallaron cerrados, como deben; churn siguió disponible y situó el orquestador
entre los hotspots. Graphify encontró la cadena Orchestrator → capacidades →
sandbox y los nodos Hermes/Kanban, pero advirtió que la exportación usaba el
esquema de IDs anterior al fix #1504. Esas limitaciones guiaron la decisión de
reconstruir los grafos solo después de fijar un commit coherente.

## Pre-mortem

Antes de reparar, se asumió que la auditoría podía fracasar de estas formas:

| Fallo previsto | Señal temprana | Mitigación aplicada |
| --- | --- | --- |
| Declarar “vivo” algo solo configurado o descrito | Docs contradicen `atlas reality`; smoke usa mock/stub | Estado con `configured` y `live_verified`; mapa canónico corregido; smokes aislados/legados etiquetados |
| Un input remoto cruza una frontera de filesystem o red | Provider usado en path, DNS re-resuelto, redirect automático | Nombres content-addressed, `O_NOFOLLOW`, conexión al IP validado, redirects revalidados |
| La autenticación identifica lo que dice el cliente | `approved_by`, chat de grupo o cabecera sin identidad server-side | Identidad derivada del token/canal; chat y usuario comprobados; claims de body ignorados |
| Código/comando autorizado escapa al host | Allowlist de comando sin mount/net namespace | Todo `execute_exec` por bwrap; mounts mínimos; cwd RO por defecto; fail-closed |
| Logs/memoria aceptan corrupción silenciosa | Symlinks, permisos abiertos, dimensión igual entre modelos distintos | Ficheros privados regulares, identidad/fingerprint de embedding, migración fail-closed |
| La auditoría causa el incidente que busca | `source .env`, workspace vivo, smoke que envía Telegram, proceso enorme | Dotenv como datos, HOME aislado, batching, pairing read-only y opt-in |
| El grafo da respuestas convincentes pero viejas | SHA del grafo distinto de HEAD o source dirty | Freshness explícita y rechazo de consultas estructurales sensibles |
| El despliegue externo queda mutable/privilegiado | `latest`, pip flotante, root runtime, secreto en argv, IP pública | Tag+commit+lock, hash de bootstrap, usuario dedicado, fichero `0600`, Tailscale/private only |
| Optimizar rompe trazabilidad | Tail carga todo; logs incluyen argumentos/títulos | Reverse tail acotado; contenido sensible sustituido por count+SHA-256 |

## Hallazgos y remediación

### P0 — fronteras críticas

1. **OS Bridge accesible sin identidad robusta fuera de loopback.** Se añadió
   token fuerte para bind remoto, comparación constante, rechazo de DNS
   rebinding por `Host`, autenticación HTTP/WebSocket, validación de `Origin` e
   identidad server-side para aprobar/rechazar business cores.
2. **Comandos estructurados fuera del jail.** La allowlist limitaba nombres,
   pero el proceso conservaba filesystem/red del usuario. `AtlasExecutor` usa
   ahora `BwrapJail` también para argv: red aislada, rootfs mínimo, cwd RO por
   defecto, inputs RO declarados, escritura específica para `patch`, captura
   acotada y error explícito sin `bwrap`.
3. **Traversal y enlaces en importación de conversaciones.** `provider` podía
   influir en el nombre de fichero. Ahora se valida como identificador, el raw
   se nombra por digest, se verifica contención y todos los ficheros/directorios
   usan creación privada, exclusiva y sin seguir symlinks.
4. **SSRF con ventana DNS/redirect.** El sink podía validar un hostname y dejar
   que la conexión lo resolviera de nuevo. La conexión se fija al IP aprobado,
   conserva el `Host` legítimo, revalida cada redirect, bloquea cambio de
   esquema y acota respuesta.

### P1 — seguridad y corrección alta

5. **HMAC Hermes reproducible y secreto débil.** La firma cubre timestamp,
   nonce y bytes exactos; el nonce se reclama en SQLite privado y persiste
   contra replay. Cliente y servidor exigen al menos 32 bytes. Se añadió health
   firmado con cuerpo exacto `{}`.
6. **Dashboard/OS bind no representaba su exposición.** Loopback conserva UX
   local; bind remoto requiere token fuerte. Las rutas Hermes con HMAC propio no
   quedan accidentalmente ocultas por el bearer del dashboard.
7. **Autorización Telegram por chat, no por actor.** Un grupo permitido podía
   implicar a todos sus miembros. Ahora se verifican `chat.id` y `from.id`; en
   grupos el usuario debe estar permitido explícitamente, incluidos callbacks.
8. **Aprobación HITL sin argumentos visibles o con secretos.** Los pendientes
   muestran preview acotado/redactado y SHA-256 de los argumentos exactos. La
   reanudación sigue usando el payload íntegro almacenado, no el preview.
9. **Merkle susceptible a symlink/permisos y tail O(n).** Directorio `0700`,
   logs `0600`, `O_NOFOLLOW`, fichero regular y append con lock. `tail(n)` lee
   bloques desde el final sin cargar la cadena completa.
10. **Espacios de embedding confundidos por dimensión.** Todos los embedders
    declaran identidad y fingerprint. FastEmbed liga versión y bytes de
    artefactos; stores SQLite/Kuzu rechazan una identidad distinta aunque la
    dimensión coincida. Índices legacy poblados sin prueba fallan cerrados;
    vacíos pueden adoptar la identidad actual.
11. **Migraciones/linaje de memoria silenciosos.** Supersede rechaza origen
    inexistente y colisiones; backfill temporal conserva filas; keystore y
    ficheros se endurecieron.
12. **Grafo estructural sin freshness fiable.** El servidor compara snapshot,
    HEAD y cambios bajo `src/atlas`; overview informa `FRESH/STALE/DIRTY/UNKNOWN`
    y las consultas de dependencia exigen `FRESH`.
13. **Graphify/GraphRAG/Neo4j operativamente frágiles.** Se corrigieron rutas,
    versión/CLI, semilla determinista, conteos reales, guard de pérdida,
    importación Neo4j parametrizada/atómica, bind loopback, credencial obligada,
    backup fail-closed y hooks respetando `core.hooksPath`.
14. **Supply chain/CI no reproducible.** Acciones GitHub están fijadas por SHA,
    lock verificado, install frozen, auditoría de dependencias, matrix Python,
    browser separado y smoke de wheel aislado. Garak y PyRIT se separaron por
    incompatibilidad real de `datasets`; Torch CPU se limita al extra Garak.
15. **Hermes desplegable como root/mutable y con secretos expuestos.** El nuevo
    provisionador fija Hermes `0.18.2` a tag+commit, usa lock upstream y `uv`
    fijado/verificado, usuario sin login, systemd endurecido, paths separados,
    config validada y skill root-owned. No hay Ollama/fallback/hooks implícitos.
16. **Canal Hermes ambiguo y duplicado.** `atlas-twin` es el cliente canónico:
    URL privada/Tailscale, sin proxies/redirects, endpoints fijos, cuerpo
    canónico y límites. `atlas-audit` delega; las rutas antiguas fallan cerradas
    o quedan marcadas como compatibilidad REST.
17. **Kanban con host público/hardcode y fuga a auditoría.** No hay host por
    defecto; SSH exige `user@host` privado/Tailscale, host key estricta y
    ejecución como usuario `hermes`. Se allowlistean acciones, se limita salida
    y el ledger guarda hash/count, no título/cuerpo.

### P2 — operabilidad, rendimiento y verdad documental

18. **Auditoría autónoma con efectos externos implícitos.** Ya no activa live
    por detectar variables ni llama el smoke REST/Telegram. Siempre prueba el
    twin aislado; pairing real es read-only y exige opt-in+host.
19. **`.env` evaluado como shell.** `safe_dotenv.py` exige dueño actual, regular
    no-symlink, modo privado, tamaño acotado, claves únicas y sintaxis literal;
    reejecuta el comando con el entorno sin `eval` ni expansión.
20. **Runner monolítico y unidades laxas.** Tests por lotes con timeout,
    workspace aislado, lock de instancia, artefactos privados y lifecycle
    systemd endurecido. La guarda de daemon avisa sin arrancar/reiniciar nada.
21. **Imports pesados en comandos baratos.** LiteLLM se importa de forma
    diferida; CLI, reality y embeddings baratos no cargan el SDK.
22. **Claims históricos tratados como estado.** ADR-026..029 y runbooks fueron
    corregidos; sellos Gate C/G llevan banner histórico; el mapa canónico marca
    Hermes `PENDIENTE`; reality separa configuración y vida; documentación de
    conteos deja de presentarse como cifra actual.
23. **Packaging dependiente del checkout.** Se añadieron datos necesarios al
    wheel y resolución de paths/version desde instalación, con smoke aislado.
24. **Publicación GraphRAG solapable y quality gate acumulativo.** Durante el
    cierre se observó una extracción semántica larga coincidiendo con el hook
    estructural: `graphify extract` no adquiría el lock de `graphify update`,
    por lo que el último escritor podía volver a publicar una capa AST vieja.
    La ruta semántica comparte ahora `.rebuild.lock`, hace que el hook encole
    cambios y ejecuta una reconciliación estructural antes de exportar. El
    quality gate toma solo el tramo desde el último marcador de corrida y
    cuenta líneas, evitando que el historial o la frase solapada “returned
    invalid JSON” dupliquen/contaminen el veredicto actual.
25. **`doctor` convertía ausencia de configuración en fallo SSH.** Sin
    `HERMES_KANBAN_TRANSPORT`, el diagnóstico instanciaba igualmente el bridge
    con el default SSH y mostraba “bridge init failed”; su lista de entorno
    también trataba simultáneamente variables de proveedores alternativos como
    si todas fueran obligatorias. Ahora el twin informa “no configurado” sin
    intentar transporte, distingue configuración inválida de inalcanzable y el
    entorno solo expone nombres presentes, nunca valores ni requisitos falsos.
26. **Timeout GraphRAG multiplicado silenciosamente.** La corrida de cierre
    mostró que `--api-timeout 900` se combinaba con los seis reintentos por
    defecto del SDK OpenAI-compatible: un solo fragmento podía consumir unos
    105 minutos. El pipeline propaga ahora `--max-retries`, usa uno por defecto
    y valida que sea un entero no negativo; cero permite un hard wall por
    intento cuando se prefiere perder un chunk antes que bloquear la operación.
    `--api-timeout` prevalece además sobre un valor heredado del entorno.
27. **Base fresca servida por un proceso MCP viejo.** Tras reconstruir Kuzu, un
    `graph_server` arrancado antes de la reparación seguía devolviendo `FRESH`
    y aceptaba importadores porque conservaba la implementación antigua en
    memoria. El servidor captura ahora `server_started_head_sha`, lo expone en
    overview y responde `SERVER_STALE` si la base y `HEAD` coinciden pero el
    proceso precede al checkout actual. Las consultas de presente fallan
    cerradas hasta reconectar; las históricas con SHA explícito siguen válidas.
28. **Client secret OAuth en argv de un proceso externo.** La inspección de
    procesos encontró una credencial de Google Workspace embebida en el JSON de
    línea de comandos de una sesión Claude ajena. El escaneo del `HEAD` no halló
    patrones equivalentes y no se copió el valor al informe. No se mató la
    sesión ni se fingió revocación: el secreto debe rotarse en Google y el
    conector debe relanzarse mediante un broker/fichero privado que no lo ponga
    en argv.
29. **Modelo NVIDIA enviado al endpoint OpenAI.** El preflight de cierre
    reveló que tener simultáneamente `OPENAI_API_KEY` y `NVIDIA_API_KEY` hacía
    que un modelo explícito `meta/*` conservara el endpoint público de OpenAI;
    todos los fragmentos devolvían 401 aunque la credencial NVIDIA fuera
    válida para su propio gateway. El enrutado usa ahora modelo más endpoint,
    no solo presencia de claves, y el plan verificable muestra el destino sin
    imprimir secretos.
30. **Quality gate aprobaba un grafo semántico parcial.** Aunque el informe
    contaba chunks fallidos y respuestas huecas, `--strict` solo evaluaba
    nodos e JSON inválido. Por tanto una caída 503 del proveedor podía terminar
    con exit 0 y publicar una cobertura incompleta. Los límites estrictos son
    ahora cero para ambos indicadores, configurables solo mediante umbrales
    explícitos, con regresiones aisladas para fallo y respuesta hueca.
31. **Unlock GraphRAG abría una carrera de inode.** La primera serialización
    eliminaba `.rebuild.lock` antes de liberar `flock`; otro proceso podía crear
    un inode nuevo mientras un waiter seguía bloqueado sobre el anterior. La
    ruta semántica conserva el pathname y decide propiedad por `flock`. El
    helper upstream todavía lo elimina al acabar su actualización corta; queda
    tratado como límite de tercero, no como garantía entre wrappers ajenos.
32. **Monitor y “autoremediador” actuaban fuera de alcance.** El monitor usaba
    `pgrep -f`/`kill` sobre todo el workstation, podía terminar Graphify de otro
    repo y elegía proveedor/modelo implícitamente; el autoremediador razonaba
    sobre reportes viejos y lanzaba trabajo LLM sin quality strict. No tenían
    callers vivos y fueron retirados fail-closed (exit 64); el reemplazo es una
    sola ejecución deliberada bajo lock.
33. **Un fallo del LLM podía borrar cobertura persistente.** Tras tres errores,
    el failure guard añadía el path atribuido por la salida del modelo a
    `.graphifyignore`. Ahora solo conserva contadores y emite candidaturas;
    aplicar exige `--apply-ignore`, ruta relativa inerte y decisión explícita.
34. **Logs semánticos legibles por otros usuarios y veredicto heredable.** Los
    errores del SDK pueden contener fragmentos enmascarados de credenciales o
    contenido, pero log/raw estaban `0664` bajo `0775`. Además, un aborto dejaba
    el informe verde anterior. La ruta crea logs/informe `0600` bajo `0700`,
    rechaza symlinks obvios y usa estados `running`, `pipeline_failed`,
    `quality_gate_failed` y `passed`.
35. **El tracker de tokens siempre sumaba cero y ocultaba alertas.** El formato
    terminaba en la palabra `tokens` y `awk` sumaba esa columna; `if ! ...`
    hacía además que el código capturado fuera siempre cero. El ledger valida
    proveedor/conteo, propaga warning/critical, usa ficheros privados y
    distingue presupuesto desconocido de 0 %. Graphify registra solo el uso
    real reportado por la respuesta; el ledger no se presenta como facturación.
36. **Guías vivas seguían ejecutando `.env` o exponiendo bearer en argv.** Aunque
    los scripts ya usaban el parser seguro, AGENTS y varios runbooks enseñaban
    `source .env`; otra receta pasaba Authorization a `curl` en la línea de
    comandos. Las rutas operativas usan ahora `safe_dotenv.py`, y la consulta
    HTTP construye el header dentro del proceso hijo.
37. **`--path` era una interfaz ficticia.** El quality wrapper aceptaba y
    reportaba otro target, pero siempre construía `.` y leía el `graphify-out`
    raíz. Hasta aislar outputs por target, cualquier valor distinto de `.`
    falla explícitamente.
38. **Etiquetado de comunidades consumía tokens sin contabilidad.** Tras la
    extracción medible, `cluster-only` volvía a invocar el LLM para nombres y
    Graphify 0.9.11 no exportaba ese uso. La topología no depende de los
    nombres: se usan etiquetas deterministas por hub con `--no-label`,
    reservando gasto LLM para input/output que sí queda registrado.
39. **Cache semántico sin identidad de productor.** Graphify conserva entradas
    por hash de fichero deliberadamente fuera del namespace de versión y sin
    prompt/backend/modelo. Cambiar NVIDIA por Gemini no reextrae hits, así que
    llamar “grafo Gemini” al resultado sería falso. El quality report expone
    hits/misses y marca `mixed_or_unverified`; GraphRAG se usa para descubrir
    hipótesis y Kuzu/AST/código para probar estructura.
40. **Capturador de fallos huérfano y expansivo.** Un `tail -F | awk` llevaba
    más de 18 horas huérfano de PID 1, copiando 80 líneas antes y después de
    cada error a un segundo fichero. Se terminaron únicamente sus dos PIDs, se
    eliminó el artefacto ignorado y el script quedó retirado con exit 64. El log
    canónico acotado y privado conserva la evidencia necesaria.
41. **Strict seguía gastando después de un veredicto imposible.** El wrapper
    esperaba toda la extracción aunque un contador ya superara su máximo. Un
    supervisor local inicia un grupo de proceso propio, cuenta solo su salida y
    lo termina al cruzar el umbral (exit 78), con escalado acotado a SIGKILL;
    nunca busca ni mata PIDs globales.
42. **Controles numéricos aceptaban valores inválidos hasta el backend.**
    Timeout, workers, concurrencia, budget y thresholds podían llegar como cero
    o texto y fallar tarde. Ambos wrappers validan positivos/no-negativos antes
    de abrir trabajo externo.
43. **Endpoint OpenAI-compatible y proveedor contable podían divergir.** El
    entorno conservaba el alias histórico `OPENAI_API_BASE`; el SDK actual solo
    lee `OPENAI_BASE_URL`, por lo que un modelo NVIDIA terminó contra OpenAI
    público con 401. Ambos wrappers normalizan el alias antes de enrutar y el
    ledger atribuye por endpoint real, incluidos NVIDIA, Groq y OpenRouter.
44. **Fail-fast confundía recuperación adaptativa con respuesta hueca final.**
    Graphify anuncia una respuesta hueca antes de bisecar el chunk; el supervisor
    estricto la trataba como fallo terminal y mataba precisamente la recuperación.
    Solo esa frase explícita de “adaptive retry can bisect” queda excluida; un
    hueco final genérico sigue fallando.
45. **Un parcial truncado podía quedar cacheado como éxito futuro.** Graphify
    guarda fragmentos por hash de contenido y escribía `partial result kept`;
    la corrida siguiente veía un hit limpio. El límite de parciales es cero por
    defecto, el informe los separa y el wrapper purga únicamente entradas que
    puede vincular a la fuente single-file exacta.
46. **Tres representaciones del mismo paper duplicaban semántica y una no era
    recuperable.** Markdown, HTML Pandoc y PDF ingresaban juntos. El PDF no se
    divide en Graphify 0.9.11 y devolvía un fragmento hueco aun con 65.536 tokens
    de salida. `.graphifyignore` excluye solo los derivados PDF/HTML; conserva el
    Markdown humano completo como autoridad semántica.
47. **Export Obsidian asumía un `NAME_MAX` inexistente y dejaba huérfanos.** El
    filesystem admite 143 bytes por componente mientras upstream limita stems a
    200; el export falló con `ENAMETOOLONG` y la escritura incremental conservaba
    notas ya eliminadas del grafo. Un adaptador calcula `PC_NAME_MAX`, construye
    un vault temporal completo, valida cobertura, preserva notas humanas y hace
    swap atómico con rollback.
48. **El quality report leía el dialecto JSON equivocado.** NetworkX serializa
    aristas como `links`, pero el wrapper priorizaba solo `edges`; comunidades
    también podían vivir solo como atributo de nodo. Los conteos reconstruyen
    ambos formatos y tienen una regresión con topología mínima real.
49. **Confidence inválida sobrevivía en cache semántico.** Cuatro entradas
    contenían el valor compuesto `EXTRACTED|INFERRED`, fuera del schema, y cada
    build emitía warning. Strict rechaza cualquier warning de validación y la
    limpieza elimina entradas con confidence fuera del enum permitido antes de
    reextraerlas.
50. **La ruta incremental amputaba el grafo completo.** Con manifest presente,
    `graphify extract` 0.9.11 escaneaba solo ficheros cambiados y publicaba ese
    delta como `graph.json`; se observó una caída de decenas de miles de nodos a
    unos cientos. Bajo el lock único, la ruta semántica retira el manifest a un
    backup seguro, fuerza detección completa reutilizando cache, exige un manifest
    nuevo y restaura el anterior ante fallo o señal. Ya no ejecuta después un
    `graphify update` que pudiera volver a publicar una capa amputada.
51. **La advertencia de IDs legacy era un falso positivo operativo.** La
    heurística upstream considera file-node todo nodo en `L1`; el comando de
    `.cursor/mcp.json` vive allí y su ID deliberadamente no deriva del nombre del
    fichero. El quality gate valida ahora solo anchors AST reales (label/metadata
    de fichero), acepta el salt ruta+extensión solo ante un stem realmente
    colisionado y rechaza IDs pre-#1504 verdaderos sin perder la configuración MCP.
52. **Una corrida fallida podía dejar el candidato como grafo canónico.** El
    quality report quedaba rojo, pero `graphify extract` ya había sustituido
    `graph.json`; además el lock de escritores no impedía editar fuentes durante
    una extracción larga. La ruta toma un snapshot privado del último manifest,
    grafo, análisis, labels, informe y Cypher, y otro snapshot SHA-256 del corpus
    detectado. Recalcula los hashes antes de exportar y restaura todo el conjunto
    ante fallo, señal o deriva. Una regresión muta una fuente tras el snapshot y
    demuestra
    que ni Neo4j export ni Obsidian se publican.
53. **`cluster-only` imprimía éxito sin publicar el clustered graph.** La
    deduplicación legítima redujo cuatro nodos; el shrink guard de `to_json`
    devolvió `False`, pero la CLI ignoró el retorno, dejó el raw de 44.494
    aristas y cero comunidades y aun anunció “graph.json updated”. Tras full
    scan, snapshot estable, IDs válidos y cobertura comunitaria exacta, el
    wrapper serializa ese mismo candidato con `force=True`. Strict rechaza
    además cualquier grafo no trivial con aristas y cero comunidades.
54. **`atlas reality --run-checks` se contradecía en el mismo documento.** La
    sección detallada `checks` contenía los resultados recién ejecutados, pero
    el resumen `tests.core/browser` seguía diciendo `unknown` y solicitaba
    ejecutar exactamente el comando ya terminado. La evidencia viva se proyecta
    ahora al resumen solo después de completar cada check; una regresión cubre
    simultáneamente éxito core, fallo browser y degradación global.
55. **Un chunk fallido podía reaparecer como cache hit verde.** Graphify hace
    checkpoints de cada chunk exitoso agrupando por `source_file`; si otra
    slice del mismo fichero falla, ya existe una entrada bajo el hash del
    fichero completo. La siguiente corrida veía un hit y ocultaba el fragmento
    ausente. La primera remediación purgó todas las claves nacidas durante una
    corrida fallida: evitó el falso verde, pero aplicó atomicidad a una frontera
    demasiado grande y provocó la pérdida de progreso descrita en el hallazgo
    60. Se conserva solo como antecedente del arreglo definitivo por fuente.
56. **El config local de Codex podía filtrarse con un staging amplio.** El TOML
    no rastreado contenía una credencial OAuth, rutas absolutas, MCPs del host y
    sandbox amplio; además estaba en modo 0664. Queda anclado en `.gitignore`,
    fuera del commit y restringido localmente a 0600. Los hooks portables viven
    en un JSON separado sin secretos. La credencial observada no se declara
    revocada: su rotación en Google sigue siendo una acción externa pendiente.
    Capturas internas locales `refs/codex/turn-diffs/*` aún alcanzan blobs de
    ambos artefactos para el undo de esta tarea; no pertenecen a `main` y
    `git push origin main` no las publica, pero un futuro push `--all/--mirror`
    sí sería improcedente hasta limpiar esas capturas y rotar la credencial.
57. **El hook Codex encontraba el wrapper pero perdía la raíz del proyecto.**
    La primera versión supuso una variable `CODEX_PROJECT_DIR` que el cliente no
    documenta; la [documentación oficial de hooks Codex](https://developers.openai.com/codex/hooks)
    establece que se ejecutan desde el CWD de sesión, que puede ser un
    subdirectorio. El JSON resuelve ahora cada script con
    `git rev-parse --show-toplevel` y el wrapper usa la misma raíz como fallback.
    Una regresión ejecuta el comando real desde `ui/atlas-shell` y falló antes
    de la corrección. La configuración no se presenta como ejecución viva:
    Codex solo carga hooks de proyecto tras confiar explícitamente esa capa.
58. **La UI versionada estaba fuera de CI y su decisión había derivado.** El
    lock pendiente subía Vite 5→7, pero ADR-059, la pregunta abierta y OS-R4
    seguían fijando Node 18/Vite 5; el lock anterior tenía 13 avisos aplicables.
    Node 22.22.2, engines/package manager, ADR y riesgo quedan reconciliados;
    CI instala el lock exacto, rechaza advisories altos/críticos y construye la
    shell. El lock actual da cero vulnerabilidades y el build transforma 77
    módulos.
59. **Una fuente privada no rastreada contaminaba GraphRAG.** El export bruto
    "Diseño UI Atlas.md" (1,7 MB, 65.640 líneas) ya estaba destilado, pero
    Graphify lo había ingerido como comunidad propia de 54 nodos y lo mezclaba
    con consultas generales; contiene URLs firmadas y contexto local. Queda
    ignorado tanto por Git como por Graphify y restringido localmente a 0600.
    Solo su destilación operativa es autoridad publicable.
60. **El rollback seguro convertía 15/16 éxitos en cero y repetía consumo.**
    Graphify escribe cada chunk antes del callback, agrupa por `source_file` con
    `merge_existing=True` y puede crear o mutar hashes ajenos al chunk. El
    wrapper inferior y el quality wrapper guardaban solo nombres y purgaban
    indiscriminadamente todo hash nuevo ante el fallo final; además, el retry
    adaptativo omitía del agregado los tokens del intento padre truncado. Atlas
    separa ahora trabajo verificable de publicación: bajo el mismo lock extrae
    una fuente por vez con cache incremental y retry adaptativo desactivados,
    registra tokens en el callback, filtra cualquier salida cruzada o dangling,
    exige schema válido y hash de contenido estable, y hace un único write
    atómico. Un 504 deja pendientes solo sus fuentes; auth, billing, cuota, 429
    o modelo rechazado detienen el lote. El full scan, manifest, grafo, Cypher y
    vault mantienen rollback conjunto. Seis unit tests y dos regresiones de
    wrapper demuestran que reiniciar repite únicamente misses seguros.

## Verificación ejecutada

| Comprobación | Resultado del 2026-07-16 |
| --- | --- |
| Suite core completa | exit 0 |
| Suite `computer_use` explícita | exit 0; Crawl4AI real omitido por entorno separado ausente |
| mypy sobre `src/atlas` | exit 0, sin issues |
| `atlas security-audit src/atlas --json` | exit 0, lista vacía |
| `atlas audit --verify` | cadena íntegra |
| `atlas doctor` | OK local; integraciones externas explícitamente no configuradas |
| Coherencia del resumen `atlas reality --run-checks` | core/browser reflejan la evidencia de `checks`; regresión dirigida exit 0 |
| Resume + transacción semántica tras fallo/deriva | fuentes completas preservadas; fuente fallida no cacheada; publicación revertida; regresiones exit 0 |
| Tests dirigidos Hermes/deploy/HMAC/kanban/reality | exit 0 |
| Tests dirigidos dotenv/auditoría/grafos/Neo4j | exit 0 |
| Regresiones lock/reconciliación/calidad GraphRAG | exit 0 |
| GraphRAG full-scan estricto | La corrida histórica anterior pasó; la verificación posterior al arreglo quedó limitada a 702/714 hits porque NVIDIA y Ollama no respondieron de forma utilizable a las fuentes largas. No se declara full scan nuevo ni cobertura semántica completa |
| Export Obsidian transaccional | una nota por nodo canónico o más, canvas presente, nombres dentro del límite real y cero backups residuales |
| Ledger local de tokens | uso reportado atribuido; se declara expresamente distinto de billing/cuota viva |
| Validación de config Hermes contra código upstream fijado | exit 0 para Groq y OpenRouter |
| `git diff --check` | exit 0 |
| Hooks portables y exclusión de artefactos privados | 11 pruebas dirigidas; JSON válido; config local ignorado y 0600 |
| Atlas shell | `npm ci --engine-strict`, árbol directo válido, 0 advisories y build Vite 7 de 77 módulos |
| Índice documental | `docs_index_audit.py --strict`, cero faltantes, huérfanos o vigentes caducados |

La suite emitió un warning upstream: FastEmbed cambió el pooling de un modelo.
El nuevo guard de identidad incluye versión y artefactos, por lo que una base
persistente incompatible se rechaza/migra explícitamente en vez de mezclarse.

## Post-mortem

### Causas raíz

1. **Confundir intención con evidencia.** ADRs, variables y scripts se habían
   convertido en claims de vida sin smoke actual.
2. **Control en la capa equivocada.** Allowlist/AST/HMAC sin nonce eran útiles,
   pero no sustituían kernel, identidad server-side o replay persistence.
3. **Defaults convenientes en fronteras sensibles.** Host público/hardcode,
   root, `.env` ejecutable y smokes automáticos ahorraban pasos a costa de
   seguridad y trazabilidad.
4. **Compatibilidad sin nombre explícito.** Stub REST y Hermes oficial
   compartían vocabulario y evidencia.
5. **Identidad parcial.** Dimensión de vector, chat o campo `approved_by`
   parecían identidad pero no demostraban productor/actor.
6. **Observabilidad que filtraba o escalaba mal.** Argumentos completos y
   lecturas O(n) convertían auditoría en riesgo de secreto/rendimiento.
7. **Grafo tratado como presente sin atarlo a commit/dirty state.** Una respuesta
   estructural vieja podía ser más peligrosa que no responder.
8. **Incrementalidad asumida sin probar la semántica de publicación.** Se daba
   por hecho que “incremental” fusionaba con el grafo previo; la CLI reemplazaba
   con el delta y el cache convertía parciales viejos en futuros hits.
9. **Límites de filesystem tratados como constantes de plataforma.** Un cap de
   200 parecía conservador frente a 255, pero no frente al filesystem real de
   143 ni frente a una sustitución incremental con derivados huérfanos.
10. **Granularidad de cache distinta de la granularidad de fallo.** El cache
    se identifica por fichero, pero extracción, reintento y fallo ocurren por
    slices/chunks; sin transacción, “algún resultado del fichero” se confundía
    con “fichero completo”.
11. **Atomicidad aplicada a estado de trabajo verificable.** Revertir una
    publicación incompleta era correcto; borrar junto con ella unidades ya
    completas e independientes no lo era. La frontera de checkpoint debe ser
    menor que la frontera de publicación.

### Lo que funcionó

- Las regresiones y fixtures aislados permitieron reproducir traversal, replay,
  SSRF, auth y mounts sin efectos externos.
- El enfoque fail-closed hizo visibles dependencias ausentes y grafos viejos.
- La investigación contra fuente primaria evitó inventar schema/flags Hermes.
- Separar contrato, configuración y vida eliminó varias contradicciones.
- La revisión independiente del diff de cierre detectó que una variable Codex
  asumida no era parte del contrato oficial; la regresión se reescribió para
  ejecutar el comando real desde un subdirectorio antes de aceptar el arreglo.

### Lo que no funcionó o no estuvo disponible

- Los subagentes de la primera pasada agotaron su cuota; en el cierre posterior
  sí hubo revisiones independientes de dependencias, fuentes privadas, secretos
  y diff final. No se confunden esos informes con ejecución de servicios vivos.
- Neo4j no estaba escuchando y no había `NEO4J_PASSWORD`; solo se validaron
  export e importador en aislamiento.
- El grafo MCP vivo estaba viejo durante la edición y, correctamente, no dio
  blast radius/importers.
- No había secretos de proveedor/Hermes/Telegram en el entorno inspeccionado;
  no se ejecutaron efectos externos para fabricar una evidencia.
- Gemini devolvió 503 y después 429; Groq aceptó probes estructurados pero su
  límite TPM rechazó la corrida completa; OpenRouter respondió al probe pero no
  tenía crédito utilizable. NVIDIA GPT-OSS completó el full scan. Ningún probe
  se presenta como SLA ni como cuota/billing verificados.

## Riesgo residual y siguiente prueba necesaria

| Riesgo residual | Estado | Condición para cerrarlo |
| --- | --- | --- |
| Hermes/VPS/provider/Telegram no verificados | Abierto, operativo | Despliegue deliberado; pairing firmado; inferencia real; entrega Telegram real, cada una registrada por separado |
| Seccomp no es allowlist portable | Abierto, arquitectónico | ADR/dependencia explícita, perfil por arquitectura y tests de syscall; mantener bwrap fail-closed |
| HMAC simétrico sin rate limit interno | Aceptado temporalmente | Rotación coordinada + rate limiting si la frontera aumenta exposición |
| Neo4j/GraphRAG vivo | No configurado | Credencial privada, servicio loopback, import atómico y consulta real |
| Crawl4AI worker real | Omitido | Crear/validar `.venv-scraping` aislado conforme a su contrato y repetir marcador |
| REST Hermes legado | Compatibilidad | Demostrar cero callers externos y retirarlo con migración/ADR |
| Inferred edges de Graphify | Riesgo epistemológico | Usarlos como hipótesis; confirmar decisiones estructurales con grafo AST/Kuzu fresco o código/tests |
| Client secret OAuth observado en argv externo | Abierto, credencial | Rotar en Google; retirar la versión expuesta; relanzar el conector sin secreto en argv |
| Trust/capturas locales de hooks Codex | Abierto, cliente local | Revisar/confiar los hooks tras el commit; no publicar refs `refs/codex/*`; limpiar capturas solo cuando ya no se necesite undo y después de rotar OAuth |
| Cache semántico sin identidad prompt/modelo | Compensado, no cerrado upstream | Mantener `mixed_or_unverified`; vaciar/reextraer con una única identidad cuando se necesite provenance uniforme |
| Heurística legacy-ID upstream sobre nodos MCP `L1` | Falso positivo conocido | Usar `legacy_file_id_count` del quality gate; no ocultar una advertencia real sin esa prueba |
| Proveedor GraphRAG externo | Variable/no SLA | Preflight pequeño, límites de timeout/retry/concurrency y full scan strict; no inferir disponibilidad futura de un éxito puntual |

## Regla de cierre

El trabajo se considera cerrado cuando el commit de auditoría, el ledger, este
documento y `MEMORY.md` coinciden; suite/mypy/docs pasan; Graphify y el grafo
estructural se regeneran sobre ese commit; y toda capa externa no probada queda
marcada como tal. Ninguna ausencia de credencial se rellena con una suposición.
