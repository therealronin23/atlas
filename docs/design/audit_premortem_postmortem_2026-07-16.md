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

## Verificación ejecutada

| Comprobación | Resultado del 2026-07-16 |
| --- | --- |
| Suite core completa | exit 0 |
| Suite `computer_use` explícita | exit 0; Crawl4AI real omitido por entorno separado ausente |
| mypy sobre `src/atlas` | exit 0, sin issues |
| `atlas security-audit src/atlas --json` | exit 0, lista vacía |
| `atlas audit --verify` | cadena íntegra |
| Tests dirigidos Hermes/deploy/HMAC/kanban/reality | exit 0 |
| Tests dirigidos dotenv/auditoría/grafos/Neo4j | exit 0 |
| Validación de config Hermes contra código upstream fijado | exit 0 para Groq y OpenRouter |
| `git diff --check` | exit 0 |

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

### Lo que funcionó

- Las regresiones y fixtures aislados permitieron reproducir traversal, replay,
  SSRF, auth y mounts sin efectos externos.
- El enfoque fail-closed hizo visibles dependencias ausentes y grafos viejos.
- La investigación contra fuente primaria evitó inventar schema/flags Hermes.
- Separar contrato, configuración y vida eliminó varias contradicciones.

### Lo que no funcionó o no estuvo disponible

- Los subagentes delegados agotaron su cuota y no aportaron revisión
  independiente; el agente principal repitió verificación local.
- Neo4j no estaba escuchando y no había `NEO4J_PASSWORD`; solo se validaron
  export e importador en aislamiento.
- El grafo MCP vivo estaba viejo durante la edición y, correctamente, no dio
  blast radius/importers.
- No había secretos de proveedor/Hermes/Telegram en el entorno inspeccionado;
  no se ejecutaron efectos externos para fabricar una evidencia.

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

## Regla de cierre

El trabajo se considera cerrado cuando el commit de auditoría, el ledger, este
documento y `MEMORY.md` coinciden; suite/mypy/docs pasan; Graphify y el grafo
estructural se regeneran sobre ese commit; y toda capa externa no probada queda
marcada como tal. Ninguna ausencia de credencial se rellena con una suposición.
