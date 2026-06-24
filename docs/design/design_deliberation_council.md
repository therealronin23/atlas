# Diseño — Cónclave (`deliberation_council`): deliberación verificable multi-voz

<!-- Doc interno de diseño (nombres internos OK). 2026-06-24. Borrador para iterar.
     Plan→DISEÑO; construir es la fase siguiente. Estado vivo en WORK_LEDGER.md (no aquí). -->

Alias narrativo (solo docs humanos): **Cónclave**. Nombre técnico (código/skill): `deliberation_council`.

## Objetivo

Un skill de **deliberación** para decisiones reales (arquitectura, stack, seguridad, bugs
atascados, decisiones irreversibles): ayuda a decidir y presiona los puntos ciegos, anclado en
las **manías** del repo (AGENTS.md §OPERATING LOOP, líneas 40–47) — no en unas "12 reglas"
externas. Barato e instantáneo por defecto (un solo juez); escala a un panel multi-modelo solo
cuando la apuesta lo merece.

La tesis (de la fuente "Council" del usuario, verificada): *el valor no es decirte qué hacer, es
enseñarte **dónde discrepan** las voces independientes — ahí está lo realmente complejo del
problema.* Un solo modelo no puede discrepar de sí mismo; varios linajes sí.

## Qué NO es (alcance, anti-bloat)

- **No ejecuta ni es un loop.** Delibera y hace *handoff*; no posee el control de ningún bucle.
- **No instala nada externo.** Reutiliza `adversarial_panel.py` (ADR-047) + `cascade.py`
  (ADR-042) + el pool de proveedores ya cableado. Nada de plugins de terceros que manejen keys
  (violaría `wire-before-claim`, "todo efecto externo Merkle-auditado", "cero deps sin ADR").
- **No corre la ceremonia completa siempre.** El coste se paga solo cuando la decisión lo merece
  (Regla 2 — Simplicidad; gating de `adversarial_panel`: "convocar modelos para un typo es absurdo").

## Principio de arquitectura: roles = interfaces, no identidades

| Rol | Hoy | Permanencia |
|-----|-----|-------------|
| **Juez / Maestro (silla)** | Claude (Anthropic 🇺🇸) | slot pluggable → sucesión (v2) |
| **Voz 1 del trío** | Gemini (Google 🇺🇸) | permanente |
| **Voz 2 del trío** | Kimi (Moonshot 🇨🇳) | permanente |
| **Voz 3 del trío** | Mistral-Large-3 (Mistral 🇪🇺) | permanente |

El trío = 🇺🇸 + 🇨🇳 + 🇪🇺, tres linajes ortogonales (máxima señal de desacuerdo). La silla
**no vota** en el panel: lo preside y sintetiza. Que sea un *slot* es lo que hace la sucesión
barata (un cambio de config, no una reescritura).

## El protocolo (4 pasos, coste escalonado)

1. **Encuadre (juez, barato).** Reformula la decisión + criterios de éxito + qué manías están en juego.
2. **Lentes (juez, barato).** Aplica solo los Sombreros que la decisión pide (normalmente Negro
   riesgos + Verde alternativa quirúrgica; a veces Blanco hechos / Amarillo upside). **Checklist
   de lentes, no seis secciones obligatorias** — eso recrearía el bloat que se evitó.
3. **Escalada (trío, caro — solo alto riesgo / irreversible).** Convoca `AdversarialPanel.verify`
   con los tres proveedores. **Diversidad obligatoria**: si no hay diversidad mínima viva →
   veredicto **UNKNOWN** (unknown > mentir), no se inventa.
4. **Síntesis honesta (juez).** **Muestra el desacuerdo crudo del trío ANTES de resumir**
   (salvaguarda dura contra la influencia de la silla). Cierra con recomendación + veredicto:
   **PASS / FAIL / UNKNOWN** (tipo `Evidence` de la capa 1).

## Profundidad adaptativa (gating)

| Apuesta | Qué corre | Coste |
|---------|-----------|-------|
| Trivial | No se activa / respuesta directa | 0 |
| Decisión normal | Pasos 1–2 (juez solo + lentes) | bajo |
| Alta / irreversible | Pasos 1–4 (+ trío + pre-mortem) | alto, justificado |
| Palanca manual | `council: full` / `council: quick` / `council: off` | — |

La autoactivación por `description` es **best-effort** (igual que el OPERATING LOOP confiesa de sí
mismo); la invocación manual es el camino fiable. No se vende "se activa siempre solo".

## Capa de reglas: las manías, no "12 reglas"

La "auditoría" NO es una tabla de ✅ autopuesta (eso era teatro y violaba la Regla 6 para
demostrar que la cumple). Es: (a) el veredicto real del paso 4, y (b) cuando importa, una nota
corta de qué manías estuvieron en juego. Las manías relevantes a la deliberación:
`honesty-over-sycophancy`, `decide-with-facts`, `internal-prior-art-first`, `wire-before-claim`,
`verify-the-real-case`, Reality First (marca lo desconocido como desconocido).

## Artefactos (dos consumidores, una fuente)

- **(A) `.claude/skills/deliberation_council/SKILL.md`** — skill nativo de Claude Code. Lo carga
  el juez (Claude). Escalada completa al trío. No versionado (`.claude/` untracked).
- **(B) `docs/skills/deliberation_council.md`** — servido por el tronco MCP (`SkillStore`,
  `mode:served`, registrado en el catálogo). **Lo usa Atlas.** Fuente canónica versionada.
- **(C) Versión copy-pega (degradada, honesta)** — para claude.ai Projects fuera de atlas. Solo
  juez-único (Sombreros + manías + honestidad). **Sin trío**: el web app no llega al pool NIM ni a
  `adversarial_panel`. Se documenta como subconjunto, no como equivalente.

(A) y (B) comparten contenido; (B) es la fuente versionada, (A) su reflejo operativo.

## Sucesión / destilación (side-effect en v1, máquina en v2)

En v1: las síntesis del juez se registran **legibles** (el porqué, no solo el veredicto) vía el
`teacher_debate`/`LessonStore` **ya cableado** (CAPABILITIES: "Lazo de aprendizaje AUDITABLE",
real). Es un side-effect barato (una llamada), **no** infraestructura nueva. Sustrato para medir
en v2 si la destilación transfiere criterio. `wire-before-claim`: registrar lecciones ≠ garantizar
que Atlas herede el juicio; eso es pregunta empírica abierta.

## Honestidad de capacidades (al construir, anotar en CAPABILITIES.md)

- Protocolo de deliberación de juez-único: será **real** (código + consumidor + tests) ya en v1.
- Escalada al trío: **real solo si** los tres proveedores responden vivos en el momento; si no,
  el propio diseño emite UNKNOWN. El cableado a Kimi/Mistral vía NIM se verifica al construir
  (memoria `nvidia-nim-frontier-models.md`: algunos identifiers dan 404).
- Destilación maestro→Atlas: **andamiaje** en v1 (se registra, no se afirma transferencia).

## Fuera de v1 — backlog v2 (validable, no vaporware)

- **Puerta de reinicio de loop con el trío**: al final de un bucle (`/autobuild`, SelfAuditRunner,
  `live_loop`), el trío decide convergió / reiniciar-con-objetivo-corregido / parar. Checkpoint
  anti-runaway (Regla 10). Reabre la frontera "deliberación, no loop" a propósito y con cuidado.
- **Debate por rondas**: los modelos se ven y se rebaten (2 rondas), separando desacuerdo real
  (sobrevive a la réplica) de malentendido. `adversarial_panel` HOY es one-shot paralelo
  (verificado); esto es la mejora aditiva genuina de la investigación del usuario.
- **Máquina de sucesión**: silla pluggable real + posible 4º sintetizador dedicado.

Cada pieza de v2 entra **tras validar v1**, no antes (tipo-1/tipo-2, `convergence-discipline-verification`).

## Definition of done (estándar del repo)

Tests verdes + mypy strict + `WORK_LEDGER.md` actualizado en el mismo commit + nota en este design
doc + límite honesto declarado en CAPABILITIES.md. `wire-before-claim`: no se declara "real" sin
consumidor no-test + integración.

## Riesgos / pre-mortem

- **Latencia/coste del trío** ahuyenta el uso → mitigación: trío es la escalada, no el defecto;
  gating agresivo.
- **La silla traga el desacuerdo** → mitigación dura: paso 4 muestra el desacuerdo crudo ANTES.
- **Autoactivación no dispara** → mitigación: invocación manual fiable + puntero opcional en AGENTS.md.
- **Sucesión se vuelve humo** → mitigación: en v1 es solo registro; la máquina espera validación.
