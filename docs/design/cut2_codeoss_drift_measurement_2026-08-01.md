# Cut 2 — medición del desfase Void→CodeOSS (2026-08-01)

Fase C1 del plan de sesión (`~/.claude/plans/starry-roaming-scroll.md`):
*"medir el desfase antes de portar"*. Sin tocar código de producto — sólo
medición, en los cuatro checkouts reales.

## El hallazgo que cambia el alcance

El plan asumía que el desfase a medir era **`atlas-codeoss-1.129.1` (nuestro
`HOST_BASELINE`) vs CodeOSS actual**. Medido:

| | Versión | Commit | Fecha |
|---|---|---|---|
| Nuestro checkout `HOST_BASELINE` | `1.129.1` | `8a7abeba` | 2026-07-18 |
| `microsoft/vscode` HEAD real | `1.132.0` | `14a7e4c1` | 2026-07-31 |

**Ese desfase es pequeño: 3 versiones menores, 13 días.**

Pero el `HOST_BASELINE` no es el checkout que importa para el port real. Las
648 líneas nuestras (205 en `atlas-ide`, 443 en `atlas-ide-forward-port`)
están escritas sobre **Void**, y Void tiene su propio `package.json`:

```
atlas-ide/package.json            "version": "1.99.3"
atlas-ide-forward-port/package.json  "version": "1.99.3"
```

**El desfase real que Cut 2 tiene que cerrar es Void (`1.99.3`) → CodeOSS
actual (`1.132.0`): ~33 versiones menores, no 3.** El `HOST_BASELINE` que
fijamos en `1.129.1` ya estaba, él mismo, 30 versiones por delante de la base
de Void — nadie lo había medido hasta ahora.

## Por qué no es un simple `git apply`

Intento real de medición: extraje el único fichero que nuestro parche toca
que también es código vscode-core de verdad (`src/vs/code/electron-main/app.ts`
— los otros 7 ficheros modificados por `atlas-ide-forward-port` están bajo
`workbench/contrib/void/`, territorio propio de Void sin equivalente
upstream) y probé un merge de 3 vías real (`git merge-file`) contra
`HOST_BASELINE` viejo/nuevo.

**El propio intento reveló el hallazgo**: el `app.ts` de Void (1505 líneas)
no tiene un merge-base común con el `app.ts` crudo de `microsoft/vscode`
(1781→1912 líneas) — son historias independientes (Void mantiene su propio
repo, no un fork con historia compartida visible). Confirma que "portar" no
es reaplicar un parche: es la tarea de fork-maintenance completa que Void
mismo tendría que hacer para avanzar de `1.99.3` a `1.132.0`, y que
`ADC-WO-109` ya preveía en su forma general ("mueve/adapta... con estrategia
de actualización upstream") — pero sin el número real encima hasta hoy.

## Lo que SÍ se puede afirmar con esta medición

- `app.ts` cambia sustancialmente entre `1.129.1` y `1.132.0` (147
  inserciones/16 borrados — un bloque nuevo de telemetría de proxy del SO).
  Nuestro gancho (registro de `IAtlasBackendService`, líneas ~1105-1134) cae
  en una sección DISTINTA del fichero (registro de servicios al final, no la
  telemetría), así que no hay colisión de línea directa visible — pero un
  fichero con 33 versiones de más de distancia real necesita el propio
  `app.ts` de Void como punto de partida, no el nuestro.
- Los otros 7 ficheros de la rama viven enteramente bajo `contrib/void/` —
  cero equivalente en vscode crudo, cero riesgo de conflicto de MERGE con
  upstream (el riesgo es si el propio Void los movió/renombró entre
  `1.99.3` y su versión actual, pregunta que este documento NO responde:
  exige mirar el repo de Void, no el de vscode).

## Lo que NO se ha hecho, a propósito

No se ha intentado el port. Con el alcance real medido (~33 versiones, no 3),
empezarlo en esta tanda habría producido exactamente lo que el operador pidió
evitar la sesión anterior: trabajo a medias sin decirlo. Queda para una tanda
dedicada (C2), con esta medición como punto de partida honesto.

## Void está realmente congelado (verificado en vivo, no sólo citado del canon)

`voideditor/void`, rama `main`, consultada en vivo el 2026-08-01:

```
version: 1.99.3
último commit: b3166e7 · 2026-06-02 · "all repos"
```

**Es la MISMA versión que llevan nuestros dos checkouts.** El canon ya decía
"el upstream Void está congelado" (`docs/design/atlas_ecosystem_map.md`);
esto lo confirma con evidencia en vivo, no como supuesto: Void no ha
avanzado en casi dos meses. La brecha de ~33 versiones **no la va a cerrar
Void por nosotros** — si Cut 2 avanza, el rebase de la superficie de Void
sobre CodeOSS actual lo hace este proyecto, no un `git pull` del upstream.

## Siguiente paso recomendado (no ejecutado)

Con Void confirmado inmóvil, el trabajo de C2 no es "esperar a que Void se
actualice" — es un rebase activo. Antes de empezarlo: inventariar los
ficheros de Void FUERA de `contrib/void/` que además tocamos nosotros (hoy
sólo `app.ts`), porque son los únicos con riesgo real de conflicto contra
CodeOSS actual; los que viven enteramente en `contrib/void/` son aditivos y
no colisionan con upstream por definición.
