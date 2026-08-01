<!-- GENERADO por atlas handoff 2026-08-01T02:21:59.766816+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-01 (autobuild extendido) — Cut 2 medido, y el hallazgo cambia el
  tamaño del trabajo: el desfase real no son 3 versiones, son ~33.**
  **C1 (medición, sin tocar código de producto)**: el plan asumía medir
  `HOST_BASELINE` (`1.129.1`) vs CodeOSS actual — y ESE desfase sí es
  pequeño (`1.132.0`, 3 versiones, 13 días). Pero las 648 líneas nuestras
  (`atlas-ide`, `atlas-ide-forward-port`) están escritas sobre **Void**, y
  Void tiene su propio `package.json`: **`1.99.3`**. El desfase que Cut 2
  tiene que cerrar de verdad es Void → CodeOSS actual, **~33 versiones
  menores**, no 3. Nadie lo había medido hasta hoy.
  **Cómo se destapó**: un intento real de merge de 3 vías
  (`git merge-file`) sobre el único fichero compartido con vscode crudo
  (`app.ts`; los otros 7 ficheros modificados viven enteramente en
  `contrib/void/`, sin equivalente upstream) no encontró merge-base común
  entre el `app.ts` de Void (1505 líneas) y el de vscode — confirma que
  "portar" no es reaplicar un parche, es la tarea completa de
  fork-maintenance.
  **Verificado en vivo, no sólo citado**: `voideditor/void` rama `main`
  sigue en `1.99.3`, último commit `2026-06-02` — **la MISMA versión que
  nuestros checkouts**. El canon ya decía "Void congelado"; ahora hay
  evidencia en vivo. La brecha no la cierra Void solo: si Cut 2 avanza, el
  rebase lo hace este proyecto.
  **Informe completo**: `docs/design/cut2_codeoss_drift_measurement_2026-08-01.md`.
  Registro de linaje (`product_lineage_registry.jsonl`) anotado con la
  evidencia medida, SIN cambiar disposición — no se ha empezado el port.
  **Deliberadamente NO se intentó C2** (portar) esta tanda: con el alcance
  real medido, empezarlo habría producido trabajo a medias sin decirlo,
  justo lo que el operador pidió evitar. Punto de partida honesto para una
  tanda dedicada.
