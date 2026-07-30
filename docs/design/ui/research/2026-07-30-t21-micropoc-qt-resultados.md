---
title: "T2.1 micro-PoC Qt6/QML — resultados de medición (tramo Linux desktop)"
status: vigente
date: 2026-07-30
---

# Resultados del micro-PoC Qt6/QML (t2-1-micropoc-qt)

Cierra el tramo Linux desktop del tercer y último candidato de
`DECISION_STACK_T21.md` (P3, gateado — "confirmar primero que compila y
rinde en esta máquina concreta antes de invertir más"). El tramo móvil
(Android) queda explícitamente **excluido del alcance** por pedido directo
del operador, igual que en Flutter y Compose — el ítem `t2-1-micropoc-qt`
YA existía en `docs/backlog.yaml` (`priority: 2`, `status: pending`, mismo
`targets: prototypes/atlas_ui/qt_micropoc/` usado aquí) y ya anticipaba
correctamente tanto el requisito de MultiEffect como el matiz de linking
LGPL — sigue `pending`, no se marca `done` (Android pendiente).

Proyecto: `prototypes/atlas_ui/qt_micropoc/` (nuevo, CMake + C++17 mínimo +
QML). Medido en la GTX 960M real (`prime-select nvidia`, mismo estado que
Flutter/Compose el mismo día).

## Bloqueante resuelto: toolchain Qt6 no existía en la máquina

Cero paquetes `qt6-*` instalados al empezar (solo Qt5 residual). Instalado
vía `apt` (acción de sistema, requirió permiso explícito del operador y
que él mismo corriera el comando — `sudo` bloqueado por falta de
contraseña interactiva, igual que con `prime-select`, en tres rondas
sucesivas según se fueron descubriendo dependencias runtime que faltaban):

1. `qt6-base-dev qt6-base-dev-tools qt6-declarative-dev qt6-declarative-dev-tools qt6-shadertools-dev qt6-websockets-dev` — headers/libs de compilación.
2. `qml6-module-qtquick qml6-module-qtquick-window` — plugins QML runtime que `qt6-declarative-dev` NO trae por defecto (Debian/Ubuntu separa headers de compilación de los módulos QML runtime en paquetes `qml6-module-*` independientes; `QQmlApplicationEngine` fallaba con "module QtQuick.Window is not installed" hasta instalar esto).
3. `qml6-module-qtqml qml6-module-qtqml-workerscript` — dependencia transitiva de `ShaderEffect`/motor QML interno, mismo patrón de paquete separado.

**Hallazgo real de packaging, no solo de esta app**: cualquier proyecto
QML en Debian/Ubuntu necesita enumerar explícitamente cada módulo QML que
usa como paquete `qml6-module-*` — los `-dev` no son autosuficientes en
runtime. Relevante para cualquier despliegue futuro de un stack Qt en
esta familia de distros.

**Versión real disponible: Qt 6.4.2**, no 6.5+. Confirmado con
`apt-cache madison qt6-base-dev` (una sola versión en los repos de Linux
Mint 22.3/Ubuntu noble, sin backports más nuevos). Esto es un hallazgo
honesto que matiza directamente `research-kmp-qt-slint.md` §B2: **`MultiEffect`
(Qt Quick Effects) requiere Qt 6.5+ y NO está disponible en esta máquina
con los repos por defecto** — no se pudo verificar el benchmark citado
("120fps con 12 efectos combinados") porque el módulo simplemente no
existe aquí. El glow de este micro-PoC usa `ShaderEffect` con GLSL/qsb
custom directamente (la ruta de shaders "de toda la vida" en Qt Quick,
disponible desde Qt5) — misma técnica de fondo que Flutter (SkSL vía
`FragmentProgram`) y Compose (SkSL vía `RuntimeEffect`), sin la capa de
conveniencia que la investigación señalaba como diferenciador de Qt. No se
intentó una PPA de terceros para conseguir Qt 6.5+ (fuera de alcance:
añadir una fuente apt no oficial es un cambio de confianza de suministro
mayor que instalar del repo oficial, no se hizo sin plantearlo aparte).

**Licencia**: todo el linking es dinámico (CMake `target_link_libraries`
contra las `.so` de los paquetes `libqt6*` de apt, sin ningún flag de
linking estático) — el camino LGPL gratuito que `research-kmp-qt-slint.md`
§B3 identificaba como viable para este caso de uso. No se tocó nada del
matiz de "QML builtins" citado ahí (siempre estático); no se investigó
más a fondo porque no bloqueaba la medición técnica.

## Qué se midió y cómo

Arquitectura real de Qt6/QML (a diferencia de Flutter/Compose, que son
"todo en un lenguaje"): `Main.qml` (vista declarativa: `ShaderEffect` con
el glow, 24 partículas orbitando vía `Repeater`+`Rectangle` con posición
calculada en JS/QML, texto de fps/WS) + `main.cpp` (backend C++ mínimo:
`MicroPocController` cuenta fps real conectado a la señal
`QQuickWindow::frameSwapped` — señal real de vsync/GPU, no un timer
aproximado — y gestiona el cliente `QWebSocket` contra el bridge). Mismo
formato de log `MICROPOC_STATS` a stdout que Flutter y Compose.

## Métricas medidas (GTX 960M real, Linux, esta máquina)

| Métrica | Valor real medido | Veredicto |
|---|---|---|
| Build release limpio (`cmake --build build`, Ninja, `-j8`) | 3.68s, CPU 259% | — (sin umbral de referencia, dato informativo) |
| Pico de RAM durante el build | RSS máx.: ~266MB (266 124 KB) | **PASA** frente al techo earlyoom 7.5GB/proceso, con margen amplísimo (~3.5% del techo) |
| Arranque en frío (proceso lanzado → primer paint + stats confirmados) | ~1.2s | **PASA** — el más rápido de los tres candidatos medidos hoy |
| fps en régimen estable | 60-61fps consistente | **PASA** contra el target de 60fps — el más estable de los tres (menos varianza que Flutter 53-61 y Compose 53-61) |
| Estabilidad ante resize de ventana | Sin crash, fps se mantiene tras 2 resizes (`wmctrl`) | **PASA-CON-MATIZ** — misma prueba puntual que los otros dos |
| WS vivo contra 127.0.0.1:7341/events | Conecta con header `Origin` explícito (`QNetworkRequest::setRawHeader`, mismo requisito transversal ya documentado); recibe los 23 eventos históricos reales | **PASA** — sin fricción de integración nueva |
| RAM en ejecución (steady state) | ~134MB RSS | **PASA** — el más ligero de los tres |
| GPU confirmada por evidencia externa | `nvidia-smi` muestra el proceso `qt_micropoc` con memoria asignada en la GTX 960M (3MiB) durante la ejecución | **Verificado directamente**, no inferido |
| Validación de shader en build | `qsb` (Qt Shader Baker, invocado por `qt_add_shaders` de CMake) compila el `.frag` a SPIR-V como paso de build — un error de sintaxis GLSL detiene el build ahí mismo | **Ventaja real de robustez** frente a Compose (que no valida SkSL hasta runtime) |

## Benchmark de sucesión (Cónclave 2026-07-17, punto 2 del veredicto)

**PASA.** Un subagente Sonnet completamente independiente (sin contexto de
esta sesión, sin ayuda ni pistas de cómo resolverlo) recibió la tarea de
añadir un tercer anillo de glow concéntrico al shader GLSL existente, con
fase/frecuencia y color distintos, fusionado de forma coherente.

- **1 sola iteración** hasta compilar limpio (`cmake --build build`).
- **Sin consultar documentación externa** (ni WebSearch ni WebFetch):
  entendió el dialecto Qt RHI/qsb (bloque de uniforms `qt_Matrix`/
  `qt_Opacity`/`uTime`/`uSize`, `qt_TexCoord0`, `fragColor`) solo leyendo
  el `.frag` original, sin tocar ningún uniform nuevo.
- **Confirmó explícitamente, sin que se le preguntara**, que el pipeline
  de build SÍ valida la sintaxis GLSL en tiempo de compilación (`qsb`
  como paso `[1/4]` del build) — contraste directo y honesto con lo que
  el benchmark equivalente de Compose reveló (SkSL no se valida hasta
  runtime). Esto NO es una opinión del subagente sobre Qt en general, es
  una observación verificable sobre el mecanismo real de build que él
  mismo pudo ver ejecutarse.
- **Verificado independientemente por mí**: ejecuté el binario tras el
  cambio (`./build/qt_micropoc`), confirmé en vivo `MICROPOC_STATS fps=60-61
  shader=ok`, sin crash.

Qt es, de los tres candidatos, el único donde tanto el benchmark de
sucesión pasó a la primera COMO el propio mecanismo de build detecta
errores de shader — coincide con Flutter en esto último (que también
detecta errores de shader en build vía `impellerc`), no con Compose.

## Lectura honesta global (tramo Linux desktop)

Ningún criterio dio **FALLA**. Qt6/QML es, de los tres candidatos medidos
hoy en esta máquina concreta, el más rápido en build (3.68s vs 31.58s
Flutter vs 89.8s Compose), el más rápido en arranque (~1.2s vs ~1.5s vs
~8.1s), el más ligero en RAM tanto de build (266MB vs 550MB vs 1.37GB)
como en ejecución (134MB vs 186MB vs 282MB), y el más estable en fps
(60-61 consistente vs 53-61 en los otros dos). Esto contradice
parcialmente la lectura teórica de `research-kmp-qt-slint.md` §A4/§A6
sobre riesgo de build en portátil modesto — ese riesgo era real para
Compose (JVM+Gradle), pero Qt con CMake+Ninja nativo resultó ser el
candidato MÁS ligero, no uno intermedio.

**El matiz real y honesto**: no se pudo verificar la ventaja estética
específica que `research-kmp-qt-slint.md` §B2 citaba como diferenciador
fuerte de Qt (`MultiEffect`, Qt Quick Effect Maker) porque requiere Qt
6.5+ y esta máquina solo tiene 6.4.2 en sus repos oficiales. El glow
medido aquí usa la misma técnica de "shader custom a mano" que los otros
dos candidatos, así que la comparación de fps es de verdad manzanas con
manzanas — pero la pieza que hacía a Qt "el único que pasa R2 sin matiz"
en el veredicto original no se pudo poner a prueba tal cual estaba
planteada.

**Comparación directa de los tres candidatos (mismos criterios, misma
máquina, mismo día 2026-07-30):**

| Criterio | Flutter | Compose | Qt6/QML |
|---|---|---|---|
| Build release limpio | 31.58s / ~550MB RSS | 89.8s / ~1.37GB RSS | **3.68s / ~266MB RSS** |
| Arranque en frío | ~1.5s | ~8.1s | **~1.2s** |
| fps estable | 53-61 | 53-61 | **60-61 (más consistente)** |
| RAM ejecución (steady) | ~186MB | ~282MB | **~134MB** |
| Build detecta errores de shader | Sí (`impellerc`) | **No** (solo runtime) | Sí (`qsb`) |
| Benchmark de sucesión | PASA, 1 iteración | PASA, 1 iteración | PASA, 1 iteración |
| Toolchain requerido en esta máquina | Ya estaba (SDK Flutter) | Gradle vía SDKMAN (usuario, sin sudo) | Qt6 vía apt (sistema, requirió operador 3 veces) |
| Shaders "cinematográficos" con herramienta dedicada | No (SkSL a mano) | No (SkSL a mano) | **No en esta máquina** (MultiEffect/QQEM necesitan 6.5+, no disponible) |

## Pendiente explícito (NO cerrado)

- **Tramo móvil (Android)**: excluido del alcance por completo — pedido
  explícito del operador.
- **MultiEffect / Qt Quick Effect Maker**: no verificable en esta máquina
  con Qt 6.4.2 de los repos oficiales; requeriría Qt 6.5+ vía una fuente
  no evaluada aquí (PPA de terceros o el instalador online de Qt, ambos
  fuera de alcance de esta sesión).
- **Revisión de licencia LGPL antes de cualquier distribución**: el
  linking es dinámico (confirmado), pero `research-kmp-qt-slint.md` §B3
  señala un matiz específico de los "QML builtins" en Qt 6 moderno que no
  se investigó a fondo aquí porque no bloqueaba la medición técnica.
- **`UI_QUALITY_GATE.md`**: mismo alcance que en Flutter/Compose, fuera de
  alcance para este micro-PoC técnico.
- **Cónclave final de stack** (`DECISION_STACK_T21.md` 2.4): con los tres
  candidatos ya medidos en Linux, puede correr un Cónclave PRELIMINAR
  (solo datos Linux) — el veredicto GANADOR final sigue sin cerrarse hasta
  que exista medición Android, cuando el operador la pida explícitamente.
