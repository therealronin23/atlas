# EDR-ADC-WO-124 — Admisión de computer-control-mcp

**Decision:** ADC-WO-124
**Program:** P08 (desktop operator)
**Evidence state:** `PROVISIONAL`
**Decision disposition authority:** `docs/canon/decision_registry.jsonl`

## Hallazgo previo a la decisión (2026-07-31)

**`computer-control-mcp==0.3.10` saltó por completo el pipeline de vetting de
ADR-075.** Instalado el 2026-07-23 (mtime del `dist-info`) vía `pip install`
directo en `.venv-desktop/`, lo que significa que **ya ejecutó código de
build/setup en esta máquina** — exactamente el paso que ADR-075 existe para
evitar antes del análisis. Verificado por ausencia:

```
grep -c "computer-control-mcp" docs/design/mcp_catalog_stage1_triage.jsonl  → 0
grep -c "computer-control-mcp" docs/design/mcp_catalog_stage2_report.jsonl  → 0
ls workspace/mcp/quarantine/ | grep computer                               → (nada, de 207 paquetes)
```

La decisión ADC-WO-124 se está deliberando **después** del acto que pretendía
gobernar. No se ha tocado la instalación ni el catálogo — sigue siendo
decisión del operador — pero el hecho debe quedar registrado con evidencia
antes de decidir nada.

## Question

¿Se admite `computer-control-mcp==0.3.10` a ejecución de terceros gobernada, o
se mantiene en cuarentena?

## Constraints

- Ejecución de terceros falla cerrado sin artefacto inmutable, hash
  verificado, recibo de procedencia y perfil de aislamiento (ADR-075).
- `SentinelGate.vet_command` solo tiene un camino positivo real hoy
  (`_is_governed_native_command`); cualquier ejecutable de terceros cae en
  `sentinel.server_vetoed` — bloqueado, sin excepción para recibos.

## Evidencia observada — los 6 ítems automatizables del scope

Producidos hoy, sobre el paquete YA instalado (sin reinstalar nada):

| Ítem del scope | Valor medido |
|---|---|
| SHA-256 del árbol (mismo algoritmo que `plugin_materializer.compute_tree_sha256`, re-verificación independiente) | `1705d29a041cbb761049165441d5a4b59430d2dfb9a18f5d0ac938ec6424a56a` |
| Licencia | `MIT` (declarada en `METADATA`, `License-File: LICENSE` presente) |
| Autor / procedencia declarada | `AB498 <abcd49800@gmail.com>`, homepage `github.com/AB498/computer-control-mcp` — autor único, sin organización |
| Inventario de dependencias directas | `fuzzywuzzy==0.18.0`, `mcp[cli]==1.13.0`, `mss>=7.0.0`, `onnxruntime==1.22.0`, `opencv-python==4.12.0.88`, `pillow==11.3.0`, `pyautogui==0.9.54`, `pygetwindow==0.0.9`, `python-levenshtein>=0.20.9`, `pywinctl==0.4.1`, `rapidocr-onnxruntime==1.2.3`, `rapidocr==3.3.1`, `windows-capture>=1.0.0` (solo win32) |
| Dependencias transitivas totales resueltas | **77 paquetes** en `.venv-desktop/lib/python3.12/site-packages/` (incluye `onnxruntime` y `opencv-python`, superficie no trivial) |
| Análisis estático (semgrep, mismo ruleset que ADR-075: `p/security-audit`) | **14 rutas escaneadas, 0 hallazgos, 0 errores.** Primer intento dio `paths.scanned: []` — falso negativo por `.gitignore` (`.venv-desktop/` está ignorado y semgrep lo respeta por defecto); repetido con `--no-git-ignore` para un resultado real |

Estado del catálogo: `docs/design/mcp_catalog.yaml:171` — `trust: quarantined`,
`status: blocked-admission`, con `install: "env DISPLAY=:99
.venv-desktop/bin/computer-control-mcp"`. Existe además un gemelo
deliberadamente NO admitido en `:172`
(`computer-control-mcp-real-display`, `DISPLAY=:0`, `trust: unadmitted`) —
la distinción Xvfb-solo vs display real ya está modelada en el catálogo,
aunque el enforcement técnico de esa distinción no existe todavía (ver
huecos abajo).

## Los dos huecos de código que el scope pide y no existen

1. **No hay perfil de sandbox Xvfb-only real.** `find . -name "*.service"` no
   encuentra ningún `atlas-xvfb.service` trackeado; Xvfb `:99` no está
   corriendo en esta máquina. Lo que existe es la convención en
   `mcp_catalog.yaml` (arriba), no enforcement.
2. **`SentinelGate` no tiene camino de recibo para ejecutables de terceros.**
   La palabra `receipt` aparece una sola vez en `sentinel_gate.py`, dentro
   del mensaje de rechazo. `plugin_receipt_broker`/`plugin_activator` emiten
   recibos para plugins **declarativos** (ADR-073); no existe un tipo de
   recibo para un binario ejecutable de terceros.

Ninguno de los dos se ha implementado en este dossier — son especificación,
no código, hasta que el operador decida admitir o no el candidato.

## Alternativas comparadas

1. **Admitir con condiciones**: producir los 2 huecos de código (jaula Xvfb
   real + camino de recibo en Sentinel), re-materializar el paquete desde el
   sdist/wheel limpio (no desde el `pip install` ya ejecutado) a través del
   pipeline normal de ADR-075, y solo entonces activar.
2. **Mantener en cuarentena indefinidamente**: el estado actual
   (`blocked-admission`) ya bloquea la ejecución vía Sentinel; no hacer nada
   es una opción válida y de coste cero.

## Confidence and limits

**Confidence:** alta en los datos medidos (hash, licencia, deps, semgrep
limpio — todo verificado, no inferido). Baja en si "0 hallazgos de semgrep"
debe pesar mucho: `p/security-audit` es un ruleset genérico, no específico
para código que captura pantalla/teclado/ratón — un 0 aquí no certifica
ausencia de riesgo de uso indebido, solo ausencia de patrones de
vulnerabilidad de código conocidos.

**Falsifier:** si al re-materializar desde el sdist/wheel limpio (sin pasar
por `pip install`) el hash del árbol difiere del medido aquí, el paquete
instalado hoy no es reproducible desde una fuente pública verificable — eso
solo endurecería el caso para no admitir sin re-verificar.

**Revisit triggers:** cualquier nueva versión publicada de
`computer-control-mcp`; cualquier decisión sobre ADC-WO-116 (que gobierna
qué cuenta como "comando nativo gobernado" en Sentinel, del que depende el
segundo hueco).

## Security and rollback

Ninguna acción mutante en este dossier: no se reinstaló, no se movió el
paquete, no se tocó `mcp_catalog.yaml`, no se cambió el estado de
`blocked-admission`. Puramente observacional. Rollback: N/A.

## Evidencia

`.venv-desktop/lib/python3.12/site-packages/computer_control_mcp-0.3.10.dist-info/METADATA`,
`docs/design/mcp_catalog.yaml:171-172`,
`docs/design/mcp_catalog_stage1_triage.jsonl` (0 apariciones),
`docs/design/mcp_catalog_stage2_report.jsonl` (0 apariciones),
`workspace/mcp/quarantine/` (207 entradas, sin este paquete),
`src/atlas/security/sentinel_gate.py` (búsqueda de `receipt`),
semgrep 1.171.0 sobre `p/security-audit`, 14 rutas, 0 hallazgos, 2026-07-31.
