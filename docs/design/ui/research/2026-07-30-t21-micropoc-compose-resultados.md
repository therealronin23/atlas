---
title: "T2.1 micro-PoC Compose Multiplatform — resultados de medición (tramo Linux desktop)"
status: vigente
date: 2026-07-30
---

# Resultados del micro-PoC Compose Multiplatform (t2-1-micropoc-compose)

Cierra el tramo Linux desktop del ítem de backlog `t2-1-micropoc-compose`
(prioridad 1, ADR-071 + `DECISION_STACK_T21.md`). El tramo móvil (Android)
queda explícitamente **excluido del alcance** por pedido directo del
operador (independiente de este micro-PoC, no diferido por falta de
dispositivo como en el caso de Flutter) — este ítem NO se marca `done` en
`docs/backlog.yaml`.

Proyecto: `prototypes/atlas_ui/compose_micropoc/` (nuevo, creado en esta
sesión, nada reaprovechado — no existía previamente ningún proyecto
Compose en el repo). Medido en la GTX 960M real (`prime-select nvidia`,
sin PRIME offload — ver hallazgo permanente en el informe de Flutter del
mismo día sobre por qué offload en modo `on-demand` no es viable con
apps GTK3/JVM en esta máquina).

## Qué se midió y cómo

Pantalla única (`src/main/kotlin/Main.kt`): shader SkSL de glow (Skia
`RuntimeEffect`, dos anillos concéntricos pulsantes — ampliado a tres
durante el benchmark de sucesión, ver abajo), 24 partículas orbitando vía
`Canvas` + `drawCircle`, contador de fps por media móvil de 1s
(`withFrameNanos`), y cliente WebSocket real (Ktor `HttpClient` + CIO)
contra `ws://127.0.0.1:7341/events` (bridge ADR-058). Métricas leídas de
`/proc/<pid>/status` (RSS), `/usr/bin/time -v` (build, con `--no-daemon`
para medir el proceso real y no el daemon persistente de Gradle — ver
nota metodológica abajo), y el mismo formato de log `MICROPOC_STATS` a
stdout que usa Flutter, para comparación directa sin parsear dos
formatos distintos.

## Nota metodológica: por qué `--no-daemon`

Gradle usa un daemon persistente por defecto; medir `time -v` sobre
`./gradlew` sin más solo captura el proceso cliente delgado que habla con
el daemon (dio un pico de RSS de ~96MB, un número falso — el daemon real
hace todo el trabajo pesado fuera de la vista de `time`). Repetido con
`--no-daemon` para forzar un único proceso JVM que compila todo
en-proceso, igual que el binario `flutter` (que no tiene daemon) — el
número resultante es el comparable de verdad.

## Setup de toolchain (bloqueante resuelto en esta sesión)

Ni Gradle standalone ni wrapper existían en el repo (Kotlin CLI sí, vía
SDKMAN). Instalado Gradle 8.11.1 vía SDKMAN (espacio de usuario, sin
`sudo`, sin tocar el sistema) — acción "regular", no de sistema. Kotlin
2.3.21 (ya presente) + Compose Multiplatform Gradle plugin 1.11.1 (última
estable en Maven Central, verificado — 1.12.0 solo tiene betas a fecha de
hoy) son compatibles según la matriz oficial de JetBrains (mínimo 2.1.0,
recomendado 2.2.20+). `gradle.properties` capa el heap explícitamente
(`-Xmx2g` JVM del build, `-Xmx1536m` Kotlin daemon, sin paralelismo) tal
como exige la aceptación del ítem de backlog, contra el techo earlyoom de
esta máquina (7.5GB/proceso).

## Métricas medidas (GTX 960M real, Linux, esta máquina)

| Métrica | Valor real medido | Veredicto |
|---|---|---|
| Build release limpio (`./gradlew createReleaseDistributable --no-daemon`) | 1m 29.8s, CPU 332% | — (sin umbral de referencia, dato informativo) |
| Pico de RAM durante el build | RSS máx. proceso único (sin daemon): ~1.37GB (1 403 636 KB) | **PASA** frente al techo earlyoom 7.5GB/proceso, con margen amplio (~18% del techo) — con matiz: no se instrumentó el escenario "con Android Studio/IDE abierto en paralelo" que citaba `research-kmp-qt-slint.md` como riesgo concreto |
| Arranque en frío (proceso lanzado → primer paint + stats confirmados) | ~8.1s | **FALLA-CON-MATIZ** frente al arranque de Flutter (~1.3-1.5s) — más de 5x más lento; esperado y ya anticipado por `research-kmp-qt-slint.md` §A5 ("el arranque en frío incluye el coste de arrancar la JVM"), pero es una desventaja real y medida, no solo teórica |
| fps en régimen estable | 53-61fps (motor Skia/Skiko, mayoría 59-61) | **PASA** contra el target de 60fps de `DECISION_STACK_T21.md` — mismo rango que Flutter |
| Estabilidad ante resize de ventana | Sin crash, fps se mantiene tras 2 resizes (`wmctrl`) | **PASA-CON-MATIZ** — misma prueba puntual que Flutter, no fuzzing de ventana |
| WS vivo contra 127.0.0.1:7341/events | Conecta con header `Origin` explícito (mismo requisito que Flutter, confirmado transversal); recibe los 23 eventos históricos reales al conectar | **PASA** — sin fricción de integración nueva, el hallazgo de Flutter sobre el header `Origin` ya cubría este caso |
| RAM en ejecución (steady state) | ~282MB RSS | **PASA-CON-MATIZ** — cumple, pero es ~1.9x más pesado que Flutter (~149MB) |
| GPU confirmada por evidencia externa | `nvidia-smi` muestra el proceso `compose_micropoc` con memoria asignada en la GTX 960M (5MiB) durante la ejecución | **Verificado directamente**, no inferido |

## Benchmark de sucesión (Cónclave 2026-07-17, punto 2 del veredicto)

**PASA.** Un subagente Sonnet completamente independiente (sin contexto de
esta sesión, sin ayuda ni pistas de cómo resolverlo) recibió la tarea de
añadir un tercer anillo de glow concéntrico al shader SkSL existente, con
fase/frecuencia y color distintos, fusionado de forma coherente con los
otros dos (no como capas desconectadas).

- **1 sola iteración** hasta compilar limpio (`./gradlew compileKotlin`).
- **Sin consultar documentación externa** (ni WebSearch ni WebFetch,
  instrucción explícita respetada): le bastó leer `Main.kt` completo
  (202 líneas) para entender el contrato de uniforms (`uSize`/`uTime` vía
  `packUniforms`) y el patrón de color existente (`cyan * alpha`),
  extendiéndolo a una mezcla ponderada por anillo sin tocar layout, WS,
  fps ni partículas.
- **Hallazgo honesto del propio subagente, no mío**: ni `compileKotlin`
  ni `createReleaseDistributable` ejecutan realmente el string SkSL — el
  shader se compila dentro de Skia solo al invocarse `makeShader(...)` en
  tiempo de ejecución, así que un error de sintaxis SkSL real (paréntesis
  mal cerrado, tipo incorrecto) no lo habría detectado ninguno de los dos
  comandos de verificación disponibles, solo lanzar la app. El propio
  subagente lo señaló sin que se le preguntara — comparó dos veces contra
  el patrón de `ring1`/`ring2` antes de escribir por esa misma razón.
- **Verificado independientemente por mí** (no solo el reporte del
  subagente, ni solo los dos comandos que el subagente pudo ejecutar):
  lancé la app real (`./gradlew run`) tras el cambio y confirmé en vivo
  `MICROPOC_STATS fps=33 shader=ok` — el shader de tres anillos SÍ compila
  y corre en Skia real, no solo en Kotlin. Reconstruido después el release
  completo (`createReleaseDistributable`) de forma independiente, exit 0.
- Contraste honesto con el benchmark de Flutter: en Flutter, el error de
  shader mal formado (`FlutterFragCoord()` sin include) SÍ lo detectaba
  el propio `flutter build` con un mensaje confuso pero real; en Compose,
  el equivalente (SkSL roto) habría pasado ambos comandos de build sin
  avisar — es una diferencia real de robustez del toolchain a favor de
  Flutter, no un artefacto de cómo se hizo la prueba.

## Lectura honesta global (tramo Linux desktop)

Ningún criterio dio **FALLA** dura salvo el arranque en frío (que es
**FALLA-CON-MATIZ**, no descalificante para un panel tipo dashboard que
se deja abierto, según el propio `research-kmp-qt-slint.md` §A5, pero sí
una desventaja real frente a Flutter si el operador quiere algo que se
sienta instantáneo). Compose cumple el target de 60fps en esta GPU
concreta con el mismo rango que Flutter, el build es más lento y más
pesado en RAM (~3x el tiempo, ~2.7x el pico de RAM de build) pero se
mantiene muy por debajo del techo earlyoom. El benchmark de sucesión pasó
limpio a la primera, igual que Flutter — pero reveló una diferencia real
de robustez del toolchain (errores de shader no detectables en build,
solo en runtime) que no tiene Flutter.

**Comparación directa con Flutter (mismos criterios, misma máquina, mismo día):**

| Criterio | Flutter | Compose |
|---|---|---|
| Build release limpio | 31.58s / ~550MB RSS | 89.8s / ~1.37GB RSS |
| Arranque en frío | ~1.5s | ~8.1s |
| fps estable | 53-61 (mayoría 59-61) | 53-61 (mayoría 59-61) |
| RAM ejecución (steady) | ~186MB | ~282MB |
| WS + Origin header | requiere el mismo fix, ya aplicado | requiere el mismo fix, ya aplicado |
| Benchmark de sucesión | PASA, 1 iteración, build detecta errores de shader | PASA, 1 iteración, build NO detecta errores de shader (solo runtime) |

## Pendiente explícito (NO cerrado)

- **Tramo móvil (Android)**: excluido del alcance por completo — pedido
  explícito del operador, no se toca hasta que lo pida.
- **Escenario "IDE abierto en paralelo durante el build"**: citado como
  riesgo concreto en `research-kmp-qt-slint.md` §A4/§A6, no instrumentado
  en esta medición (el pico de 1.37GB es con la máquina por lo demás
  ociosa).
- **`UI_QUALITY_GATE.md`**: mismo alcance que en Flutter, fuera de
  alcance para este micro-PoC técnico.
- Qt (P3) sigue sin medir — último candidato de `DECISION_STACK_T21.md`.
