# Atlas

Runtime de inteligencia local, con la afirmación como unidad auditable.

Atlas coordina modelos locales y de proveedor, herramientas, servidores MCP,
memoria, aprobaciones y auto-mejora en frío. Lo que lo distingue no es lo que
puede hacer, sino que **no se le permite afirmar que hace algo sin evidencia
fresca que lo demuestre** — ni a un modelo, ni a su propia documentación.

Local-first, sin dependencia de SaaS. No es un chatbot con herramientas, ni un
wrapper de APIs, ni un clon de otro agente.

## Por qué existe

El problema no es que un agente escriba código malo: es que **el registro de lo
que hizo se desincroniza de lo que realmente pasó**, y nadie lo nota. Los docs
prometen capacidades que el código no tiene. Un test verde tapa una regresión
que nadie mapeó. Un catálogo dice `verificado` sobre un binario que el gate de
seguridad ya bloquea.

Atlas trata esa deriva como un defecto de primera clase, con detectores
deterministas: sin LLM y sin red, así que son baratos y repetibles.

| Detector | Qué contrasta | Dónde corre |
|---|---|---|
| `component_wiring_drift` | Las filas del canon contra el **grafo AST real**, en las dos direcciones: sobre-afirmación *y* sub-afirmación | **PreflightGate** + radar |
| `ecosystem_drift` | Que toda decisión de arquitectura real tenga fila en el mapa del ecosistema | **PreflightGate** + radar |
| `docs_index_drift` / `docs_graph_drift` | Docs sin entrada en el índice, enlaces rotos y huérfanos | **PreflightGate** + radar |
| `check_canon` | Integridad referencial de ~2100 registros machine-readable | **CI** |
| `impacted_tests` | Qué tests puede romper un cambio, **por referencia real**, no por convención de nombres | **pre-commit** |

`PreflightGate` es la puerta que corre **antes de cada ciclo de
auto-construcción**: el lazo no se propone cambios mientras el canon miente
sobre qué está cableado. Es deliberadamente el sitio más caro de mentir.

Ninguno de los detectores de deriva bloquea el commit humano hoy —sólo
`impacted_tests` y `check_canon` lo hacen— y eso es deuda declarada, no un
descuido oculto.

La detección de **sub**-afirmación es deliberada: no basta con cazar docs que
prometen demasiado. Un componente construido, cableado y con tests pasando que
el canon marca como ausente es igual de falso. El día que se cableó, el
detector encontró 8 filas así — dos de ellas con código importado y tests
verdes mientras el canon no admitía ni que el código existiera.

La misma regla se aplica a las evaluaciones del propio sistema: el gate de
sucesión F2.6 tiene un fallo registrado (2/6) en vez de un prompt ajustado
para sacar mejor nota. Un receipt de una prueba que se retocó hasta pasar no
mide nada.

## Vocabulario de estado

Ningún documento de este repo dice "hecho". Cada capacidad lleva un estado
explícito, y **no son sinónimos**:

```
MISSING → RESEARCH → PROPOSED_DESIGN → ACCEPTED_DESIGN → CODE_PRESENT
        → TESTED → WIRED → RUNTIME_CONFIGURED → LIVE_VERIFIED → PRODUCT_ACCEPTED
```

Más `CONTRADICTED` (fuentes válidas discrepan), `PARKED` y `SUPERSEDED`.

`RUNTIME_CONFIGURED` no es `LIVE_VERIFIED`: que dos servidores MCP estén
configurados no prueba que respondan. `LIVE_VERIFIED` exige una observación
fresca y fechada — **citar un documento anterior no cuenta como evidencia**.

El vocabulario completo está en [`STATUS.md`](STATUS.md).

## Verifícalo tú, no me creas

Este README no lleva cifras de tests ni de cobertura, a propósito: se
desincronizarían en días y sería exactamente el defecto que el proyecto
persigue. Los números salen del sistema:

```bash
git clone https://github.com/therealronin23/atlas.git && cd atlas
python -m venv .venv && .venv/bin/pip install -e '.[dev,mcp]'

.venv/bin/atlas reality --json          # estado verificable, barato
.venv/bin/atlas reality --run-checks    # ejecuta suite + mypy + navegador
.venv/bin/atlas audit --verify          # integridad de la cadena Merkle

PYTHONPATH=src .venv/bin/python scripts/check_canon.py       # integridad del canon
PYTHONPATH=src .venv/bin/python scripts/sanitation_audit.py  # radar de deriva
```

`atlas reality` reporta `unknown` o `degraded` en lugar de adivinar. Si dice
que el grafo está `STALE` o que Hermes está en `mock`, es que lo está.

Requiere Python ≥3.11. `bubblewrap` es opcional; sin él, la ejecución de
código generado queda fail-closed en vez de correr sin aislamiento.

## Estado honesto

**Funciona hoy**: el runtime local, la cadena Merkle auditada, el grafo
estructural del proyecto (Kuzu), memoria y lecciones entre sesiones, el ciclo
de auto-mantenimiento (descubre, analiza, propone, y un decisor veta), y
ColdUpdate — que aplica cambios al propio Atlas sólo tras validarlos en un
worktree aislado, revirtiéndolos si los checks post-apply fallan.

**No funciona todavía, y el repo lo dice**:

- **Sin UI de producto.** `ui/atlas-shell` es un arnés de validación por
  declaración explícita (ADR-071), no la interfaz final. Se opera por CLI.
- **Hermes en `mock`**, sin delegación real a otro nodo.
- **MCP `RUNTIME_CONFIGURED`, sin handshake vivo verificado.**
- **Bridge 7341 `CONTRADICTED`**: su código expone POST mutantes que
  contradicen el contrato read-only de su propio ADR. Sin resolver, y
  registrado como tal en vez de silenciado.
- **Control de escritorio en cuarentena** (`blocked-admission`): el binario de
  terceros no tiene artefacto, hash ni receipt, así que el gate lo bloquea
  antes de arrancarlo — aunque una prueba histórica lo diera por bueno.

La autonomía está capada a propósito: el decisor por defecto es humano y
ColdUpdate no auto-aplica.

## Navegación

| Documento | Para qué |
|---|---|
| [`ATLAS.md`](ATLAS.md) | Entrada canónica: qué es, invariantes, arquitectura |
| [`STATUS.md`](STATUS.md) | Realidad verificable y vocabulario de estados |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | `CURRENT` / `TARGET` / `TRANSITION` separados |
| [`PLAN.md`](PLAN.md) | Lista ejecutable y defaults fail-closed |
| [`WORK_LEDGER.md`](WORK_LEDGER.md) | Estado vivo: dónde está el trabajo y la siguiente acción |
| [`AGENTS.md`](AGENTS.md) | Protocolo para agentes que operen el repo |
| [`docs/canon/`](docs/canon/) | Registros machine-readable: componentes, decisiones, conflictos, preguntas abiertas |
| [`forks/README.md`](forks/README.md) | Checkouts de terceros fuera del repo, terminado vs pendiente |

## Estado del proyecto

Proyecto personal en desarrollo activo, de un solo operador. El canon actual
es una **candidata pendiente de aceptación explícita del operador**; no está
declarado estable ni listo para producción de terceros.

El repo **no lleva fichero de licencia** todavía, así que por defecto no se
concede permiso de uso, copia ni distribución.
