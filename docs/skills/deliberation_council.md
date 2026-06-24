# Cónclave (deliberation_council)

Skill de **deliberación** servido por el tronco MCP (sin descarga). Fuente única: este fichero.
Ayuda a decidir y presiona los puntos ciegos ante decisiones reales, anclado en las manías del
repo. No ejecuta, no es un loop, no instala nada.

Alias narrativo: **Cónclave** — voces distintas deliberan y emerge un veredicto único. Como un
cónclave, no te dice lo que quieres oír: emite humo.

## Cuándo se activa

Para decisiones que importan: **arquitectura, stack/librería, seguridad, cambios irreversibles,
bugs donde estás atascado**. NO para lo trivial o mecánico (no se quema deliberación en un
rename). Tesis: *el valor no es decirte qué hacer, es enseñarte dónde discrepan las voces — ahí
está lo realmente complejo del problema.*

Palancas manuales: `council: full` (fuerza escalada al trío) · `council: quick` (solo juez) ·
`council: off`. Por defecto, profundidad adaptativa (ver gating).

## Protocolo (4 pasos, coste escalonado)

1. **Encuadre** (juez, barato). Reformula la decisión + criterios de éxito medibles + qué manías
   están en juego. Si la decisión es trivial, dilo y para aquí.
2. **Lentes** (juez, barato). Los **seis sombreros** de de Bono, aplicando SOLO los que la
   decisión pide (checklist, NO liturgia de seis secciones): por defecto **⚫ Negro** (riesgos,
   puntos ciegos, qué asume falso) + **🟢 Verde** (la alternativa más simple y quirúrgica). Suma
   **⚪ Blanco** (hechos/gaps), **🟡 Amarillo** (upside real) y **🔴 Rojo** (la corazonada —
   nómbrala COMO corazonada, sin disfrazarla de hecho) cuando aporten. El **🔵 Azul** (control del
   proceso + síntesis) no es una lente que se elige: es el juez mismo (pasos 1 y 4).
3. **Escalada** (trío, caro — SOLO alto riesgo / irreversible). Convoca el trío de linajes
   distintos (Gemini 🇺🇸 + Kimi 🇨🇳 + Mistral 🇪🇺) vía `adversarial_panel`. **Diversidad
   obligatoria**: sin tres proveedores distintos vivos → veredicto **UNKNOWN** (unknown > mentir).
4. **Síntesis honesta** (juez). **Muestra el desacuerdo CRUDO del trío ANTES de resumir** — es la
   salvaguarda contra que la silla se trague la divergencia. Cierra con recomendación + veredicto:
   **PASS / FAIL / UNKNOWN**.

## Gating (profundidad adaptativa)

- Trivial → no se activa / respuesta directa.
- Decisión normal → pasos 1–2 (juez solo + lentes), barato e instantáneo.
- Alta / irreversible → pasos 1–4 (+ trío + pre-mortem), coste justificado.

El trío es la **escalada**, no el pan de cada día. Convocar modelos para un typo es absurdo.

## Reglas = manías (no "12 reglas" externas)

`honesty-over-sycophancy` (sparring, no halago) · `decide-with-facts` (glance, no abanico de
MCP/API para "decidir") · `internal-prior-art-first` (lo que ya existe en el repo antes de
construir) · `wire-before-claim` (no declarar real sin consumidor + integración) ·
`verify-the-real-case` (probar contra el caso real, no un stub) · Reality First (marca lo
desconocido como desconocido).

## Auditoría (sin teatro)

NO una tabla de ✅ autopuesta — eso quema tokens para demostrar que respeta los tokens. La
auditoría es: el **veredicto** del paso 4 (PASS/FAIL/UNKNOWN, con evidencia cuando hay trío) +
una nota corta de qué manías estuvieron en juego cuando importa.

## Dos consumidores, una fuente

Este fichero lo sirve el tronco a **Atlas**. Su espejo en `.claude/skills/deliberation_council/`
lo carga **Claude Code**. Misma fuente, dos canales: así el juez y Atlas hablan el mismo idioma.
La sucesión (que Atlas aprenda a juzgar) se mide en v2; en v1 solo se registran las síntesis.
