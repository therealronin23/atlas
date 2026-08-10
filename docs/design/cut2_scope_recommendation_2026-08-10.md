# Cut 2 — recomendación de alcance para ADC-WO-109 (2026-08-10)

Continúa `cut2_codeoss_drift_measurement_2026-08-01.md`. Aquel documento midió
el desfase y se detuvo, a propósito, antes de decidir. Éste responde la
pregunta que dejaba abierta y **recomienda**; la decisión sigue siendo del
operador (`operator_decision_required: true`).

Sólo medición sobre los checkouts reales. No se ha compilado nada — ver
"Límites" al final.

## La pregunta estaba mal planteada

El marco heredado es: *"hay que rebasar ~33 versiones de Void (1.99.3) hasta
CodeOSS actual (1.132.0), y Void está congelado desde el 2026-06-02, así que lo
hacemos nosotros"*. Es una tarea enorme y ha bloqueado `ADC-WO-109` desde
entonces.

Pero ese rebase sólo hace falta **si queremos las funciones de Void**. Nadie
había medido si las queremos. Medido ahora:

## Qué son en realidad nuestras 443 líneas

`git diff --numstat b3166e7..34803da` en `atlas-ide-forward-port`:

| Fichero | Líneas | Qué es |
|---|---|---|
| `contrib/void/electron-main/atlasBackendMainService.ts` | **+146** | **nuestro** (fichero nuevo) |
| `contrib/void/test/electron-main/atlasBackendMainService.test.ts` | **+208** | **nuestro** (fichero nuevo) |
| `contrib/void/common/voidSettingsTypes.ts` | +30 / −19 | modificación a Void |
| `contrib/void/common/modelCapabilities.ts` | +23 | modificación a Void |
| `contrib/void/electron-main/llmMessage/sendLLMMessage.impl.ts` | +13 | modificación a Void |
| `contrib/void/common/voidSettingsService.ts` | +11 / −1 | modificación a Void |
| `contrib/void/common/refreshModelService.ts` | +4 / −1 | modificación a Void |
| `code/electron-main/app.ts` | +8 / −1 | modificación a **vscode-core** |

**354 líneas (80%) están en ficheros que creamos nosotros. 89 son
modificaciones, y 81 de esas 89 caen en ficheros que sólo existen en Void.**

Matiz que corrige la lectura anterior: el documento del 01-ago decía que 7 de
los 8 ficheros son "aditivos, sin colisión con upstream". Están bajo
`contrib/void/`, sí — pero 6 de ellos son `M`, no `A`: **modifican fuente de
Void**, no la añaden. La ausencia de colisión con *vscode* es cierta; la
independencia de *Void* no lo era.

## El dato que decide

Los imports de `atlasBackendMainService.ts`, que es el núcleo del puente:

```ts
import { spawn, type ChildProcess } from 'child_process'
import * as http from 'http'
import * as fs from 'fs'
import * as path from 'path'
import { createDecorator, type IInstantiationService } from '.../platform/instantiation/common/instantiation.js'
```

**Cero imports de Void.** Stdlib de Node y **una** API core de vscode. Vive en
`contrib/void/` por convención de carpeta, no por dependencia.

Y esa API existe en el host, verificado en el checkout `HOST_BASELINE`
(`atlas-codeoss-1.129.1`):

```
src/vs/platform/instantiation/common/instantiation.ts
  :52   export interface IInstantiationService
  :109  export function createDecorator<T>(...)
```

`app.ts` también existe (84 KB), que es donde va el gancho de 8 líneas.
`contrib/void/` no existe en CodeOSS — lo esperado.

## Recomendación: abandonar la línea Void

**Tomar CodeOSS como host y portar el puente de Atlas directamente encima. No
rebasar Void.**

Lo que se conserva: las 354 líneas nucleares (servicio + sus 208 de test) y el
gancho de 8 líneas en `app.ts`, que es vscode-core y está en CodeOSS.

Lo que se tira: las 81 líneas que enganchan con Void. Son fontanería para
registrar a Atlas como proveedor de modelos **en la UI de chat de Void** —
`voidSettingsService`, `modelCapabilities`, `sendLLMMessage`. Y esa UI ya está
superada por decisión propia: **ADR-085 eligió Flutter en exclusiva**, y la
Mission Console (construida el 2026-08-10, 26 ficheros, verificada contra el
runtime vivo) es la superficie de Atlas. Rebasar 33 versiones de Void para
conservar una UI de chat que ADR-085 sustituyó es pagar el coste más alto del
proyecto por la pieza que ya decidimos no usar.

Con esto **`ADC-WO-109` deja de depender del rebase** y su alcance pasa a ser:
un servicio autocontenido, un gancho de 8 líneas y el pin exacto de upstream.

## Lo que esta recomendación NO afirma

- **No se ha compilado.** La afirmación es sobre imports y procedencia de
  ficheros, no sobre un build verde. `platform/instantiation` es de las APIs
  más estables de vscode, pero entre la base de Void y 1.132.0 hay distancia
  real y eso no se ha ejercitado.
- **No se ha medido qué hace `atlasBackendMainService.ts`** más allá de sus
  imports. Si su lógica asume convenciones de Void en runtime (rutas, ajustes),
  aparecería al compilar, no leyendo cabeceras.
- **El pin exacto de CodeOSS sigue abierto.** El `HOST_BASELINE` local es
  `1.129.1` (2026-07-18) y upstream iba por `1.132.0` el 31-jul. Elegir el pin
  es parte de la decisión, no de esta medición.
- **No dice nada de `ADC-WO-111`** (Android). Aunque ADR-085 + Mission Console
  apuntan a que la proyección Android sea la misma app Flutter en otro target,
  eso no se ha medido y no se afirma aquí.

## Si se prefiere la otra rama

Mantener Void es defendible sólo si se quiere su UI de chat y su fontanería de
proveedores. En ese caso el coste es el rebase de ~33 versiones, con Void
congelado desde el 2026-06-02 y sin merge-base común entre su `app.ts` (1505
líneas) y el de vscode (1912) — o sea, trabajo de fork-maintenance completo, no
un `git apply`. La recomendación de arriba existe precisamente para que esa
factura se pague sólo si se quiere lo que compra.

---

# Resultado del spike (2026-08-11)

La recomendación de arriba se apoyaba en imports y procedencia de ficheros, y
declaraba explícitamente que **no se había compilado**. Ya se ha comprobado.

## Qué se hizo

Rama `spike/atlas-bridge-on-codeoss` en `~/proyectos/atlas-codeoss-1.129.1`,
commit `bfc15ab0`:

```
contrib/void/electron-main/atlasBackendMainService.ts
   ->  contrib/atlas/electron-main/atlasBackendMainService.ts
```

**Ni un import cambia.** Las rutas relativas tienen la misma profundidad desde
`contrib/atlas/electron-main/` que desde `contrib/void/electron-main/`, y el
fichero sólo importa stdlib de Node y `platform/instantiation`. El gancho de
`app.ts` se reancla en puntos genéricos de vscode-core (bloque de imports,
`services.set` antes de `Promises.settled`, y el `return` de `createChild`);
los anclajes que usaba en Void citaban servicios propios de Void que aquí no
existen, pero ninguno de los que el gancho necesita.

## Typecheck, con control

Configuración del propio repo (`tsconfig.base.json` + `src/typings/*.d.ts`),
con las versiones que fija su `package.json`: TypeScript `6.0.0-dev.20260416`
y `@types/node` 24.

| | errores |
|---|---|
| con el fichero portado | **16** |
| **CONTROL**, misma config sin él | **16** |

Idénticos, uno a uno. **El port introduce cero errores de tipo.** Los 16 son
ruido del banco: un typecheck de proyecto único fuerza los tipos de Node sobre
`base/common`, capa que CodeOSS compila sin ellos (`Timeout` vs
`TimeoutHandle`). No aparecen en el build real del repo.

El control importa: sin él, "16 errores" se lee como fracaso. Es la misma
disciplina que el `OracleSolver` del banco de fitness — una medida sin control
no es una medida.

## Una sospecha mía que resultó falsa

Al leer el gancho pensé que `this._register(service)` no compilaría, porque
`_register<T extends IDisposable>` exige `IDisposable` y las seis primeras
líneas de `IInstantiationService` no lo declaran. Probado con un fichero sonda
que reproduce el gancho exacto: **compila**. El interfaz sí declara `dispose()`
más abajo (`instantiation.ts:76`) y satisface `IDisposable` estructuralmente.
Mi grep se quedó corto; el compilador lo zanjó.

## Límite que seguía en pie — cerrado el 2026-08-11

**Esto no era un build completo.** El checkout no tiene `node_modules` (VS Code
pide varios GB y compilación nativa), así que se ha verificado la superficie de
API por tipos, no que Electron arranque ni que el servicio spawnee el bridge en
tiempo de ejecución. Eso es el siguiente paso, y es cualitativamente distinto:
`npm install` + `npm run compile` + arrancar.

De paso: la cabecera del fichero arrastraba `Copyright 2025 Glass Devtools` por
copia-pega del vecino de Void. Corregida en el port — el fichero es de Atlas.

---

# Build real (2026-08-11) — y un falso verde mío

## Resultado

`npm install` + `npm run compile` en `~/proyectos/atlas-codeoss-1.129.1`, rama
`spike/atlas-bridge-on-codeoss`, commits `bfc15ab0` (port) y `49bc7aa2` (fix):

| Paso | Resultado |
|---|---|
| `npm install` | **rc=0** — 1563 paquetes en 9 min, 0 errores npm, 2 módulos nativos compilados |
| `tsgo --project src/tsconfig.json --noEmit` | **rc=0** — 0 errores en TODO el árbol |
| `node build/checker/layersChecker.ts` | sin violaciones de capa |
| `tsgo --project build/checker/tsconfig.electron-main.json` | **rc=0** |
| `npm run compile` | **rc=0** en 4,9 min · 62 tareas con 0 errores · `out/` 380 MB |

Y el puente está en la salida del build, que es la prueba que importa:

```
out/vs/workbench/contrib/atlas/electron-main/atlasBackendMainService.js  (17 KB)
out/vs/code/electron-main/app.js  ->  AtlasBackendMainService     x2
                                      IAtlasBackendService        x2
                                      resolveAtlasBackendService  x2
```

**La recomendación de portar sobre CodeOSS queda verificada por compilación**,
no sólo por lectura de imports.

## Preparación que evitó perder el tiempo

El repo pide Node `24.18.0` (`.nvmrc`) y `build/npm/preinstall.ts` rechaza
cualquier minor inferior; había 24.15.0. Comprobado ANTES de lanzar el install
—el gate habría matado la instalación a mitad— e instalado con `nvm`. La 26.1.0
que ya estaba tampoco vale: el gate exige major 24 exacto. El resto de
prerequisitos (python3/make/g++/pkg-config, x11, libsecret-1, xkbfile, gio-2.0,
nss) estaban.

## El falso verde, que es lo más útil de esta tanda

El spike del día anterior concluyó "cero errores introducidos" con un banco
acotado **y con control**. El árbol completo encontró un error real en nuestro
propio fichero, de la misma familia que yo había descartado como ruido:

```
atlasBackendMainService.ts(134,3): error TS2740:
  Type 'TimeoutHandle' is missing the following properties from type 'Timeout'
```

CodeOSS declara un handle opaco propio en `src/typings/base-common.d.ts`
—`interface TimeoutHandle { readonly _: never }`, con el comentario *"a trick
that seems needed to prevent direct number assignment"*— y su `setTimeout`
devuelve ese, no `NodeJS.Timeout`. El fichero portado declaraba el de Node.

El control de ayer **era correcto** para los 16 errores de `base/common`: esos
sí eran artefacto del banco. Pero había un caso genuino de la misma familia
dentro de nuestro código, y sólo aparece cuando el proyecto entero resuelve el
`setTimeout` ambiental como lo hace el build.

Moraleja, aplicada a mí mismo: **una aproximación de la puerta no es la puerta,
ni siquiera con control.** Es la misma clase de defecto que esta auditoría
lleva persiguiendo toda la semana —el smoke del tronco MCP que hacía
`tools/list` sin invocar, la CLI probada con `--help`, los tests de ACP que
excluían el transporte— y esta vez el que la cometió fui yo. Por eso el límite
"no se ha compilado" estuvo escrito y repetido en cada entrega hasta hoy.

## Lo que sigue sin estar probado

**Compilar no es ejecutar.** No se ha arrancado Electron, así que no está
verificado que el servicio spawnee `atlas coding-bridge` ni que sobreviva al
ciclo de vida real de la aplicación. Ese es el siguiente escalón y vuelve a ser
cualitativamente distinto.
