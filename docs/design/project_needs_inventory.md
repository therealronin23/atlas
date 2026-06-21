# Project Needs Inventory — qué necesitamos para TODO el proyecto

<!-- Doc interno (nombres técnicos OK; NO es entregable). 2026-06-19. -->
<!-- Objetivo: inventario honesto de herramientas, deps, datos, compute, infra y
     externos que el proyecto necesita o necesitará. Triaje, no checklist de "cerrar todo". -->

## 0. Principio rector (anti-sobrearquitectura)

No se trata de cerrar los ~30 OSM en Suspensión. La mayoría son horizonte de
bajo-valor/alto-coste o requieren infra que no tenemos. Triamos en 4 cubos:
**CLOSE-NOW** (barato+valioso, 0 infra nueva), **TOOL-ACCEL** (lo desbloquean las
herramientas free de red-team), **NEEDS-DEPS** (requiere dep/ADR/infra → diferir o
decidir), **PRODUCT/ECOSYSTEM** (UI, despliegue, legal — fuera de "código del core").

---

## 1. Herramientas de seguridad / red-team (FREE, dev/CI — NO runtime)

Regla 6 CLAUDE.md: entran como **tooling de desarrollo en venv aislado**, nunca como
dep de runtime. Corren en entorno aislado (`ATLAS_HOME` propio), nunca contra el servicio
vivo (corrompe el Merkle single-writer).

| Herramienta | Uso ofensivo | Uso defensivo | Desbloquea |
|---|---|---|---|
| **NVIDIA Garak** | "Nmap para LLMs": scan de prompt-injection, jailbreaks, leaks | regresión nocturna del filtro | OSM-009 |
| **Microsoft PyRIT** | campañas multi-turn agénticas | genera corpus para la métrica de campaña | OSM-012/013 |
| **DeepTeam / Promptfoo** | baterías declarativas | CI/CD + regresión por commit | OSM-009 |
| **Giskard / Inspect (UK AISI)** | testing estructurado | scorecards reproducibles | OSM-008 STRIDE |

**Cómo encajan en nuestro diseño:** atacan al filtro Osmosis y **todo queda en el log
co-firmado** → cada ataque es un dato para (a) la métrica de campaña (C_attempts/K_attribution,
OSM-001) y (b) la memoria inmune. Eso es red-team con feedback verificable — mejor que el de
muchos startups, como bien dice el análisis de Grok.

**Caveat honesto:** generan corpus y miden *metodología*; las tasas absolutas dependen del
clasificador que se enchufe (hoy básico). Etiquetar siempre como tal.

---

## 2. Datos / corpus (FREE — verificar licencia antes de usar)

- Corpus público de jailbreaks/prompt-injection (AdvBench-style, HarmBench, in-the-wild
  jailbreak datasets) → para la demo de métrica de campaña y la regresión.
- **Necesidad:** verificar licencia de cada dataset antes de redistribuir/citar (regla de
  verificación de citas aplica también a datos).

---

## 3. Modelos (free/local + API barata)

- **Clasificador del metadata-monitor**: modelo pequeño local (estilo Llama-3.1-8B o el
  Nemotron ya integrado vía LiteLLM) + embeddings ligeros. Hoy es el eslabón débil real.
- **Feedback RLAIF** (si vamos por ahí): API fuerte (Claude/Grok) para generar preferencias.
- Compute disponible: HP Omen + VPS → fine-tuning pequeño viable; escala industrial NO.
  Honesto: no competimos en escala; el loop de mejora continuo sí es alcanzable.

---

## 4. Stack RLAIF / Constitutional AI (OPCIONAL, pesado — decidir antes de entrar)

Del análisis de Grok: **TRL (HF) + OpenRLHF + Argilla**, DPO/GRPO, constitution pequeña
(50-100 principios). Fases: RLAIF con feedback de API → apelaciones reales como señal humana
(el bucle OSM-027 es oro aquí) → hybrid RLHF con tráfico real.
**Decisión honesta pendiente:** esto es un compromiso grande. Solo entrar si el objetivo
pasa de "filtro verificable" a "filtro que además aprende a clasificar". Riesgo de scope-creep.

---

## 5. Crypto / estándares (deps reales a decidir)

- **COSE (RFC 9052)** — para interoperar con SCITT (Signed Statements). Dep real → ADR.
  Alto valor: alinea Osmosis con el estándar IETF emergente en vez de formato propio.
- ZK (horizonte, NO ahora): Halo2/Nova/PIRANHAS/zRA — meses cada uno, diferidos por diseño.

---

## 6. Infra / ecosistema (despliegue, no código-core)

- **Witness nodes independientes** (≥2 hosts no controlados por el operador) → cierre real
  de split-view (OSM-035). Hoy: transporte HTTP hecho; faltan los nodos = infra, no código.
- **Reproducible builds** (OSM-036) → confianza en filtro open-source.

---

## 7. No-código (externos)

- Asesoría legal real para el argumento de escudo legal (OSM-030) — hipótesis sin abogado.
- Cuenta arXiv + DOIs en el upload.
- Licencia: decidir AGPL-3.0 + dual-license (modelo open-core, análisis de Grok).

---

## Triaje de OSM (qué hacemos con cada cubo)

**CLOSE-NOW (barato+valioso, sin infra nueva):**
- 001 métrica de campaña (C_attempts/K_attribution) — base de la demo de cifras
- 010 anti-replay en co-firmas — endurecimiento directo
- 032 rate-limit/anti-spam del log (DoS) — el appealer ya tiene rate-limit; extender al log
- 039 provenance record (decision/action/cause) — verificar si ya está en InspectionRecord
- 008 STRIDE threat model (doc) — barato, sube credibilidad
- 006 test de escala del log (100k) — mide, no añade deps

**TOOL-ACCEL (las herramientas free los desbloquean):**
- 009 red-team simulado → Garak/PyRIT
- 011 mutador dual, 012 PromptFuzz-SC, 013 ACE-Safety → corpus de PyRIT
- 005 señuelo DECOY → diseño + harness

**NEEDS-DEPS / decidir (ADR):**
- COSE/SCITT interop (§5) — alto valor, dep real
- RLAIF stack (§4) — solo si ampliamos scope
- 015-019/031 ZK, 020 hardware — diferidos por diseño

**PRODUCT/ECOSYSTEM (no core ahora):**
- 041 canal transparencia Art.13 (UI), 034 graded responder, 021 KYC, 022 frontier API,
  035 witness nodes, 036 reproducible builds

---

## Secuencia recomendada (foco, no "todo a la vez")

1. **Demo doble** (completitud + métrica de campaña) usando Garak/PyRIT como atacante en
   harness aislado → cierra OSM-001 + 009 y produce el artefacto de credibilidad nº1.
2. **CLOSE-NOW restantes** (010, 032, 039, 008, 006) — endurecimiento barato.
3. **Decidir COSE/SCITT** (ADR) — interop estándar.
4. Lo demás: diferido con motivo escrito.
