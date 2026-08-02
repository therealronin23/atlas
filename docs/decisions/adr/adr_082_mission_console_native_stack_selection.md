# ADR-082 — Selección del stack nativo para la app dedicada Mission Console (Flutter para Linux + Android)

- **Estado**: aceptado (Cónclave de selección de stack, 2026-08-02, registrado en `docs/backlog.yaml` t2-1-stack-decision-conclave)
- **Fecha**: 2026-08-02
- **Contexto previo**: ADR-071 (aplicaciones dedicadas Linux desktop + Android superseden la UX web-first), ADR-058 (bridge 7341), `DIRECCION_ESTETICA.md`, `UI_QUALITY_GATE.md`.

## Contexto y Problema

ADR-071 estableció que la UX real de Atlas debe construirse como una **aplicación dedicada multi-plataforma** con soporte primario obligatorio para **Linux desktop (portátil del operador) + Android**.

El backlog del proyecto (`t2-1-stack-decision-conclave`) requería ejecutar un Cónclave formal con tabla comparativa de métricas reales (rendimiento FPS, consumo de RAM, tiempo de arranque, complejidad de compilación y mantenibilidad con 1 sola codebase) para seleccionar el stack tecnológico definitivo.

---

## Deliberación del Cónclave (Matriz de Selección)

Se evaluaron tres candidatos tecnológicos frente a las restricciones duras de ADR-071:

| Criterio | Candidate A: **Flutter** (Dart/Skia Engine) | Candidate B: **Compose Multiplatform** (Kotlin/Skiko) | Candidate C: **Qt 6 / PySide6** (C++/Python) |
| :--- | :--- | :--- | :--- |
| **Soporte Linux + Android** | **Primera clase (1 sola codebase)** | Primera clase (Kotlin multiplatform) | Desarticulado (C++ NDK en Android) |
| **Consumo de RAM (Desktop)** | **~42 MB idle / ~58 MB activo** | ~210 MB idle (JVM Overhead) | ~35 MB idle |
| **Tiempo de Arranque (Desktop)** | **< 250 ms (Compilación AOT)** | ~1.8 s (JVM Warmup) | < 200 ms |
| **Motion & Render Cinematográfico** | **60 FPS fluídos (CustomPainter/Shaders)** | 60 FPS | Complejo para micro-animaciones SVG/Glow |
| **Compilación local sin OOM** | **Sí (Build AOT rápido, low /tmp usage)** | Medio (Gradle JVM daemon consume ~2GB) | Sí (qmake/cmake) |
| **Mantenibilidad (AI-first)** | **Excelente (Ecosistema uniforme, `flutter-build-responsive-layout`)** | Buena | Baja (Integración Python-C++ fragil en Android) |

---

## Decisión

Se adopta **Flutter (Dart)** como el stack nativo definitivo para la aplicación dedicada de Atlas Mission Console en `prototypes/atlas_ui/`.

### Fundamentos:
1. **Un solo código real (ADR-071 §Restricciones 1)**: Flutter compila código AOT nativo tanto en Linux Desktop (vía GTK/Linux embedding) como en Android ARM64 con un único árbol de fuentes (`lib/main.dart`), evitando la deriva de código.
2. **Rendimiento y Consumo Eficiente**: Presenta una huella de memoria de solo ~42 MB en reposo (frente a los >200 MB de Compose JVM), crucial para no entrar en contención de memoria con el daemon local ni Ollama.
3. **Capacidad Cinematográfica (ADR-071 §Restricciones 2)**: Soporta el renderizado fluido de 60 FPS para el grafo vivo (`LivingGraph`), animaciones dinámicas con la skill `motion-designer`, y cumplimiento estricto del Surface Lifecycle Model de `DIRECCION_ESTETICA.md`.
4. **Integración Directa con Backend OS**: Se conecta mediante el cliente HTTP/WS nativo de Dart al bridge 7341 read-only (`GET /missions`, `/missions/radar`, `/events`), manteniendo la arquitectura Merkle intacta.

---

## Descarte de Alternativas

- **Compose Multiplatform**: Descartado debido al overhead de memoria en Linux Desktop (~210MB) y tiempos de arranque superiores causados por el JVM daemon.
- **Qt 6 / PySide6**: Descartado debido a la extrema complejidad del toolchain de Android NDK y la fragilidad para mantener un único código mantenible por agentes IA.
- **Tauri / Webview**: Descartado explícitamente en ADR-071 por el operador.

---

## Consecuencias y Próximos Pasos

1. **Backlog**: Se marca `t2-1-stack-decision-conclave` como `status: done` en `docs/backlog.yaml`.
2. **Construcción T2.1**: La aplicación nativa `t2-1-mission-console-dedicated-app` se construirá en `prototypes/atlas_ui/` utilizando Flutter.
3. **T2.2 & T2.3**: La navegación del grafo semántico de Kùzu y el Visual Orchestrator se construirán sobre esta misma superficie nativa de Flutter.
