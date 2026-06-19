# Auditoría + premortem — ADR-054 y el conjunto Gateway (051/053/054)

Fecha: 2026-06-15 · Tipo: auditoría completa con premortem · Tono: honesto, sin
sycophancy (a petición explícita del usuario) · Pregunta del usuario:
*"¿hemos descubierto algo? y si no es novedoso, ¿cabe mejorarlo con el proceso
acumulado de Atlas + lo que haya por ahí?"*

> Veredicto en una línea: **ninguna capa individual es un descubrimiento — todas
> existen en papers de 2024-2026. Lo que NO existe en la literatura es la
> composición "capas de detección/engaño sobre un log de completitud verificable
> en ambos sentidos" (capa 4). Eso es modesto pero real, y es justo lo que el
> proceso acumulado de Atlas puede ejecutar mejor que un paper suelto.**

---

## A. ¿Qué es descubrimiento y qué no? (respuesta directa)

| Pieza | ¿Novedoso? | Quién ya lo tiene |
|---|---|---|
| Filtro/clasificador en cascada | No | CC++ (Anthropic, ene-2026) |
| Objetivo móvil (polimorfismo) | No | FlexLLM/MTD (dic-2024) |
| Señuelo / "sensación de éxito" | No | HoneyTrap, Active Honeypot Guardrail (2025-2026) |
| Merkle como log de auditoría | No | Certificate Transparency (RFC 9162, 2021) |
| Attestation de enclave | No | RATS (RFC 9334) |
| **Completitud por co-firma del cliente + detección de omisión** | **Parcial** | la idea de witness/gossip es de CT; aplicarla a *inspección de contenido de IA* con co-firma del usuario como mitad probatoria es poco visto |
| **Composición: detección/engaño ↔ log de completitud que genera la causa** | **Sí (modesto)** | no encontrado como sistema integrado en la literatura revisada |

**Conclusión honesta:** el "descubrimiento" no es una técnica nueva. Es un
**encuadre** (reframe) y una **integración**. En investigación eso vale menos que
un algoritmo nuevo, pero como *carta de presentación de cómo piensa Atlas* vale
exactamente lo que el usuario quería: demuestra criterio de composición y
honestidad, no un avance de SOTA.

---

## B. Fallos de raíz de ADR-054 (lo que lo mata)

### B1. R1 (sonda verificable) puede vaciar la capa 3 en el ÚNICO dominio que importa.
El caso de uso del veto es ciberofensiva/exfiltración — dominios **verificables**
por el atacante. Ahí el señuelo se detecta al primer intento ejecutable. Entonces
la capa 3 no "engaña al adversario serio"; solo sirve para generar la causa
forense. Si la carta vende "honeypot que recupera el modelo del mareo de prompt",
un revisor responde: "en mi dominio lo detecto ejecutándolo". **Hay que vender la
capa 3 como generador-de-causa, no como defensa eficaz.** Si se vende lo segundo,
C1 reaparece disfrazado.

### B2. Dependemos de números que la propia metodología que citamos desacredita.
Citamos *Attacker Moves Second* para decir "las defensas reportan números
inflados" y en la misma página usamos el 68.77% de HoneyTrap. Es incoherente
salvo que se diga explícitamente (y se dice, I4/R2): **no construir sobre esas
cifras**. Riesgo de que en la ejecución alguien las trate como reales y dimensione
mal. Mitigación: I4 prohíbe reportar tasas; el premortem lo reitera aquí.

### B3. Tres dependencias externas vivas = superficie de mantenimiento permanente.
Mismo patrón que D2 de ADR-052: cada capa externa (CC++, MTD, HoneyTrap) hay que
seguirla, versionarla o reimplementarla bajo la regla de oro. Para un solo
desarrollador esto es deuda recurrente, no un build de una vez.

---

## C. La pregunta que importa: ¿lo mejora el proceso acumulado de Atlas?

Esta es la parte donde la respuesta es **sí, y de forma concreta** — no por la
idea, sino por la maquinaria que Atlas ya tiene construida y verificada:

1. **Log de completitud (ADR-053, ya construido y verificable con `atlas reality`).** Es la capa 4. No
   hay que inventarla: existe en `src/atlas/transparency/`. Esto es lo que ningún
   paper de honeypot tiene — todos registran "internamente" sin completitud
   verificable por el usuario.
2. **VerifiedProducer + panel adversarial (ADR-048, capa 3 del enjambre).** El
   mismo lazo abogado-del-diablo que Atlas usa para auto-mejora puede **generar y
   verificar los decoys**: un decoy es un artefacto que debe pasar el invariante
   "plausible para el atacante ∧ inútil de verdad". Eso es exactamente un
   `ArtifactKind` con verificador. Atlas ya sabe producir-bajo-verificación.
3. **LessonStore (ADR-044).** Cada bypass observado es una lección
   (`avoid_pattern` + `detection_heuristic`) que realimenta la capa 1. El sistema
   **aprende de la campaña que la capa 4 hizo inocultable** → cierra el lazo
   detección→evidencia→mejora. Ningún honeypot publicado tiene este realimentado.
4. **Decider/PDP (ADR-040).** El gating I1 (señuelo solo tras causa confirmada)
   es una decisión del PDP intercambiable, no un `if` hardcodeado. Encaja con la
   dirección "humano como una implementación más".
5. **Organismo de conocimiento (ADR-049).** El conector genérico ya rastrea
   señales externas; un `KnowledgeSource` para "nuevas técnicas de jailbreak /
   nuevas defensas" mantiene la capa 1 y la lista de abusos al día
   automáticamente. La obsolescencia de B3 se mitiga con maquinaria existente.

> **Esta es la respuesta real a la pregunta del usuario:** lo descubierto no es
> novedoso como técnica, PERO Atlas ya tiene cinco subsistemas construidos
> (transparency, VerifiedProducer, LessonStore, Decider, knowledge organism) que
> convierten un honeypot estático de paper en un **lazo vivo:
> produce decoy verificado → causa registrada inocultable → lección →
> mejora del filtro → conocimiento actualizado**. Eso sí es propio, porque
> depende de capacidades que solo este repo tiene juntas.

---

## D. Lo que falta para que la mejora sea real (no aspiracional)

1. **`ArtifactKind.DECOY` + verificador** (plausible ∧ inútil) — sin esto, los
   decoys son ad-hoc y no pasan por la maquinaria de verificación. Es la pieza que
   conecta C2 con la realidad.
2. **`KnowledgeSource` de técnicas jailbreak/defensa** — sin esto, B3 (obsolescencia)
   no está mitigado, solo prometido.
3. **Métrica de campaña falsable** — definir qué cuenta como "encarecí la campaña"
   de forma medible (p.ej. nº de intentos co-firmados antes de bloqueo, coste de
   re-optimización estimado). Sin métrica, I4 es retórica.
4. **Red-team adaptativo propio (aunque sea mínimo)** — un atacante de juguete que
   re-optimiza contra nuestras capas, para no caer en B2 (creernos los números
   ajenos). El enjambre/panel adversarial de ADR-048 es el candidato natural.

---

## E. Premortem: causa de muerte más probable, por orden

1. **Se vende la capa 3 como defensa eficaz** (no como generador de causa) y un
   revisor la rompe con una sonda verificable (B1) → se pierde la credibilidad que
   sí daba la capa 4. *Mitigación: el encuadre de la carta debe ser "coste +
   verificabilidad", nunca "detección".*
2. **Se dimensiona sobre 68.77%/"0%"** y la realidad adaptativa lo desmiente (B2).
   *Mitigación: I4 + métrica de campaña propia (D3).*
3. **Fatiga de mantener tres líneas externas** (B3/D2 de ADR-052) antes de cerrar
   el lazo vivo de la sección C. *Mitigación: priorizar capa 4 + LessonStore (lo
   propio y ya construido); las externas tras interfaz, sin perseguir su SOTA.*

**Qué NO lo mata:** la maquinaria de Atlas (sección C). El riesgo nunca es la
ingeniería propia; es sobre-reclamar eficacia de capas ajenas.

---

## F. Veredicto

- **¿Descubrimiento?** No como técnica. Sí como **composición + encuadre**, y la
  parte verdaderamente propia (capa 4 sobre la que cuelgan las demás, realimentada
  por LessonStore/VerifiedProducer/knowledge organism) es modesta pero real y
  **ejecutable hoy con subsistemas ya construidos y testeados**.
- **¿Se mejora con el proceso de Atlas?** Sí, concretamente: cinco subsistemas
  existentes convierten honeypots estáticos de paper en un lazo vivo
  produce→evidencia→lección→mejora→conocimiento. Esa es la única ventaja
  defendible, y es real porque ya está construida en partes.
- **Recomendación:** NO construir las tres capas externas. Construir **D1
  (ArtifactKind.DECOY + verificador)** y **D3 (métrica de campaña)** sobre la capa
  4 ya existente — es lo propio, lo barato y lo honesto. Las capas 1-3 quedan tras
  interfaz con stubs. La carta a Anthropic se reescribe con el eje "coste +
  verificabilidad + lazo de aprendizaje", retirando toda promesa de tasa.

El planteamiento no es novedoso, pero tampoco vacío: es una **integración honesta
que solo Atlas puede ejecutar como organismo vivo**. Eso es exactamente lo que el
usuario pidió averiguar.

---

## ADDENDUM 2026-06-15 — capa 5 (inmunidad adaptativa) tras 2ª investigación

El usuario señaló que Atlas, con memoria, puede *inmunizarse* acumulando
conocimiento del ataque. **Confirmado por literatura, y vuelve a no ser novedoso:**
*immune memory-based jailbreak detection* (arXiv:2512.03356, dic-2025; immune
detection + active immunity + memory updating; 94%) y co-evolución
CHASE/Self-RedTeam/TriPlay-RL/MAGIC (2026). ADR-054 reescrito con esto.

**El hallazgo que SÍ aporta valor (y agrava el veredicto a favor):** CHASE
confiesa que el auto-juego **colapsa en diversidad** — el defensor se estanca en
lo que ya vio. Atlas tiene la única mitigación estructural: el organismo de
conocimiento (ADR-049) inyecta diversidad de ataque **externa**, que el auto-juego
no genera. Auto-juego solo → plateau; auto-juego + ADR-049 → no. Ningún paper lo
tiene porque ninguno tiene organismo de conocimiento conectado. Esto refuerza F:
lo propio sigue siendo capas 4-5, ahora con un argumento más fuerte (la pieza que
evita el estancamiento es exclusiva de Atlas). Nuevo riesgo R2: esa inyección
**aún no está cableada** → promesa hasta construirla (D2). Y R3: inmunidad no es
esterilizante (como la biológica, falla ante el novel hasta exponerse).
