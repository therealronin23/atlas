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
