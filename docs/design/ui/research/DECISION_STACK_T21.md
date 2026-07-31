---
title: "T2.1 — decisión de qué prototipar (enjambre + Cónclave, 2026-07-17)"
status: vigente
date: 2026-07-17
---

# Qué se prototipa y por qué (síntesis del Cónclave)

Contexto: ADR-071 (apps dedicadas Linux+Android). Evidencia: los 3 dossieres
de este directorio (enjambre Sonnet, fuentes 2025-2026 con URLs). Deliberación:
trío de emergencia Gemini(caído, fail-closed declarado) + Qwen/Groq 🇨🇳 +
Mistral-Large/OpenRouter 🇪🇺 — las dos cuentas NIM colgaban a nivel socket
(ese incidente produjo el fix INFER_REQUEST_TIMEOUT_S en el hub, 51ca94da).

## Veredicto del panel: FAIL al plan SIN medir → corregido así

Las voces discreparon en el orden (Mistral: Qt primero por estética; Qwen:
Qt/Compose pueden no ni compilar en esta máquina) pero convergieron en tres
correcciones que se adoptan ÍNTEGRAS:

1. **Micro-PoC medida ANTES de las 20 pantallas** (por stack, en ESTA máquina):
   una pantalla con shader de glow + partículas + 60fps target. Se mide:
   fps reales en la GTX 960M (Linux) y en el móvil del operador (APK),
   pico de RAM del build (vs techo earlyoom 7.5GB/proceso), tiempo de build,
   arranque en frío, y WS vivo contra el API 7341.
2. **Benchmark de sucesión en vivo** (idea de Mistral, encaja con la
   preocupación nº1 del operador): en cada prototipo, un agente Sonnet debe
   modificar un shader/pantalla sin ayuda del modelo caro. Si no puede, ese
   stack pierde puntos de sucesión — QML entra bajo sospecha demostrable
   (benchmark QML100 de Qt), no descartado a priori.
3. **Métricas cuantificables para la elección final**, no solo sensación:
   fps/jank, RAM, arranque, APK size, y el resultado del benchmark de sucesión.
   El operador elige CARÁCTER con los prototipos; los números eligen la técnica.

Corrección del juez al trío (manía challenge-the-trio): "físicamente inviable"
(Qwen) es sobreafirmación — hay 665GB de disco libres y el heap de Gradle se
capa por configuración; lo correcto es su fondo: medir el build primero.

## Decisión

- **Se prototipan TRES**: Flutter (P1 — SDK ya instalado, mejor loop para
  agentes IA, coste marginal mínimo), Compose Multiplatform (P2 — Kotlin
  mainstream, mejor carta de sucesión), Qt6/QML (P3 — el campeón estético;
  gateado a que su micro-PoC compile y rinda en esta máquina, y con el
  benchmark de sucesión como juez de su QML).
- **Tauri v2 ELIMINADO** (unánime trío + dossier): webkitgtk 40fps en Linux
  con retractación pública de un mantenedor + WebGL context-lost desde 2023 +
  red local rota en APK release (#10633) — ataca el corte de la ola.
- **React Native y Slint descalificados** en el enjambre (sin Linux / sin
  shaders). Ver dossieres.

## Orden de ejecución

1. Micro-PoC Flutter (medir) → si pasa, prototipo completo ~20 pantallas.
2. Micro-PoC Compose (medir, heap de Gradle capado) → ídem.
3. Micro-PoC Qt (medir; revisar linking dinámico LGPL + QML-builtins antes
   de distribuir nada) → ídem.
4. Los 2-3 prototipos instalados en el portátil y el Android del operador +
   tabla de métricas → el operador elige carácter; Cónclave final de stack
   con datos de ESTA máquina.

## Estado 2026-07-30: pasos 1-3 cerrados, Cónclave preliminar sin quórum

Los tres micro-PoCs (Flutter/Compose/Qt) están medidos en la GTX 960M real
de esta máquina, los tres PASA — ver
`docs/design/ui/research/{2026-07-23-t21-micropoc-flutter,2026-07-30-t21-micropoc-compose,2026-07-30-t21-micropoc-qt}-resultados.md`.
Resumen: Qt gana en build/arranque/RAM/fps, pero con un matiz honesto —
MultiEffect (su ventaja estética original) requiere Qt 6.5+ y esta
máquina solo tiene 6.4.2 en repos oficiales, no verificable.

Se intentó un Cónclave PRELIMINAR (solo datos Linux, vía `deliberation_council`
→ `adversarial_panel`) el mismo día: **UNKNOWN**, no PASS/FAIL — solo 2/3
linajes respondieron (`nvidia_glm` fail-closed), el panel exige 3 voces
distintas y correctamente rehúsa sintetizar sin esa diversidad ("unknown
> mentir"). De las dos voces que sí respondieron, `nvidia_mistral_large`
dio una objeción sustantiva real (riesgo de que la ventaja de Qt no
escale a ~20 pantallas / >10-15 `ShaderEffect` simultáneos, cita un
`QTBUG-98765` no verificado — tratar como no confirmado; coincide con el
hallazgo ya documentado sobre MultiEffect); `gemini_free` dio una
respuesta hostil cortada a media frase, sin contenido aprovechable. Un
reintento se colgó ~10min sin responder (killed). No re-litigiar este
intento fallido sin repetirlo con `nvidia_glm` confirmado vivo primero.

## Estado 2026-07-31: Cónclave preliminar con QUÓRUM REAL — veredicto FAIL

Los dos bloqueos que impidieron el quórum el día anterior quedaron
arreglados con evidencia medida, no supuesta:

1. **Tope de tiempo por-intento → presupuesto total** (`ac0243c`): un
   proveedor colgado ya no cuesta 120s×3 reintentos, cuesta 120s una vez.
2. **Fallback de linaje inalcanzable por nivel** (`5b912d6`): el reviewer
   ahora recorre los niveles del linaje en orden hasta que uno conteste,
   en vez de fijar el nivel del primario.
3. **Linaje CN invertido** (`7936cad`): `nvidia_glm` se cuelga siempre
   (medido tres veces distintas); `groq_qwen3` (mismo linaje CN — Qwen es
   Alibaba, GLM es Zhipu) pasa a primario. Medido: el asiento CN pasó de
   123.0s/`reachable=False` a **9.2s/`reachable=True`**.

Con eso, el Cónclave real dio **quórum 3/3** por primera vez —
`gemini_free`, `groq_qwen3`, `nvidia_mistral_large` respondieron los tres.

**Veredicto: `FAIL`.** Las tres voces, independientemente, señalan la
misma objeción de fondo: el benchmark de referencia (una pantalla, glow +
24 partículas) es demasiado estrecho para extrapolar a ~20 pantallas
complejas, y la ventaja numérica de Qt (build/arranque/RAM/fps) podría no
sobrevivir a esa escala. Puntos convergentes entre las tres voces:

- **MultiEffect roto la premisa original.** `nvidia_mistral_large` lo
  dice explícito: "la comparación de fps se vuelve irrelevante — Qt ya no
  tiene una capa de abstracción superior para efectos visuales" sin él.
  Coincide con el hallazgo ya documentado en el informe de Qt.
- **Escalabilidad de shaders/memoria GPU sin medir**: la GTX 960M tiene
  solo 2GB VRAM; ningún micro-PoC probó 5-10 shaders complejos
  simultáneos, ni qué pasa con 20 pantallas cargadas a la vez.
- **Toolchain de Qt como riesgo de despliegue**: `groq_qwen3` señala que
  el split real de paquetes Debian (`qt6-declarative-dev` vs
  `qml6-module-*`, medido hoy mismo — 3 rondas de apt) rompe builds
  reproducibles/CI si no se gestiona con cuidado.
- **Benchmark de sucesión estadísticamente insignificante**: n=1 en los
  tres candidatos, ninguna voz lo acepta como prueba suficiente.
- **`gemini_free` no aportó objeciones nuevas** más allá de calificar la
  síntesis previa de "autoengaño" — descartable como señal, pero no
  invalida el veredicto: las otras dos voces sí dieron objeciones
  concretas y verificables.

**Lo que este veredicto NO dice**: no descalifica a Qt como candidato ni
corona a Flutter/Compose — dice que el benchmark de referencia (una
pantalla) es insuficiente para decidir con confianza a la escala real del
producto (~20 pantallas). Es exactamente el tipo de punto ciego que el
Cónclave existe para encontrar antes de invertir semanas construyendo
sobre una base no probada.

El ADR de stack GANADOR sigue sin cerrarse — paso 4 (Android + elección
del operador) pendiente, a pedir explícitamente. Este veredicto añade una
recomendación nueva y concreta para cuando se retome: antes de comprometerse
a un stack, medir un prototipo con MÁS de una pantalla y más carga de
shaders simultánea, no solo el micro-PoC de referencia.
