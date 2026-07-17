# Dossier de investigación — Tauri v2 (candidato principal) y React Native (secundario) para la UI cinematográfica de Atlas

Contexto evaluado: apps DEDICADAS (no web) Linux desktop + Android, un solo código, estética JARVIS (negro profundo, acento cian, grafos de nodos con glow animado, paneles flotantes glass, motion 60fps), cliente HTTP+WS contra `127.0.0.1:7341` (API read-only local + eventos), build en portátil modesto (16GB RAM, earlyoom mata procesos >7.5GB, `/tmp` tmpfs 4GB, GPU GTX 960M). Advertencia previa del proyecto: compilar Tauri/webkit2gtk en esta máquina ya se señaló como coste real (ADR-059). Ya existe un shell Vite7+React18+TS (1.930 líneas TSX) cableado al API.

Fecha de investigación: 2026-07-17. Fuentes 2025-2026 vía WebSearch/WebFetch (herramienta de búsqueda web quedó intermitentemente no disponible a mitad de la investigación por un problema de infraestructura del clasificador de seguridad — cubierto igualmente con lo recabado, sin recurrir a memoria del modelo).

---

## PARTE 1 — TAURI v2

### 1. ¿Soporte Android estable en 2026?

- Tauri 2.0 estable salió en octubre de 2024; a julio de 2026 el proyecto va por la línea **2.11.x** (2.11.5, publicada el 1 de julio de 2026), con parches cada pocas semanas. El **desktop** (Windows/macOS/Linux) tiene casi dos años de uso real en producción (Spacedrive, AppFlowy, Clash Verge). [Tauri 2.0 Stable Release](https://v2.tauri.app/blog/tauri-20/), [Build Mobile and Desktop Apps From One Codebase](https://www.mayhemcode.com/2026/07/build-mobile-and-desktop-apps-from-one.html)
- El soporte **móvil (iOS/Android)** es más nuevo que el de escritorio: "funciona, pero vas a encontrar aristas en soporte de plugins, firmado, y peculiaridades del webview" — cita directa del análisis de mediados de 2026. La experiencia de desarrollo (DX) para móvil sigue en mejora activa, no está al nivel de pulido del desktop. [mayhemcode.com, jul-2026](https://www.mayhemcode.com/2026/07/build-mobile-and-desktop-apps-from-one.html)
- No encontré un hilo consolidado de "devs publicando en Google Play con Tauri 2" con volumen — la señal es indirecta (issues de GitHub activos sobre firmado, red local y permisos, ver §5), lo cual en sí mismo es un dato: la base de developers Android-en-producción con Tauri es todavía pequeña comparada con Flutter/RN.

**Veredicto parcial**: Android en Tauri 2 es real y usable, pero es la pata más joven del framework — no tiene la madurez de años que sí tiene el desktop.

### 2. Honestidad webview: rendimiento real

**Linux (webkit2gtk):**
- Arquitectura de compositing subóptima documentada por el propio proyecto WebKitGTK: el WebProcess pinta directamente sobre una X Window propiedad del UIProcess, sin integración con el paint loop del UIProcess — esto es la raíz de buena parte del jank en Linux. Mejoras en Wayland (WebKitGTK+ 2.17.92) redujeron CPU y memoria, pero el problema estructural persiste en versiones posteriores. [The WebKitGTK Project](https://webkitgtk.org/), [WebKitGTK+ 2.17.92 - Phoronix](https://www.phoronix.com/news/WebKitGTK-2.17.92-Released)
- **Dato de campo, el más contundente encontrado**: un desarrollador reportó que su app Tauri "solo llega a 40fps en Ubuntu con webkitgtk" pese a aceleración GPU, contra **240fps** al portar la misma app a Electron (Chromium). Un mantenedor de Tauri respondió con honestidad brutal: *"with webkitgtk getting worse/more unstable each release i changed my mind"* sobre recomendar Tauri para Linux. Otro usuario: *"Webview on linux is still shit"*, con fallos incluso en carga de vídeo. Un tercero reportó no poder *"run any serious wasm application with webkit on Linux"* (referencia a un bug upstream de WebKit, #259441, con arreglo lento). [Discusión tauri-apps #8524](https://github.com/orgs/tauri-apps/discussions/8524)
- El equipo de Tauri confirma que **no existe** una librería de webview basada en Firefox como alternativa, y que la única vía de escape (CEF/Chromium embebido) está "en progreso" desde noviembre de 2025 pero el trabajo interno (dogfooding en proyectos de cliente) va primero; *"the open source work will follow a bit later"* — sin ETA pública. [misma discusión #8524]

**Android (WebView del sistema):**
- El Android System WebView es Chromium puro, actualizado vía Google Play de forma independiente de la versión de Android (desde Lollipop), siguiendo el ciclo de 6 semanas beta→stable de Chromium — esto es estructuralmente MUCHO menos fragmentado que el mosaico de escritorio (WebView2/WKWebView/webkit2gtk). [Android WebView - Chromium docs](https://chromium.googlesource.com/chromium/src/+/HEAD/android_webview/docs/faq.md)
- WebGL "funciona en general en móvil (Android e iOS) sin cuidados especiales" según discusiones de la comunidad Tauri — pero esto contrasta con bugs reales de WebGL en el webview de **desktop** (ver §3). No encontré benchmarks específicos de fps para Tauri-en-Android con escenas WebGL complejas (glow, partículas, grafos de nodos) — es un hueco real de evidencia, no una garantía.

**Conclusión de honestidad**: por dentro SIGUE siendo un webview, y en Linux esto no es teórico — hay un mantenedor de Tauri documentado retractándose en público de recomendar la plataforma para Linux, con una cifra de 40fps vs 240fps de Chromium. Android es la cara más segura de esta apuesta (WebView moderno y centralizado), Linux es la más débil — justo el escritorio que el operador va a usar a diario.

### 3. Capacidad cinematográfica (WebGL/WebGPU, three.js/pixi, "no sentirse web")

- WebGL2 ha estado indisponible en ciertas versiones del webview de Tauri según un hilo de discusión. [WebGL2 support #2866](https://github.com/tauri-apps/tauri/discussions/7966)
- Bug documentado y **sin resolver desde marzo de 2023**, etiquetado `status: upstream` (bloqueado en WebKit, no en manos de Tauri): escenas three.js que fallan con "WebGL: context lost" en la ventana de la app de escritorio, mientras funcionan perfectamente en el navegador normal — con alto uso de CPU acompañando el fallo. [Issue #6559](https://github.com/tauri-apps/tauri/issues/6559), caso similar en [Issue #8498](https://github.com/tauri-apps/tauri/issues/8498) (three.js: "Could not create a WebGL context")
- **"No sentirse web" no es automático**: Tauri **no soporta estilizar la scrollbar** vía `::-webkit-scrollbar` — hay que recurrir a librerías JS externas (overlayscrollbars) para eliminar el chrome de navegador. Selección de texto nativa, menú contextual de clic derecho, "rubber band"/bounce de scroll — todo eso hay que desactivarlo manualmente vía CSS (`user-select:none`, `overscroll-behavior:none`) y JS; no viene apagado por defecto. Un análisis lo resume sin rodeos: *"Tauri es básicamente Electron con dos diferencias mayores: usa el webview del sistema y backend Rust"* — sigue siendo, en esencia, una página web con chrome quitado a mano. [Discusión #6067](https://github.com/tauri-apps/tauri/issues/6067), [Discusión #8829](https://github.com/orgs/tauri-apps/discussions/8829)
- En cuanto a capacidad bruta de motion: un benchmark cruzado de sistemas de animación web (ene-2026) encontró que WebGL es la tecnología más estable a gran escala (5.000-10.000 objetos animados), mientras que animación DOM-pura degrada notablemente pasados ~500 objetos — lo cual favorece construir los grafos de nodos con glow en WebGL/three.js/pixi.js en vez de CSS/DOM puro, independientemente del contenedor (Tauri o navegador). [Cross-Device Benchmark of Modern Web Animation Systems, jimaging 2026](https://doi.org/10.3390/jimaging12010045)

**Conclusión**: SÍ es técnicamente posible lograr look cinematográfico con WebGL/three.js dentro de Tauri — pero (a) hay un bug real de "WebGL context lost" abierto y sin arreglo desde 2023 específicamente en el contenedor de escritorio de Tauri, bloqueado upstream; y (b) despojar la sensación "web" (scrollbars, selección, bounce) exige trabajo manual explícito, no es gratis.

### 4. Coste de build en portátil modesto

- Hay un problema de build documentado y bien diagnosticado: `tauri dev` recompila dependencias sin cambios en cada iteración por un conflicto de variables de entorno entre `rust-analyzer` (que corre `cargo check` sin `MACOSX_DEPLOYMENT_TARGET`) y el build real de `tauri dev` — provoca recompilaciones dobles. El fix (target dir separado + perfil de Cargo) bajó los tiempos de un desarrollador de ~25s a ~10s por iteración — lo cual implica que SIN ese tuning, los tiempos de compilación en máquinas modestas son sensiblemente peores. [How to make your Tauri dev faster](https://dev.to/ahonn/how-to-make-your-tauri-dev-faster-2en1)
- Bug de memoria conocido en Linux: uso de RAM crece mucho al redimensionar la ventana repetidamente y **no baja hasta cerrar la app** — riesgo concreto dado que earlyoom en esta máquina mata procesos >7.5GB. [Issue #10102](https://github.com/tauri-apps/tauri/issues/10102)
- En runtime (no build), Tauri 2.9.6 usa ~50% menos RAM que Electron — dato positivo pero no responde a la pregunta de coste de *compilación* Rust+webkit2gtk, que sigue siendo la native compilation completa de un binario Rust con enlazado contra GTK/WebKitGTK — no hay cifras públicas específicas de tiempo/RAM de build encontradas para hardware equivalente a GTX 960M/16GB, pero la fricción documentada del propio proyecto (necesidad de tuning solo para llegar a 10-25s por cambio incremental) es señal de que el build **inicial** completo (`cargo build --release` desde cero, con el linkeo de webkit2gtk) es la operación cara — coherente con la advertencia previa ADR-059 del proyecto.
- **Android**: por defecto Tauri compila para las 4 arquitecturas (aarch64, armv7, i686, x86_64) salvo que se use `--split-per-abi` para generar APKs individuales más pequeños. Requiere NDK 28+ para cumplir el nuevo requisito de Google de páginas de memoria de 16KB en apps nuevas. No hay cifras públicas de tamaño de APK citadas en las fuentes consultadas. [App Size | Tauri](https://v2.tauri.app/concept/size/), [Prerequisites | Tauri](https://v2.tauri.app/start/prerequisites/)
- **Sin cuentas**: firmar un APK/AAB para sideload NO requiere cuenta de Google Play — se genera un keystore Java propio vía `keytool` y se firma localmente. [Android Code Signing | Tauri](https://tauri.app/distribute/sign/android/)
- **Riesgo emergente a vigilar (no bloqueante en 2026)**: Google está desplegando "Android Developer Verification" globalmente desde marzo de 2026; la aplicación forzosa del lado del usuario (bloquear instalación de apps de developers no verificados) arranca en septiembre de 2026 solo en Brasil/Indonesia/Singapur/Tailandia, expandiéndose globalmente en 2027. Google mantiene explícitamente una vía de sideload avanzada + ADB para power users incluso tras el despliegue. Para un solo dispositivo personal instalado vía ADB en 2026, esto NO bloquea — pero es una fecha a vigilar de cara a 2027. [Android developer verification rolling out — Android Developers Blog, mar-2026](https://android-developers.googleblog.com/2026/03/android-developer-verification-rolling-out-to-all-developers.html), [Android Authority timeline](https://www.androidauthority.com/android-sideloading-changes-timeline-3679204/)

### 5. Sync/IPC: cliente HTTP/WS al núcleo local

- Tauri v2 tiene un plugin HTTP oficial (`@tauri-apps/plugin-http`, wrapper de `reqwest` en Rust) con API compatible con `fetch`. Requiere configuración explícita de **capabilities/ACL** con patrones glob de scope por URL antes de poder hacer fetch — fricción de seguridad deliberada pero manejable (hay que declarar `127.0.0.1:7341` y/o el rango LAN/Tailscale explícitamente). [HTTP Client | Tauri](https://v2.tauri.app/plugin/http-client/), [Capability | Tauri](https://v2.tauri.app/reference/acl/capability/)
- WebSocket: es una Web API estándar del navegador — no encontré bloqueos específicos de Tauri para WS de eventos, ni en desktop ni en Android (funciona igual que en cualquier webview moderno).
- **Bug Android real y directamente relevante para el caso de uso** (hablar con el núcleo Atlas en LAN/Tailscale desde el móvil): *"El acceso a IPs de red local funciona bien en builds de release de Windows y Linux, pero en Android SOLO funciona en el entorno de desarrollo — el build de release no puede cargar páginas de otros dispositivos."* Esto es exactamente el escenario de "hablar con 127.0.0.1:7341 corriendo en el portátil, desde el móvil vía Tailscale" en un APK compilado para producción — hoy reportado como roto. [Discusión tauri-apps #10633](https://github.com/orgs/tauri-apps/discussions/10633)
- Adicionalmente, Android bloquea tráfico HTTP sin cifrar por defecto desde API 28 (Android 9) — hablar con `127.0.0.1:7341` o una IP LAN sin TLS exige opt-in explícito vía `usesCleartextTraffic`/`network_security_config.xml`, una pieza extra de configuración nativa Android que hay que mantener. [Network security configuration | Android Developers](https://developer.android.com/privacy-and-security/security-config)

**Conclusión**: el patrón HTTP+WS es viable en el desktop Linux, pero en Android hay un bug de red local documentado en release builds que ataca justo el corazón del caso de uso (sync con el núcleo vía LAN/Tailscale) — no es un detalle menor, es un bloqueador potencial a validar antes de comprometerse.

### 6. Riesgos

- **Fragmentación de webview real, no teórica**: WebView2/Chromium en Windows, WKWebView en macOS, webkit2gtk en Linux, Android System WebView (Chromium) + WKWebView en iOS para móvil — "cada bug surface es distinto, escribes una vez y pruebas tres veces" (cita de un análisis técnico). Un mantenedor de Tauri documentó públicamente su cambio de opinión sobre recomendar la plataforma en Linux por inestabilidad creciente release tras release. [Exploring System Webviews in Tauri - DEV](https://dev.to/shrsv/exploring-system-webviews-in-tauri-native-rendering-for-efficient-cross-platform-apps-9hl), [discusión #8524](https://github.com/orgs/tauri-apps/discussions/8524)
- **Madurez móvil**: soporte Android "más nuevo", con aristas activas en firmado, permisos y comportamiento de red (ver arriba) — no es el camino más transitado del ecosistema Tauri todavía.
- **Input latency**: no encontré benchmarks específicos publicados de latencia táctil de Tauri-en-Android; la literatura general de gaming móvil sitúa <40ms como aceptable para uso casual, pero no hay datos propios del framework — hueco de evidencia, no se puede afirmar ni descartar con datos duros.
- **CVE/mantenimiento upstream fuera de control de Tauri**: el bug de WebGL context-lost (#6559) lleva desde 2023 esperando arreglo upstream en WebKit — ilustra que ciertos problemas de fondo no dependen del equipo de Tauri y no tienen fecha.

---

## PARTE 2 — REACT NATIVE (barrido corto)

### 7. ¿Linux desktop de primera clase?

- Microsoft mantiene oficialmente **react-native-windows** (UWP/WPF) y **react-native-macos**. No existe un proyecto Linux mantenido por Microsoft o por Meta/el core de React Native. [React Native for Desktop | Microsoft Learn](https://learn.microsoft.com/en-us/windows/dev-environment/javascript/react-native-for-windows), [Out-of-Tree Platforms | React Native](https://reactnative.dev/docs/out-of-tree-platforms)
- La lista oficial de "out-of-tree platforms" cubre Windows, macOS, visionOS, tvOS y react-native-web/react-native-skia — Linux **no aparece** en esa lista curada.
- El único candidato encontrado para Linux desktop es `dmgctrl/react-native-linux`, un puerto vía Qt bifurcado de un proyecto antiguo de Canonical. Verificado directamente: **~12 estrellas, sin señales de actividad reciente** — un análisis directo del repo lo describe como *"experimental/abandonado... debería considerarse una prueba de concepto, no una plataforma estable y soportada."* [dmgctrl/react-native-linux](https://github.com/dmgctrl/react-native-linux)

**Veredicto**: React Native **NO tiene** Linux desktop de primera clase ni de facto viable en 2026. Esto **incumple directamente el requisito duro** del operador (Linux desktop + Android, un solo código) — no es un matiz, es una descalificación de entrada para el caso de uso de escritorio. React Native seguiría siendo una opción razonable *solo para Android*, pero el operador ya rechazó explícitamente tener dos bases de código o depender de soluciones no-Linux-first.

---

## TABLAS VEREDICTO

### Tauri v2

| Requisito | Veredicto | Evidencia (1 línea + URL) |
|---|---|---|
| R1 — Linux + Android primera clase | PASA-CON-MATIZ | Desktop maduro (~2 años, apps reales); Android funciona pero es la pata más joven, con bugs de red activos — [mayhemcode.com jul-2026](https://www.mayhemcode.com/2026/07/build-mobile-and-desktop-apps-from-one.html) |
| R2 — Cinematográfico real 60fps + shaders | PASA-CON-MATIZ | WebGL técnicamente posible, pero bug de "context lost" sin arreglo desde 2023 en el webview de escritorio y reporte de campo de 40fps (webkitgtk) vs 240fps (Chromium) en Linux — [Issue #6559](https://github.com/tauri-apps/tauri/issues/6559), [discusión #8524](https://github.com/orgs/tauri-apps/discussions/8524) |
| R3 — Un solo código | PASA | Un solo frontend TS/React compartido entre desktop y móvil vía el mismo proyecto Tauri — [Develop | Tauri](https://v2.tauri.app/develop/) |
| R4 — HTTP/WS al núcleo local | PASA-CON-MATIZ | HTTP plugin + ACL funcionan, pero acceso a IP de red local en Android release build está roto según reporte directo de la comunidad — [discusión #10633](https://github.com/orgs/tauri-apps/discussions/10633) |
| R5 — Sync multi-dispositivo | FALLA (hoy) | El mismo bug de R4 ataca justo el escenario LAN/Tailscale móvil↔portátil en producción, no solo en dev — [discusión #10633](https://github.com/orgs/tauri-apps/discussions/10633) |
| R6 — Build viable en portátil modesto, sin cuentas | PASA-CON-MATIZ | Sideload sin cuenta de Google es real (keystore propio); pero build de Rust+webkit2gtk es la operación cara que el proyecto ya señaló en ADR-059, con bug de memoria conocido en Linux que no libera RAM hasta cerrar — [Issue #10102](https://github.com/tauri-apps/tauri/issues/10102), [Android Code Signing | Tauri](https://tauri.app/distribute/sign/android/) |
| R7 (solo Tauri) — Honestidad webview: ¿puede no sentirse web? | PASA-CON-MATIZ | Scrollbar nativa no estilizable (requiere librería JS externa), selección/menú contextual hay que apagarlos a mano — es alcanzable pero no automático — [Discusión #8829](https://github.com/orgs/tauri-apps/discussions/8829) |

### React Native

| Requisito | Veredicto | Evidencia (1 línea + URL) |
|---|---|---|
| R1 — Linux + Android primera clase | **FALLA** | Sin Linux oficial (solo Windows/macOS de Microsoft); único puerto Linux (Qt) está abandonado (~12 estrellas, sin actividad) — [react-native-linux](https://github.com/dmgctrl/react-native-linux), [Out-of-Tree Platforms](https://reactnative.dev/docs/out-of-tree-platforms) |
| R2 — Cinematográfico real 60fps + shaders | PASA-CON-MATIZ | Motion nativo real vía Reanimated/Skia es fuerte en Android/iOS, pero es irrelevante si R1 ya falla para el requisito de escritorio |
| R3 — Un solo código | FALLA | Sin Linux de primera clase, "un solo código" para el par Linux+Android que pide el operador no se sostiene — mismo dato que R1 |
| R4 — HTTP/WS al núcleo local | PASA | fetch/WebSocket estándar disponibles en Android vía RN; no evaluado a fondo por quedar descalificado en R1/R3 |
| R5 — Sync multi-dispositivo | N/A | No evaluable de forma útil sin desktop Linux — el requisito completo ya cae en R1 |
| R6 — Build viable en portátil modesto, sin cuentas | N/A | No evaluado a fondo — descalificado antes de llegar a esta pregunta |

---

## Conclusión honesta

**Tauri v2** cumple el requisito duro de "una sola app dedicada" mejor que la alternativa evaluada aquí, y reutiliza el shell TS/React de 1.930 líneas ya cableado — ventaja real y concreta. Pero no es gratis: hay **dos hallazgos que deberían pesar en la decisión antes de comprometerse**:

1. Un mantenedor de Tauri se retractó públicamente de recomendar la plataforma para **Linux** citando inestabilidad creciente de webkit2gtk release tras release, con un caso documentado de 40fps vs 240fps frente a Chromium — esto es justo el escritorio que el operador usa a diario, y confirma la advertencia previa del proyecto (ADR-059) con datos de campo, no solo intuición.
2. El acceso a **red local (LAN/Tailscale) desde un build de release de Android** está reportado como roto en la comunidad — ataca directamente el escenario central de "el móvil habla con el núcleo Atlas corriendo en el portátil" que es la razón de ser de la app Android.

**React Native** queda descalificado en el primer filtro: no tiene Linux desktop de primera clase ni siquiera de facto — el único puerto existente está abandonado. No cumple la condición "un solo código" para el par de plataformas que pide el operador; sería, como mucho, una opción solo-Android, lo cual el operador ya excluyó al pedir explícitamente Linux+Android en un solo código.

Ninguno de los dos stacks investigados aquí sale con un PASA limpio en la pregunta central de rendimiento cinematográfico en Linux — el candidato con más peso de evidencia negativa concreta y reciente (2025-2026, con cita textual de un mantenedor del propio proyecto) es precisamente webkit2gtk en Linux dentro de Tauri.

---

### Nota metodológica

La herramienta de búsqueda web quedó temporalmente no disponible por un problema de infraestructura (clasificador de seguridad) durante una parte de la investigación, después de haber completado ~10 búsquedas y 2 fetches directos con resultados sustanciales y verificables (incluyendo las discusiones de GitHub más reveladoras: #8524, #10633, #6559, y el repo abandonado de react-native-linux). No se completaron búsquedas adicionales sobre benchmarks de Fabric/Reanimated en detalle ni sobre ejemplos adicionales de apps Tauri-Android en producción — estos son huecos de evidencia declarados arriba, no omisiones silenciosas.
