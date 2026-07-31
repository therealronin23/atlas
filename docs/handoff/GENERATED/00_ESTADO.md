<!-- GENERADO por atlas handoff 2026-07-31T22:42:45.999180+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 — CIERRE DE SESIÓN. Todo empujado a `main`; el operador vuelve
  con una idea nueva.**
  **Qué se cerró hoy**: F0.2 (radar de código dormido regex→AST: veía 2 de 16),
  F1 completo salvo `correction.py` (1.211 de 1.315 loc dormidos despertados),
  monitorización local con aviso por Telegram (verificada extremo a extremo en
  el móvil del operador), Cónclave con modelos de razonamiento, y el rediseño
  de `atlas reality`.
  **Estado medido al cierre**: suite **4955 passed · 6 skipped**, `check_canon`
  PASS (2105), `mypy` limpio, daemon `active`, watchdog `active`, Hermes
  `live_verified: true`, `.env` en 600 y fuera de git.
  **DECISIONES TOMADAS POR EL OPERADOR AL CIERRE (2026-08-01)** — dirección
  fijada; el diseño de detalle queda para la sesión siguiente:
  1. **Productor de parches: "adaptador determinista CON LLM"**. Ni la opción
     (a) pura determinista (estéril) ni la (b) planificador LLM libre.
     **TENSIÓN QUE HAY QUE RESOLVER ANTES DE CONSTRUIR**: esa forma híbrida es
     exactamente la que el Cónclave demolió como *erosión encubierta*, y el
     operador dice a la vez que **"el Cónclave estuvo bien hasta ahora"**. Las
     dos cosas no pueden ser ciertas sin más precisión. Lectura que SÍ podría
     sobrevivir a las 5 objeciones de Mistral: **el determinismo va en la
     PUERTA, no en el planificador** — el LLM propone, y un adaptador
     determinista sólo acepta parches que encajen en formas permitidas, con la
     ruta gobernada de ColdUpdate intacta detrás. No construir hasta que esa
     distinción esté escrita y contrastada.
  2. **El Cónclave pasa de 3 voces a 5 como mínimo.** El operador recuerda que
     el original del que salió la idea tenía ≥5. **VERIFICADO HOY**:
     `_TRIO_NAMES` es una constante de 3, no un límite de arquitectura, y hay
     **seis** linajes de preentrenamiento con clave viva sin credenciales
     nuevas — Google, Zhipu, Mistral, Meta/Llama, Alibaba/Qwen,
     NVIDIA/Nemotron. Coherente con su propio diseño ("la diversidad se mide
     por linaje, no por vendor de hosting"). Bonus: hoy 2 de 3 asientos van
     con el primario tocado (`nvidia_glm` se cuelga, `nvidia_mistral_large`
     da 410), así que 5 asientos reducen el radio de daño.
     **HUECO REGISTRADO**: de qué repo salió la idea del Cónclave **no está
     escrito en ningún sitio del canon**. Pendiente de que el operador lo diga.
  3. **El prompt hostil NO se toca por ahora** — "el Cónclave estuvo bien
     hasta ahora". El hallazgo del `BLOCKING` a un timeout de 30→60s queda
     anotado, no accionado. Revisar DESPUÉS de ampliar a 5 voces: puede que
     con más asientos la señal de desacuerdo mejore sin tocar el prompt.
  4. **Forks y absorciones: hacerse y CERRARSE.** Se acabó dejarlos abiertos.
  5. **Cut 2 = Void + CodeOSS ACTUAL de 2026**, no el spike fijado en
     `1.129.1`. Implica actualizar el `HOST_BASELINE` del registro de linaje.
  6. **Hermes debe autocorregirse** con correcciones y ayuda del asistente.
  7. **El stack de UI (T2.1) puede esperar.**
  8. **Criterio transversal del operador**: muchas de estas decisiones van en
     concordancia con **Void, Zed, Codex y Cursor** — no decidirlas aisladas
     de lo que hacen esas herramientas.
  **Frentes sin empezar**: dossier de Osmosis (F2.1), replanteo de alcance de
  UI (F3.1), e investigar+planificar `business/extract.py` y
  `mcp/adapter_registry.py` (los 2 dormidos que el radar nuevo destapó).
  **Absorción — lo que queda medido (grep + radar AST, 2026-08-01)**:
  LangGraph es la ÚNICA fila de la matriz con cero código (ni `StateGraph` ni
  aristas condicionales); y `LessonStore.apply_lifecycle_transitions()`
  —portado de `curator.py` de Hermes el 18-jul, 9 tests verdes— tiene **CERO
  callers de producción**: `record_recall()` sí está cableado, así que Atlas
  lleva semanas contando uso de lecciones **sin que nada las envejezca jamás**
  a `stale`/`archived`. Mismo fallo de clase que ADC-WO-108.
