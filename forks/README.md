# Forks y checkouts externos — inventario

**Para quien llegue en sesión limpia:** hay checkouts de terceros FUERA de este
repo, en `~/proyectos/`, que son materia prima de `ADC-WO-109/110` (Cut 2). No
aparecen en `git status` y ninguno de los cuatro docs de arranque
(`AGENTS.md`, `WORK_LEDGER.md`, `STATUS.md`, `PLAN.md`) citaba sus rutas hasta
2026-07-29. Si te preguntan "¿hemos forkeado algo?", la respuesta mirando sólo
`atlas-core` es *no* — y es engañosa.

Autoridad de los datos: `docs/canon/product_lineage_registry.jsonl` (SHA,
capabilities, disposition, evidence) y `docs/design/atlas_ecosystem_map.md`
(clasificación). Este fichero es el ÍNDICE, no una fuente nueva: si discrepan,
mandan el registro de linaje y el mapa.

Verificado el 2026-07-29 y **re-verificado el 2026-08-10** con `git rev-parse`
contra cada checkout: los seis intactos, limpios y en el mismo SHA. Cero deriva
en 12 días.

## TERMINADO

Trabajo real hecho y commiteado en su propio repo. No está integrado en
`atlas-core` ni pretende estarlo todavía.

| Fork | Ruta | Upstream | Rama | HEAD | Qué hay |
|---|---|---|---|---|---|
| Atlas IDE — Void baseline | `~/proyectos/atlas-ide` | `voideditor/void` | `feat/atlas-bridge-baseline` | `d8e96ed` | provider roles + baseline del bridge |
| Atlas IDE — Void forward port | `~/proyectos/atlas-ide-forward-port` | `voideditor/void` | `feat/atlas-desktop-forward-port` | `34803da` | bridge 7342, supervisión de lifecycle, tests de escritorio (443 inserciones / 8 ficheros) |

Ambos checkouts estaban **limpios** (cero ficheros sin commitear) el 2026-07-29
y seguían igual el 2026-08-10.

`atlas-ide-forward-port` **no es un clon independiente**: es un *worktree
enlazado* de `atlas-ide` (su `.git` es un fichero de 78 bytes, no un
directorio). Comparten object store — borrar `atlas-ide` se llevaría por
delante la historia de las 443 líneas del forward-port.

**Void pasó de `PORT_SOURCE` a `PATTERN_DONOR` el 2026-08-11** (decisión del
operador). Se conserva íntegro como mentor de UI/UX y de backend; lo que se
abandona es rebasarlo. Motivo medido en
`docs/design/cut2_scope_recommendation_2026-08-10.md`: 354 de nuestras 443
líneas viven en ficheros propios y el núcleo del puente
(`atlasBackendMainService.ts`) importa **cero símbolos de Void** — sólo stdlib
de Node y `platform/instantiation`, que existe en CodeOSS. Las 81 líneas
acopladas registran Atlas en la UI de chat de Void, ya sustituida por la
Mission Console (ADR-085, Flutter). El host real pasa a ser CodeOSS.

## PENDIENTE

Clonados y sin una sola línea nuestra: están en el commit de upstream. Son
baseline y referencia, no trabajo a medias.

| Checkout | Ruta | Upstream | Rama | HEAD | Disposition |
|---|---|---|---|---|---|
| Code OSS 1.129.1 | `~/proyectos/atlas-codeoss-1.129.1` | `microsoft/vscode` | `spike/atlas-codeoss-1.129.1` | `8a7abeba` | `HOST_BASELINE` |
| Zed | `~/proyectos/atlas-editor-zed` | `zed-industries/zed` | `main` | `c9e8e61` | `PATTERN_DONOR` |

**Zed no se forkea.** El canon lo clasifica `UPSTREAM_REFERENCE` /
`PATTERN_DONOR`: donante de ACP y de patrones de interacción, con boundary de
licencia Apache/GPL explícito. Asimilar por contrato o componente aislado
(`ADC-WO-110`), nunca trasplante completo. Code OSS es el host baseline sobre
el que se portaría Void (`ADC-WO-109`), no un fork a mantener.

## DISECCIONES

`~/proyectos/atlas-forks/` — material de lectura, no forks vivos. Se minan y se
olvidan: no contraen deuda de rebase.

| Disección | Tamaño | Licencia | Añadido |
|---|---|---|---|
| `aider` | 147 MB | — | jul 2026 |
| `hermes-agent` | 278 MB | — | jul 2026 |
| `cline` | 101 MB | — | jul 2026 |
| `openhands` + `openhands-docs-audit` | 167 MB | — | jul 2026 |
| `software-agent-sdk-audit` | 33 MB | — | jul 2026 |
| `bumblebee` | 3,0 MB | — | jul 2026 |
| `vercel-mcp-adapter` | 1,1 MB | — | jul 2026 |
| **`codex`** (`openai/codex`) | **139 MB** | **Apache-2.0** | **2026-08-11** |
| **`claude-agent-sdk`** (`anthropics/claude-agent-sdk-python`) | **3,9 MB** | **MIT** | **2026-08-11** |

Los dos nuevos van con `--depth 1` (misma disciplina que los checkouts
`shallow` de CodeOSS y Zed): se disecciona el código actual, no la historia.

**Codex no es binario.** Era el handicap que frenaba su fork: `openai/codex` es
repo público de Rust, verificado en vivo con `git ls-remote` el 2026-08-11. Lo
binario es el empaquetado de npm, no la fuente. Ya se auditó a nivel de código
el 2026-07-02 — de ahí salió la técnica #20 (descubrimiento jerárquico de
`AGENTS.md`) que hoy corre en `AtlasCoder` y `ToolCoder` — pero **no se guardó
el fork**; esto lo cierra.

**Cursor sí es imposible.** Fuente cerrada, sin repo del editor. Se extrae por
observación y ya se hizo: su modo *ensemble* es hoy `ParallelCoder.run_ensemble`
y su sistema de reglas por glob es `conditional_rules.py`.

Son el material de `docs/design/absorption_master_plan.md`. De ahí salieron
piezas ya en `atlas-core` — `git_checkpoint.py` (de
`cline/sdk/.../checkpoint-restore.ts`), `repo_map.py` (Aider, citado en su
propio docstring).

También existe `~/proyectos/atlas-ui-prototypes` (824 MB, **no es repo git**).

## La puerta (actualizado 2026-08-11)

`ADC-WO-108` (Cut 1) está **DONE**, así que la puerta que este fichero
describía ya no es la que bloquea. Estado real de las dos fichas:

- **`ADC-WO-110`** (ACP/patrones de Zed) → **READY**. Nunca dependió de la
  decisión de Cut 2; sus dos dependencias reales están cerradas. Licencias
  medidas el 2026-08-10: Zed `crates/acp_*` es GPL-3.0-or-later, el SDK que
  Atlas usa (`agent-client-protocol` 0.11.0) es Apache-2.0, y hay cero fuente
  de Zed en `src/`. Se adoptó el **protocolo**, no el código. La conformidad
  ACP por stdio real se ejecutó por primera vez ese día
  (`tests/test_acp_stdio_conformance.py`); la suite previa lo construía en
  proceso y su docstring excluía el transporte.
- **`ADC-WO-109`** (host del Workbench) → alcance decidido el 2026-08-11:
  CodeOSS es el host, Void deja de rebasarse. Sigue sin compilarse — la
  recomendación se apoya en imports y procedencia de ficheros, no en un build
  verde.

## Por qué los repos no están dentro de atlas-core

Propuesto por el operador el 2026-07-29 y **no aplicado**, pendiente de su
decisión con estos datos encima de la mesa:

- **Tamaño** (medido entero el 2026-08-10; las cifras de julio se quedaban
  cortas): `atlas-editor-zed` **13 GB** · `atlas-ide` **4,3 GB** ·
  `atlas-ui-prototypes` 824 MB · `atlas-forks` 870 MB · `atlas-codeoss`
  459 MB · `atlas-ide-forward-port` 224 MB. Cerca de **20 GB**.

  Pero el disco **no es el argumento**: ~14 GB de eso son caché de compilación
  regenerable (Zed 12 GB en `target/`, `atlas-ide` 1,8 GB de `node_modules` +
  204 MB de `out`); los `.git` son 25 MB y 33 MB. El peso real de fuente es
  ~4 GB, y hay 601 GB libres al 31%. Lo que pesa de un fork vivo es el
  mantenimiento, no los bytes.
- **Historias git independientes**: son repos completos con su upstream. Meterlos
  dentro exige submódulos o subtree; ambos son decisión de arquitectura, no un
  `mv`.
- **Licencias**: el boundary Apache/GPL de Zed está declarado en el canon.
  Vendorizar cambia la exposición.

La alternativa que este fichero implementa: los repos se quedan fuera y aquí
vive el índice versionado, que es lo que faltaba de verdad. Si aun así se
decide moverlos, hacerlo por ADR explícito (invariante 6) y con estrategia de
actualización upstream declarada.
