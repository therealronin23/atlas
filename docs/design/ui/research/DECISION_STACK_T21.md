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

El ADR de stack GANADOR sigue sin cerrarse — paso 4 (Android + elección
del operador) pendiente, a pedir explícitamente.
