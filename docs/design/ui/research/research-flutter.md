# Dossier de investigación — Flutter como candidato para la UI cinematográfica de Atlas

Contexto evaluado: apps dedicadas (no web) Linux desktop + Android, un solo código, estética JARVIS (negro profundo, acento cian, grafos de nodos con glow, paneles glass, 60fps), cliente HTTP+WS contra `127.0.0.1:7341`, build en portátil modesto (16GB RAM, earlyoom mata procesos >7.5GB, /tmp tmpfs 4GB, GTX 960M).

Fecha de investigación: 2026-07-17. Fuentes 2025-2026 vía WebSearch/WebFetch, sin usar memoria del modelo salvo para interpretar resultados.

---

## 1. Linux desktop — ¿de primera clase en 2026?

Flutter cuenta Linux entre sus plataformas de primer nivel ("first-party support for web, desktop (Windows, macOS, Linux), and embedded"), pero el **motor de render en Linux hoy sigue siendo Skia por defecto, no Impeller**. El equipo tiene un backend Impeller-Vulkan para Linux en desarrollo activo, con el objetivo declarado de convertir Impeller en el motor único (unificado) en las seis plataformas durante 2026, pero a fecha de la investigación **Impeller en macOS/Windows/Linux "es capaz de correr, pero no está activado por defecto — hay que habilitarlo manualmente"** (docs.flutter.dev/perf/impeller, vía búsqueda). Esto es un estado experimental/opt-in en el escritorio Linux, no producción por defecto.

Evidencia de que el ecosistema Linux SÍ está vivo con Flutter en producción: **Canonical construyó App Center de Ubuntu (reemplazo de Ubuntu Software desde Ubuntu 23.10) enteramente en Flutter**, y ha publicado varios posts oficiales ("Canonical enables Linux desktop app support with Flutter", ubuntu.com/blog) sobre adoptarlo como stack de referencia para apps de escritorio del propio Ubuntu, incluyendo soporte experimental en RISC-V. Esto es la prueba más fuerte de "app Linux real de calidad" hecha con Flutter que se encontró.

Dato de adopción: "Desktop adoption reached 11.2% for Linux" (cifra citada en un resumen de "State of Flutter 2026", sin poder verificar la metodología original — tratar como señal débil, no como hecho duro).

Hay bugs de estabilidad reportados en 2025-2026 específicos de Linux (ver sección 9).

**Conclusión parcial:** Linux está soportado y tiene al menos un caso de uso de referencia serio (Canonical), pero el motor de render moderno (Impeller) todavía no es el default ahí — sigue en Skia, lo cual es relevante para el requisito de shaders/glow a 60fps consistente.

Fuentes:
- [Desktop support for Flutter](https://docs.flutter.dev/platform-integration/desktop)
- [Impeller rendering engine — docs.flutter.dev](https://docs.flutter.dev/perf/impeller)
- [Flutter's 2026 Roadmap Just Dropped](https://webartdesign.com.au/blog/flutters-2026-roadmap-just-dropped-and-its-all-about-finishing-the-job/)
- [GitHub PR #162684 — add ability to enable Impeller on windows/linux desktop](https://github.com/flutter/flutter/pull/162684)
- [GitHub - ubuntu/app-center](https://github.com/ubuntu/app-center)
- [Canonical enables Linux desktop app support with Flutter](https://canonical.com/blog/canonical-enables-linux-desktop-app-support-with-flutter)
- [Flutter and Ubuntu so far](https://ubuntu.com/blog/flutter-and-ubuntu-so-far)

---

## 2. Android — Impeller y rendimiento en gama media

Aquí el panorama es opuesto al de Linux: **Impeller es el motor por defecto en Android API 29+ desde Flutter 3.27**, y ya no se considera experimental en 2026. Reportes de comunidad citan "frame times decreased by 30–40% on mid-range Android devices" y un uso de memoria "~100MB menos que Skia". En pantallas de alto refresco, "Impeller consistently delivers 120 FPS" según los mismos resúmenes.

Matices honestos encontrados:
- Persisten "quirks" en algunos GPUs Adreno de gama media (se recomienda probar en hardware real, no solo emulador).
- Hay reportes de **degradación del cold start** al activar Impeller en algunos casos (issue "Impeller Slow Cold start issue" #175128 en el repo de Flutter).
- El punto fuerte de Impeller es eliminar el jank de compilación de shaders en caliente que afectaba a Skia — relevante directamente para el caso de uso (shaders de glow).

**Conclusión parcial:** Android es la plataforma donde Flutter/Impeller está más madura y probada en gama media; Linux va un paso por detrás.

Fuentes:
- [Impeller rendering engine](https://docs.flutter.dev/perf/impeller)
- [Impeller Slow Cold start issue #175128](https://github.com/flutter/flutter/issues/175128)
- [How Impeller Is Transforming Flutter UI Rendering in 2026 — DEV Community](https://dev.to/eira-wexford/how-impeller-is-transforming-flutter-ui-rendering-in-2026-3dpd)

---

## 3. Capacidad cinematográfica real: shaders, glow, partículas, tipografía

Flutter expone **`FragmentProgram`/`FragmentShader`** como API nativa de Dart (`dart:ui`), cargable con GLSL vía `FragmentProgram.fromAsset`, y usable directamente como `Paint.shader` en cualquier `Canvas` API — esto es exactamente el mecanismo pedido en la tarea (equivalente a AGSL/fragment programs). Documentación oficial: "Writing and using fragment shaders" en docs.flutter.dev.

Paquetes de soporte encontrados en pub.dev:
- **`flutter_shaders`**: utilidades sobre `FragmentProgram`, incluye personalización del efecto ink/inkwell con shader propio.
- **`shader_buffers`**: composición de shaders multi-capa al estilo ShaderToy (`ShaderBuffers` widget con `mainImage` + buffers), pensado justo para efectos tipo shader-art (glow, ruido, partículas) — mapea bien a "glow animado" pedido.
- **`shader_presets`**: colección de presets listos.

Ejemplos concretos de glow: se documentó una técnica de "radial falloff from a center point, multiplied by a color" que produce un efecto de glow convincente **sin pasadas de blur**, apta para 60fps.

Para partículas/orbes sin shaders (fallback más barato en CPU/GPU antigua): **`CustomPainter`** es la vía clásica — se encontraron ejemplos reales tipo "OrbPainter" (glow central + anillos de onda animados con trigonometría), y el paquete **`particle_field`** de gskinner ("A Flutter Widget for adding high performance custom particle effects to your UI", con `drawAtlas` para rendimiento) como librería ya empaquetada, no solo tutorial.

No se encontró un showcase específico "JARVIS UI hecho en Flutter" con nombre propio y URL verificable — la evidencia es indirecta (piezas sueltas: shaders, particle_field, CustomPainter demos) más que un caso de estudio único documentado. Esto es una laguna real de evidencia, no una negación de viabilidad: las piezas existen, pero no hay un ejemplo end-to-end "esto es un JARVIS-UI en Flutter en producción" que se haya podido verificar.

Tipografía: Flutter soporta **variable fonts** de forma nativa desde 2020 (v1.17.0) vía `FontVariation` (conforme a la spec OpenType), en todas las plataformas — cubre el requisito de "tipografía fina".

Fuentes:
- [Writing and using fragment shaders — docs.flutter.dev](https://docs.flutter.dev/ui/design/graphics/fragment-shaders)
- [flutter_shaders | Flutter package](https://pub.dev/packages/flutter_shaders)
- [shader_buffers | Flutter package](https://pub.dev/packages/shader_buffers)
- [GitHub - monster555/flutter_shader_demo](https://github.com/monster555/flutter_shader_demo)
- [GitHub - gskinner/particle_field](https://github.com/gskinner/particle_field)
- [Flutter Magic: Build Your Own Particle System — Medium](https://medium.com/easy-flutter/flutter-magic-build-your-own-particle-system-and-look-like-a-wizard-b1fa55b75c85)
- [Flutter's fonts and typography — docs.flutter.dev](https://docs.flutter.dev/ui/design/text/typography)
- [FontVariation class — Dart API](https://api.flutter.dev/flutter/dart-ui/FontVariation-class.html)

---

## 4. Grafos de nodos interactivos

Existen varios paquetes maduros en pub.dev, ninguno es "el" estándar de-facto pero hay elección real:

- **`graphview`** (nabil6391/graphview en GitHub): layouts Tree, Directed, Layered, Balloon, Circular, Radial, Tidy Tree, Mindmap; navegación interactiva (jump-to-node, zoom-to-fit, auto-centrado), animaciones de expand/collapse, pan/zoom/tap. Requiere combinarse con `InteractiveViewer` como motor de zoom. Demo en vivo: graphview.surge.sh.
- **`flutter_graph_view`**: widgets para "force-oriented diagrams" (grafo de fuerzas, más parecido a lo que se pediría para un grafo de nodos vivo con física).
- **`graph_builder`**: widget customizable para grafos acíclicos (árboles de skills, organigramas, dependencias).
- **`advanced_graphview`**: Tree/Graph/Topology UI de configuración simple.

Ninguno de estos es shader-driven por defecto (son Canvas/CustomPainter estándar), así que el "glow animado" sobre los nodos habría que capa-encimarlo a mano con `CustomPainter` o fragment shaders — trabajo de integración real, no llave en mano.

Fuentes:
- [graphview | Flutter package](https://pub.dev/packages/graphview)
- [GitHub - nabil6391/graphview](https://github.com/nabil6391/graphview)
- [flutter_graph_view | Flutter package](https://pub.dev/packages/flutter_graph_view)
- [graph_builder | Flutter package](https://pub.dev/packages/graph_builder)

---

## 5. Cliente HTTP + WebSocket

`web_socket_channel` es el paquete oficial/estándar (mantenido por el equipo Dart), en versión `^2.3.0` a fecha de las guías 2025 revisadas. Provee `WebSocketChannel` con stream de escucha + sink de envío; se documenta como apto para "chat apps, live dashboards, or multiplayer games" — encaja con el caso de uso (eventos del bus de Atlas por WS). Para HTTP simple, el paquete `http` (también oficial) es la vía estándar y no arrojó ninguna señal de inmadurez en la búsqueda.

Matiz: la implementación "cruda" del canal no trae reconexión automática ni backoff — hay que construirlo (patrón bien documentado en varias guías 2025), no es gratis pero tampoco es un vacío de librería.

Fuentes:
- [Communicate with WebSockets — docs.flutter.dev](https://docs.flutter.dev/cookbook/networking/web-sockets)
- [Building a Scalable WebSocket Client in Flutter — Medium](https://medium.com/@birhos/building-a-scalable-websocket-client-in-flutter-f7a78c4166c5)
- [Top Flutter Websocket, RPC, gRPC packages — Flutter Gems](https://fluttergems.dev/websocket/)

---

## 6. Coste de build en un portátil modesto (16GB RAM, earlyoom, /tmp 4GB, GTX 960M)

**Disco/RAM del SDK:**
- Flutter SDK solo: ~1.6-2.8GB en disco.
- Setup completo realista (Android SDK + imágenes de emulador + IDE): **10GB o más** de espacio libre recomendado.
- RAM: no hay piso oficial duro documentado, pero el consenso de comunidad sitúa el mínimo práctico en 8GB, con **16GB "fuertemente recomendado"** cuando se corre emulador Android + IDE simultáneamente. El portátil del operador está justo en el límite recomendado, no por encima.

**Riesgo de OOM real durante build (relevante directamente para earlyoom):**
- El proceso `gen_snapshot` (compilador AOT de Dart a código nativo, se invoca en build de release tanto para Android como para el binario Linux) es conocido por picos de RAM altos; hay un issue histórico de Flutter documentando fallos "Out of memory" durante el snapshot generation incluso en sistemas con 8GB de RAM.
- Esto es una coincidencia directa con el patrón que ya mató procesos en esta máquina (earlyoom matando >7.5GB) — el build de **release** (no el hot-reload de debug) es el momento de mayor riesgo, no el desarrollo día a día.
- No se encontró un benchmark de tiempo de build (`flutter build linux --release` / `flutter build apk --release`) en minutos verificado con fuente citable — laguna de evidencia. Lo que sí es estructural: el build Linux release NO recompila el motor C++ (usa artefactos de engine precompilados descargados), solo compila el snapshot Dart AOT + wrapper CMake/Ninja — más ligero que Android. El build Android release pasa además por Gradle + R8/proguard + gen_snapshot por ABI, que es la ruta más pesada en RAM.

**¿Se puede compilar todo sin cuenta de nadie?** SÍ, con evidencia: no se requiere cuenta de Google para compilar. Lo que sí se necesita es un keystore de firma para el APK — se puede generar uno local con `keytool -genkeypair` (dummy/test), sin ninguna cuenta externa. Y es factible un flujo completamente offline (SDK descargado y cacheado localmente, `.pub-cache`/`.gradle`/`.android` portados, `--offline` en gradle) una vez completada la descarga inicial de dependencias.

Fuentes:
- [System Requirements for Flutter — Syncfusion](https://help.syncfusion.com/flutter/system-requirements)
- [Your Essential Guide to Flutter SDK Download and Installation for 2026](https://codematrixlab.com/flutter-sdk-download/)
- [GitHub issue #25657 — Out of memory error while running flutter build apk](https://github.com/flutter/flutter/issues/25657)
- [Setting Up Flutter Project Without Internet Access — Medium](https://medium.com/@divyanshverma9460/setting-up-flutter-project-without-internet-access-060755c8a10a)
- [The Flutter Release Gauntlet — DEV Community](https://dev.to/kenryikegbo/the-flutter-release-gauntlet-how-to-build-your-first-android-apk-without-the-headache-4c06)

---

## 7. Empaquetado Linux

Flutter soporta explícitamente **AppImage, deb, pacman, rpm y Flatpak** (incluye tooling de manifest para build offline de Flatpak y publicación en Flathub). El binario final vive en `build/linux/x64/<mode>/bundle/` y es un binario **estáticamente enlazado**. La vía "oficial" recomendada por Google es Snap, pero eso no impide los otros formatos.

Dato de tamaño real citado: un AppImage empaquetado de ejemplo pesó **~225MB** — grande para un asistente de escritorio, coherente con que Flutter embebe su propio motor de render + runtime Dart en cada binario (no comparte runtime del sistema como GTK nativo).

No se encontró dato verificado sobre tiempo de arranque en frío del binario Linux — laguna de evidencia (se sabe que en Android hay reportes de degradación de cold-start con Impeller; no hay equivalente confirmado para Linux en la búsqueda).

Fuentes:
- [Build and release a Linux app to the Snap Store — docs.flutter.dev](https://docs.flutter.dev/deployment/linux)
- [Build Linux apps with Flutter — docs.flutter.dev](https://docs.flutter.dev/platform-integration/linux/building)
- [Packaging Flutter Desktop Apps for Linux — The Complete Guide — Medium](https://medium.com/fludev/packaging-flutter-desktop-apps-for-linux-the-complete-guide-0588a0ac9f82)
- [Package Flutter Linux App Into AppImage Part 2 — DEV Community](https://dev.to/hosamhasan/package-flutter-linux-app-into-appimage-part-2-1c5o)

---

## 8. Mantenibilidad por agentes IA (generación de Dart)

Hay evidencia concreta y reciente de que el ecosistema está optimizando activamente para agentes de código:
- Existe un repo dedicado **`flutter-llm-toolkit`** ("Flutter/Dart agents, skills, patterns, and references for Claude Code") en GitHub — señal de que la comunidad ya está construyendo tooling específico para que Claude Code opere sobre proyectos Flutter.
- Guías 2026 de freeCodeCamp y otros argumentan que "Dart's strong typing and Flutter's predictable widget patterns make it one of the most Claude-code-friendly frameworks", con el analyzer de Dart dando feedback de compilación inmediato que permite auto-corrección, y hot-reload para verificación visual rápida en el loop del agente.
- Google + el equipo de Android Studio anunciaron integración de **Gemini de primera clase para Dart y Flutter** en Google I/O 2025 — inversión oficial en asistencia IA sobre este stack, no solo esfuerzo de terceros.

Nota de sesgo: estas fuentes son en gran parte contenido de marketing/blogs orientados a vender servicios de desarrollo con IA (cifras de ROI del tipo "10-15x" deben tratarse con escepticismo), pero la señal estructural (tipado fuerte + analyzer + hot reload = loop de auto-corrección rápido para un agente) es un argumento técnico razonable independientemente del marketing.

Fuentes:
- [GitHub - rolandtolnay/flutter-llm-toolkit](https://github.com/rolandtolnay/flutter-llm-toolkit)
- [How to Use Claude Code to Build Flutter Apps Faster — freeCodeCamp](https://www.freecodecamp.org/news/how-to-use-claude-code-to-build-flutter-apps-faster-best-practices/)
- [Dart & Flutter momentum at Google I/O 2025 — Flutter blog](https://blog.flutter.dev/dart-flutter-momentum-at-google-i-o-2025-4863aa4f84a4)

---

## 9. Riesgos honestos

**Tamaño de runtime:** cada binario embebe su propio motor de render + runtime Dart (no hay runtime compartido del sistema); el ejemplo de AppImage de ~225MB lo confirma. Esto es notablemente más pesado que una app GTK/Qt nativa equivalente.

**Jank/estabilidad conocida en Linux desktop 2025-2026 (issues abiertos reales, no genéricos):**
- Issue #155083: crash al minimizar/maximizar la ventana en Flutter Linux.
- Issue #170937: ventana en blanco en Ubuntu 22.04.5 con servidor X11.
- Issue #169470: app se congela/crashea al arrancar sobre X11.
- Estos son issues de **estabilidad de ventana**, no solo de rendimiento de dibujo — relevante porque una UI "cinematográfica" que crashea al redimensionar es un problema de producto, no cosmético.

**GPU antigua (directamente relevante — GTX 960M es Maxwell, ~2015):** issue #181441 documenta que un usuario con una GPU Nvidia igual de vieja (GT 710) sufre **artefactos gráficos severos con Impeller** y depende del flag `--no-enable-impeller`, flag que Flutter ha marcado como "va a desaparecer en una próxima versión" — es decir, el camino de salida para hardware antiguo se está cerrando activamente. Como en Linux Impeller todavía no es default (sección 1), esto pega más fuerte a futuro que hoy, pero es una bandera roja real para una GTX 960M.

**Dependencia de Google:** Google recortó ~200 puestos de los equipos de Flutter/Dart/Python en abril-mayo de 2024 (antes de I/O ese año) — no es un rumor sin fuente, hubo cobertura amplia (TechCrunch, InfoWorld). Desde entonces el equipo restante ha seguido publicando roadmap activo (I/O 2025 y 2026 con anuncios de Impeller 2.0/unificación de motor), así que el proyecto no está abandonado, pero el precedente de recorte real ante presión de costes en Google es un hecho verificado, no una hipótesis.

**Laguna de evidencia honesta:** no se encontró ningún ejemplo end-to-end verificable de una UI "tipo JARVIS/sci-fi" completa construida en Flutter y documentada como caso de estudio — la viabilidad se apoya en piezas técnicas sueltas (shaders, particle_field, graphview) que sí existen y funcionan por separado, pero integrarlas en la estética pedida es trabajo de construcción real, no un template disponible.

Fuentes:
- [GitHub issue #155083 — crash on Linux window resize](https://github.com/flutter/flutter/issues/155083)
- [GitHub issue #170937 — Linux desktop window is blank](https://github.com/flutter/flutter/issues/170937)
- [GitHub issue #169470 — app freezes/crashes on startup (X11)](https://github.com/flutter/flutter/issues/169470)
- [GitHub issue #181441 — Impeller opt-out removal, old GPU artifacts](https://github.com/flutter/flutter/issues/181441)
- [Google lays off staff from Flutter, Dart and Python teams — TechCrunch](https://techcrunch.com/2024/05/01/google-lays-off-staff-from-flutter-dart-python-weeks-before-its-developer-conference/)
- [Is Flutter Dead in 2025? — Flexxited](https://flexxited.com/blog/is-flutter-dead-in-2025-googles-roadmap-and-app-development-impact)

---

## Tabla VEREDICTO

| Requisito | Veredicto | Evidencia (1 línea) |
|---|---|---|
| **R1** — Linux + Android de primera clase | **PASA-CON-MATIZ** | Android tiene Impeller como default y maduro; Linux es soportado (Canonical/App Center lo prueba) pero Impeller ahí sigue opt-in, no default, en 2026. |
| **R2** — Cinematográfico real, 60fps + shaders | **PASA-CON-MATIZ** | `FragmentProgram`/`flutter_shaders`/`shader_buffers`/`CustomPainter`/`particle_field` existen y son reales, pero no hay caso de estudio JARVIS-completo verificado, y GPU vieja tipo GTX 960M ya reporta artefactos con Impeller (issue #181441). |
| **R3** — Un solo código, apps dedicadas | **PASA** | Es la propuesta de valor central de Flutter: mismo código Dart compila a binario Linux nativo y APK Android nativo, sin WebView de por medio. |
| **R4** — HTTP/WS al núcleo local | **PASA** | `http` y `web_socket_channel` son paquetes oficiales, maduros, documentados para casos de dashboards en vivo — encaja directo con 127.0.0.1:7341. |
| **R5** — Sync multi-dispositivo vía WS | **PASA-CON-MATIZ** | El canal WS base es sólido, pero reconexión/backoff/estado compartido entre Linux y Android hay que construirlos a mano — no viene resuelto de fábrica. |
| **R6** — Build viable en portátil modesto sin cuentas | **PASA-CON-MATIZ** | No requiere ninguna cuenta (Google/otra) para compilar y sí es 100% offline-capable tras la descarga inicial, pero el build release usa `gen_snapshot`, con historial documentado de fallos OOM incluso en máquinas de 8GB — riesgo real y directo de repetir el patrón earlyoom en 16GB si hay build+editor+Ollama concurrentes. |

**Lectura honesta global:** Flutter cumple con solidez el requisito arquitectónico (un solo código, HTTP/WS maduro, cero cuentas) y tiene las piezas técnicas de bajo nivel para el look cinematográfico (shaders reales, no un hack). Los dos puntos débiles genuinos son (a) Linux desktop va un escalón por detrás de Android en madurez de motor de render — Impeller no es default ahí todavía — y (b) el propio hardware objetivo (GTX 960M) coincide con el perfil de GPU que ya reporta problemas serios con Impeller, justo cuando Flutter está retirando la vía de escape (`--no-enable-impeller`). No es un descarte, pero cualquier decisión debería asumir que el escritorio Linux con esta GPU concreta es la superficie de mayor riesgo técnico del stack, no un detalle menor.
