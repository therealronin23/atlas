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

Verificado el 2026-07-29 con `git rev-parse` contra cada checkout.

## TERMINADO

Trabajo real hecho y commiteado en su propio repo. No está integrado en
`atlas-core` ni pretende estarlo todavía.

| Fork | Ruta | Upstream | Rama | HEAD | Qué hay |
|---|---|---|---|---|---|
| Atlas IDE — Void baseline | `~/proyectos/atlas-ide` | `voideditor/void` | `feat/atlas-bridge-baseline` | `d8e96ed` | provider roles + baseline del bridge |
| Atlas IDE — Void forward port | `~/proyectos/atlas-ide-forward-port` | `voideditor/void` | `feat/atlas-desktop-forward-port` | `34803da` | bridge 7342, supervisión de lifecycle, tests de escritorio (443 inserciones / 8 ficheros) |

Ambos checkouts estaban **limpios** (cero ficheros sin commitear) el 2026-07-29.

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

## DISECCIONES (histórico, julio 2026)

`~/proyectos/atlas-forks/` — 727 MB, sin menciones en el ecosystem map:
`aider`, `bumblebee`, `cline`, `hermes-agent`, `openhands`,
`openhands-docs-audit`, `software-agent-sdk-audit`, `vercel-mcp-adapter`.

Son el material de `docs/design/absorption_master_plan.md` (762 líneas). De ahí
salieron piezas ya en `atlas-core` — `git_checkpoint.py` (de
`cline/sdk/.../checkpoint-restore.ts`), `repo_map.py` (Aider, citado en su
propio docstring). No son forks vivos: son fuentes de disección.

También existe `~/proyectos/atlas-ui-prototypes` (824 MB, **no es repo git**).

## La puerta

Todo lo de arriba tiene `target_cut: CUT-2` en el registro de linaje, y
**Cut 2 no está abierto**. `ADC-WO-109` (portar Void sobre CodeOSS/VSCodium) y
`ADC-WO-110` (ACP/patrones de Zed) no se abren hasta satisfacer sus gates; la
puerta es terminar Cut 1 (`ADC-WO-108`), hoy parcialmente construido. No
empieces a portar nada desde aquí sin esa decisión.

## Por qué los repos no están dentro de atlas-core

Propuesto por el operador el 2026-07-29 y **no aplicado**, pendiente de su
decisión con estos datos encima de la mesa:

- **Tamaño**: `atlas-ide` 764 MB · `atlas-forks` 727 MB · `atlas-codeoss`
  459 MB · `atlas-ide-forward-port` 224 MB · `atlas-ui-prototypes` 824 MB ·
  `atlas-editor-zed` sin terminar de medir (excedió 2 min de `du`). Más de
  3 GB.
- **Historias git independientes**: son repos completos con su upstream. Meterlos
  dentro exige submódulos o subtree; ambos son decisión de arquitectura, no un
  `mv`.
- **Licencias**: el boundary Apache/GPL de Zed está declarado en el canon.
  Vendorizar cambia la exposición.

La alternativa que este fichero implementa: los repos se quedan fuera y aquí
vive el índice versionado, que es lo que faltaba de verdad. Si aun así se
decide moverlos, hacerlo por ADR explícito (invariante 6) y con estrategia de
actualización upstream declarada.
