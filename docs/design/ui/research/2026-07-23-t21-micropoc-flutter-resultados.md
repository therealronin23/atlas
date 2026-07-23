---
title: "T2.1 micro-PoC Flutter — resultados de medición (tramo Linux desktop)"
status: vigente
date: 2026-07-23
---

# Resultados del micro-PoC Flutter (t2-1-micropoc-flutter)

Cierra el tramo Linux desktop del ítem de backlog `t2-1-micropoc-flutter`
(prioridad 1, ADR-071 + `DECISION_STACK_T21.md`). El tramo móvil (Android)
queda explícitamente **diferido**: el operador no tenía el dispositivo a
mano en esta sesión — ver decisión abajo. Este ítem NO se marca `done` en
`docs/backlog.yaml`.

Proyecto: `prototypes/atlas_ui/flutter_micropoc/` (nuevo, creado en esta
sesión, nada reaprovechado — no existía previamente).

## Qué se midió y cómo

Pantalla única (`lib/main.dart` + `shaders/glow.frag`): shader GLSL de glow
(`dart:ui` `FragmentProgram`, dos anillos concéntricos pulsantes tras el
benchmark de sucesión — ver abajo), 24 partículas orbitando vía
`CustomPainter` (patrón "OrbPainter" de `research-flutter.md`), contador de
fps por media móvil de 1s, y cliente WebSocket real contra
`ws://127.0.0.1:7341/events` (bridge ADR-058, arrancado con
`.venv/bin/atlas os-bridge`). Sin capturar el display real en ningún
momento (evita tocar la política de GUI-automation de Atlas, que es para
las acciones del propio Atlas, no para diagnóstico manual de desarrollo):
las métricas se leyeron de `/proc/<pid>/status` (RSS), `/usr/bin/time -v`
(build), y un log periódico a stdout (`MICROPOC_STATS`) que la propia app
imprime — no de una captura de pantalla.

## Dos hallazgos reales corregidos antes de poder medir nada

Ambos son hallazgos honestos del propio proceso de medición, no ruido —
documentados porque son releventes para cualquier futuro cliente nativo
(incluido el Android diferido):

1. **Shader GLSL no compilaba**: `FlutterFragCoord()` no existe sin
   `#include <flutter/runtime_effect.glsl>` al principio del `.frag` — el
   compilador de shaders de Flutter (`impellerc`) da un error confuso
   ("no matching overloaded function" + "vector swizzle selection out of
   range") en vez de decir claramente "falta el include". Corregido
   añadiendo el include.
2. **WebSocket rechazado con HTTP 403**: `src/atlas/api/server.py:
   _validate_websocket_origin` exige un header `Origin` que case con el
   `Host` (protección tipo CSRF, ADR-058) — ni el cliente Dart
   (`WebSocketChannel.connect` genérico) ni un cliente Python de prueba
   (`websockets`) lo envían por defecto, porque `Origin` es un concepto de
   navegador, no de cliente nativo. Corregido usando
   `IOWebSocketChannel.connect(uri, headers: {'Origin':
   'http://127.0.0.1:7341'})` — API específica de `dart:io`, no disponible
   en la fachada cross-platform genérica del paquete. **Implicación real
   para T2.1**: cualquier stack (Flutter, Compose, Qt) que conecte un
   cliente nativo al bridge necesitará este mismo ajuste — no es un
   problema de Flutter, es un requisito de integración del propio bridge
   que ningún dossier anterior había verificado en la práctica.

## Métricas medidas (GTX 960M, Linux, esta máquina)

| Métrica | Valor real medido | Veredicto |
|---|---|---|
| Build release limpio (`flutter build linux --release`) | 29.49s, CPU 131% | — (sin umbral de referencia, dato informativo) |
| Pico de RAM durante el build | RSS máx. proceso `flutter`: ~509MB (521400 KB) | **PASA** frente al techo earlyoom 7.5GB/proceso — con matiz: solo mide el proceso driver `flutter`, no el agregado simultáneo de sus subprocesos hijos (dart/cmake/ninja/clang); no se instrumentó memoria de sistema completa durante el build |
| Arranque en frío (proceso lanzado → primer paint + stats confirmados) | ~1.3s | **PASA** (cualitativo, sin umbral de referencia previo en el repo) |
| fps en régimen estable | 58-61fps (motor Skia por defecto en Linux — Impeller no está activo, consistente con `research-flutter.md` §1) | **PASA** contra el target de 60fps de `DECISION_STACK_T21.md` |
| Estabilidad ante resize de ventana | Sin crash, fps se mantiene tras 2 resizes (`wmctrl`) | **PASA-CON-MATIZ** — mitiga la preocupación de los issues #155083/#170937/#169470 citados en `research-flutter.md`, pero es una prueba puntual, no un fuzzing de ventana |
| WS vivo contra 127.0.0.1:7341/events | Conecta tras el fix de Origin; recibe los 23 eventos históricos reales (`event_store.tail(50)`) al conectar | **PASA-CON-MATIZ** — funciona, pero solo tras un fix de integración no trivial y no documentado previamente (ver hallazgo #2 arriba) |
| RAM en ejecución (steady state) | ~149MB RSS | **PASA** (ligero) |
| Artefactos gráficos de GPU vieja (riesgo issue #181441) | Ninguno observado | **No aplica todavía**: Impeller no está activo por defecto en Linux (Skia sí), así que este micro-PoC no ejercitó la ruta de riesgo real citada en `research-flutter.md` §9. Dato pendiente si en el futuro se prueba con `--enable-impeller` explícito. |

## Benchmark de sucesión (Cónclave 2026-07-17, punto 2 del veredicto)

**PASA.** Un subagente Sonnet completamente independiente (sin contexto de
esta sesión, sin ayuda ni pistas de cómo resolverlo) recibió la tarea de
modificar `shaders/glow.frag` para tener dos anillos de glow concéntricos
con fases distintas, verificando con `flutter analyze` + `flutter build
linux --release` reales.

- **1 sola iteración** hasta compilar limpio — ni un error de shader, ni de
  Dart.
- **Sin consultar documentación externa** (ni WebSearch ni WebFetch): le
  bastó leer `glow.frag` y `main.dart` para entender el contrato de
  uniforms (`uSize`→índices 0/1, `uTime`→índice 2) y extenderlo sin tocar
  `main.dart`.
- Verificado independientemente (no solo el reporte del subagente): `flutter
  analyze` limpio y `flutter build linux --release` exitoso confirmados por
  mí tras el cambio.
- Contraste honesto: el "loop de autocorrección rápido para un agente" que
  argumenta `research-flutter.md` §8 (tipado fuerte + analyzer + hot reload)
  se sostuvo en la práctica — pero solo DESPUÉS de que un humano/sesión
  previa arreglara el bug real del include (`FlutterFragCoord`); un agente
  sin ese fix previo habría tenido que descubrir el mismo error confuso del
  compilador de shaders. No se probó ese caso (partir de un shader roto)
  porque no era el objetivo del benchmark.

## Lectura honesta global (tramo Linux desktop)

Ningún criterio medido dio **FALLA**. Flutter cumple el target de 60fps en
esta GPU concreta (Maxwell, GTX 960M) usando el motor por defecto (Skia,
no Impeller) sin artefactos ni crashes. El build y el runtime son ligeros
en RAM, muy por debajo del techo earlyoom. El benchmark de sucesión —la
métrica que más preocupaba al operador según memoria
`succession-proofing-priority-2026-07-15`— pasó limpio a la primera.

Los dos matices reales (RAM del build no agregada, WS requiriendo un fix
de integración) no son descalificantes, pero SÍ son trabajo real que
cualquier stack ganador tendrá que replicar — el segundo en particular es
un hallazgo nuevo sobre el propio bridge de Atlas, no sobre Flutter, y
aplica igual a Compose o Qt cuando se midan.

## Pendiente explícito (NO cerrado)

- **Tramo móvil (Android)**: el operador no tenía el dispositivo a mano en
  esta sesión (decisión explícita, ver `AskUserQuestion` de esta misma
  sesión). `flutter devices` no detecta ningún Android conectado ahora
  mismo; `adb` no está en el PATH del shell. Falta: conectar el dispositivo
  (USB debugging o wireless adb, a decidir con el operador — no hay
  protocolo previo documentado en el repo), `flutter build apk --release`,
  medir fps/RAM/APK size en el móvil real, y repetir el benchmark de
  sucesión sobre el flujo Android si aplica.
- **Impeller explícito**: no se probó `--enable-impeller` en Linux (fuera
  de alcance de esta medición, Skia es el default y el que se midió).
- **UI_QUALITY_GATE.md**: confirmado fuera de alcance para este micro-PoC
  (es para el prototipo/producto final de ~20 pantallas, no para
  benchmarking técnico de una pantalla — ver investigación previa a esta
  sesión).
- Compose y Qt (P2/P3) siguen sin medir — ítems de backlog separados
  (`t2-1-micropoc-compose`, Qt no visto en el grep previo pero referenciado
  en `DECISION_STACK_T21.md`).
