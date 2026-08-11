# Cut 2 — alcance de producto, medido

<!-- Doc interno de diseño. Cubre el `scope` de ADC-WO-109 que quedaba en cinco palabras. -->

**Estado**: medido el 2026-08-11 sobre el checkout real
`~/proyectos/atlas-codeoss-1.129.1`, rama `spike/atlas-bridge-on-codeoss`.
**Ficha**: `ADC-WO-109`, `scope`: *exact upstream pin · privacy, branding,
Open VSX, update, packaging · comprehensive E2E and rollback*.
**Ya cerrado de esa ficha**: el puente compila, arranca y negocia versión; el
E2E `cambio → hallazgo → propuesta → aprobación → recibo` existe; la
degradación sin backend también. Falta lo de abajo.

Este documento no decide nada que sea del operador (nombre, dominio, a qué
galería apuntar). Mide lo que hay y dice lo que cuesta cada pieza, para que la
decisión se tome sobre datos y no sobre la palabra "empaquetado".

---

## 1. El pin exacto — **el más barato de los siete, y se creía lo contrario**

| | |
|---|---|
| Pin local | **1.129.1** (`ac355fb4d039edb8cc28e1f8e45c6d5d8c437fe2`) |
| Upstream hoy | **1.132.0** |
| Deriva | **3 releases menores** (1.130.0, 1.131.0, 1.132.0) |

Lo que importa no es cuántas versiones, sino **qué toca de lo nuestro**. El
puente vive en `contrib/atlas/` (nuestro, upstream no lo toca) y engancha en
tres ficheros del host. Diff `1.129.1 → 1.132.0` de esos tres:

| Fichero | Cambio |
|---|---|
| `src/vs/platform/instantiation/common/instantiation.ts` | **sin cambios** — es la API que importa el servicio |
| `src/typings/base-common.d.ts` | **sin cambios** — es el `TimeoutHandle` que nos costó un TS2740 |
| `product.json` | 4 líneas |
| `src/vs/code/electron-main/app.ts` | 168 líneas (153+/19−) |

Las 168 líneas de `app.ts` asustan hasta mirar **dónde**. Nuestro hook son 8
líneas en dos anclajes, y los dos sobreviven intactos en 1.132.0:

```
1.129.1  services.set(ICSSDevelopmentService, new SyncDescriptor(...))   ← insertamos justo después
1.132.0  services.set(ICSSDevelopmentService, new SyncDescriptor(...))   línea 1298, mismo comentario encima

1.129.1  return this.mainInstantiationService.createChild(services);      ← partimos en const + resolve
1.132.0  return this.mainInstantiationService.createChild(services);      línea 1306, idéntica
```

El churn upstream está en otras partes del fichero (servicios de MCP gateway,
sobre todo), no en nuestra zona de inserción.

**Recomendación (la decisión sigue siendo del operador): pinear en 1.132.0
ahora**, mientras la deriva es de tres releases y los anclajes son literalmente
la misma línea. El coste medido es re-aplicar 8 líneas y recompilar. Esperar
sólo hace que esa cifra crezca.

> **HECHO Y VERIFICADO el 2026-08-11**, unas horas después de escribir lo de
> arriba. Rama `spike/pin-1.132.0` en el checkout del fork. Los dos anclajes
> estaban exactamente en `:1298` y `:1306`; `contrib/atlas/` (4 ficheros)
> entró **sin tocar una línea**. Verificado en los tres niveles, con el código
> de salida leído fuera de la tubería: `npm install` rc=0 (hizo falta el Node
> 24.18.0 de nvm — la puerta de `preinstall.ts` rechaza el 24.15.0 del PATH),
> `npm run compile` rc=0 con «0 errors» en 3,92 min, y `node --test` 21/21. Y
> **arrancando** sobre Xvfb :99, que es lo que cierra «compilar no es
> ejecutar»: el Workbench 1.132.0 spawneó el `atlas coding-bridge` real
> escuchando en 7342. La rama anterior queda intacta como rollback.
>
> Lo que esto convierte en dato: subir el pin ya no es una estimación.

Esto corrige de paso la intuición que traía el proyecto: la conversación
temía un rebase caro. El rebase caro era el de **Void** (~33 versiones), y ese
ya se descartó al elegir CodeOSS como host. El del host es de otro orden.

---

## 2. Privacidad — **ni "ya está" ni "queda todo"**

La suposición cómoda era que Code-OSS ya es privado y que la tubería de
VSCodium es trabajo pendiente. Medido sobre las 45 claves del `product.json`,
ninguna de las dos cosas.

**La telemetría es imposible por construcción, no por configuración.** La
puerta real está en `telemetryUtils.ts:125`:

```ts
if (productService.enableTelemetry && productService.aiConfig?.ariaKey) { … }
```

y este `product.json` **no tiene ninguna de las dos claves**. Tampoco
`crashReporter`, `experimentsUrl`, `surveys`, `settingsSearchUrl` ni
`msftInternalDomains`. No hay nada que apagar: no hay a dónde enviar. Eso es
más fuerte que `enableTelemetry: false`, que se vuelve a encender con una
línea.

**Pero quedan tres salidas de red reales**, y decir "ya es privado" habría
sido falso:

| Clave | Destino | Qué es |
|---|---|---|
| `voiceWsUrl` | `wss://falcon-caas.mai.microsoft.com/voice-code/api/v1/realtime/voice` | WebSocket de voz de Microsoft |
| `webviewContentExternalBaseUrlTemplate` | `https://{{uuid}}.vscode-cdn.net/insider/<sha>/…` | contenido de webviews desde el CDN de Microsoft |
| `defaultChatAgent` | ids de `GitHub.copilot` / `copilot-chat` + URLs de documentación | agente de chat por defecto |

Más `trustedExtensionAuthAccess`, que concede acceso a la autenticación de
GitHub a Copilot Chat, y `builtInExtensions`, que descarga extensiones en
tiempo de build **con `sha256`** (verificable, no ciego).

**Vigilado en código**:
`src/vs/workbench/contrib/atlas/test/common/atlasProductPrivacy.test.ts`. No
exige "cero salidas" —hoy sería mentira— sino que el conjunto sea exactamente
el medido: cualquier clave nueva con `https://`, `wss://` o `http://` hace
fallar el test. Añadir una salida pasa a ser una decisión explícita en vez de
una línea que nadie ve. Siete casos, corren sueltos en 0,2 s.

**Pendiente de decisión del operador**: qué hacer con las tres. Vaciar
`voiceWsUrl` y `defaultChatAgent` es trivial y sin efectos colaterales; el
CDN de webviews **no** lo es (servir webviews desde el mismo origen tiene
implicaciones de seguridad que VSCodium resuelve con su propio dominio).

---

## 3. Branding — mecánico, pero necesita nombres

Estado actual, todo sin tocar de Code-OSS:

| Clave | Valor hoy |
|---|---|
| `nameShort` / `nameLong` | `Code - OSS` |
| `applicationName` | `code-oss` |
| `dataFolderName` | `.vscode-oss` |
| `urlProtocol` | `code-oss` |
| `win32AppUserModelId` | `Microsoft.CodeOSS` |
| `licenseUrl` / `reportIssueUrl` | apuntan a `microsoft/vscode` |

Hay además ~15 claves `win32*` y `darwin*` (AppIds, mutexes, bundle
identifiers) que van juntas. El trabajo es mecánico y de una sentada; lo que
bloquea es el conjunto de nombres, que es del operador: nombre corto, nombre
largo, protocolo de URL, carpeta de datos y a dónde van los enlaces de
licencia e incidencias.

`dataFolderName` merece un aviso: cambiarlo **estrena perfil** — extensiones y
ajustes del `.vscode-oss` actual dejan de verse. Es la decisión correcta para
un producto propio, pero hay que tomarla sabiéndolo.

---

## 4. Open VSX — una clave, y una consecuencia

Medido: **no hay `extensionsGallery` en absoluto**. Sin
`extensionsGallery.serviceUrl`, `ExtensionGalleryManifestService` reporta
`Unavailable` (`extensionGalleryManifestService.ts:29`) y **no se puede
instalar ninguna extensión de ninguna galería**. Hoy el fork sólo tiene las
`builtInExtensions`.

Apuntar a Open VSX es añadir un objeto con `serviceUrl`, `itemUrl` y
`resourceUrlTemplate`. Lo que hay que decidir no es eso, es lo de después:
Open VSX no tiene el catálogo del marketplace de Microsoft, y usar el de
Microsoft desde un build no oficial **viola sus términos de uso**. Es una
decisión de producto, no de configuración, y el test de §2 la deja registrada
el día que se tome.

---

## 5. Actualización — sin canal, y probablemente esté bien

Medido: no hay `updateUrl` ni `quality`. El fork no se actualiza solo y no
consulta a nadie.

Para un producto que se despliega desde el propio repo del operador, montar un
servidor de actualizaciones es coste sin beneficio claro. La alternativa
honesta es `git pull` + rebuild, que es lo que ya se hace. **Recomendación:
dejarlo sin canal y decirlo en la documentación del producto**, en vez de
montar infraestructura que nadie va a mantener. Si algún día hay más de un
usuario, se revisa.

---

## 6. Empaquetado — existe y es de upstream

`build/gulpfile.vscode.linux.ts` ya trae las tareas, con arquitectura
parametrizada:

```
vscode-linux-<arch>-prepare-deb   / -build-deb
vscode-linux-<arch>-prepare-rpm   / -build-rpm
vscode-linux-<arch>-prepare-snap  / -build-snap
```

No hay que construir empaquetado: hay que **ejercitarlo una vez** y ver qué se
rompe con el branding cambiado (los `.deb`/`.rpm` llevan dentro el nombre de
aplicación, el icono `linuxIconName` y el protocolo de URL). Depende de §3,
así que va después.

**Sin medir todavía**: cuánto tarda y cuánto ocupa un `.deb` completo. No se
ha corrido ninguna vez.

---

## 7. Rollback

El de la ficha (*"restaurar el último host compilable y desactivar las
costuras de Atlas por separado"*) ya se cumple por construcción, y conviene
dejarlo escrito porque es lo que hace barato equivocarse:

- El puente vive **entero** en `contrib/atlas/` salvo 8 líneas en `app.ts`.
  Quitar esas 8 líneas deja un CodeOSS de serie que compila.
- El backend es un **proceso aparte** (`atlas coding-bridge`): si no está, el
  Workbench arranca igual y lo dice en el log. Verificado ejecutando el
  2026-08-11.
- El pin es un tag de git; volver a 1.129.1 es un `git checkout`.

---

## Orden recomendado

`1 (pin) → 3 (branding) → 4 (Open VSX) → 6 (empaquetado) → 2 (las tres salidas)`

El pin primero porque su coste crece solo. El branding antes que el
empaquetado porque el segundo mete el primero dentro del paquete. Las tres
salidas de red al final porque son las únicas que necesitan una decisión con
matiz — las otras son mecánicas o ya están.

**§5 (actualización) no está en el orden** porque la recomendación es no
hacerlo.

## Lo que este documento NO afirma

- No decide nombres, dominio ni galería: eso es del operador.
- No afirma que el `.deb` funcione: nunca se ha construido uno.
- No afirma que 1.132.0 compile con el puente: afirma que los dos anclajes son
  idénticos y que los otros dos ficheros no cambiaron. Compilar sigue siendo
  el siguiente paso, y **compilar tampoco es ejecutar** — la lección de esta
  misma semana.
