# ADR-054 — Antivirus inmune para IA: malla de evidencia verificable + memoria adaptativa

Fecha: 2026-06-15 · Estado: **Propuesto** (v3, tras investigación de estado del
arte e implementaciones reales) · Resuelve C1 de
`audit_adr051_052_premortem_2026-06-15.md` · Contexto: ADR-051, ADR-053, ADR-049,
ADR-048, ADR-044, ADR-040, ADR-036.

> **Tesis central:** el "antivirus para IA" NO es el clasificador. El motor de
> escaneo es commodity intercambiable — igual que en el antivirus tradicional.
> El producto es la **malla de evidencia verificable en ambos sentidos + la
> memoria inmune que aprende de cada campaña sin colapsar en diversidad**. Esa
> combinación no existe implementada en ningún sistema en producción hoy
> (verificado 2026-06-15: solo Anthropic CC++ y Microsoft Azure AI Content
> Safety han cruzado la brecha paper→producción, y ninguno tiene verificabilidad
> mutua ni memoria inmune con diversidad externa).

---

## Estado del arte real (verificado 2026-06-15, no solo papers)

**Lo que está en producción:**
- **CC++ (Anthropic)**: cascada probe-ligero → clasificador externo. Shadow
  deployment sobre Claude Sonnet 4.5 dic-2025/ene-2026. La mejor defensa existente.
  El propio paper admite: sin test sistemático contra búsqueda adaptativa de
  jailbreak.
- **Azure AI Content Safety / Prompt Shields (Microsoft)**: guardrails en capa
  de infraestructura. Productivo.
- **Bifrost (Maxim AI, open source)**: AI gateway en Go con guardrails en capa
  de infraestructura.

**Lo que existe SOLO como paper/demo sin producción:**
- HoneyTrap (arXiv:2601.04034): sin repo público encontrado.
- IMAG immune memory (arXiv:2512.03356): sin repo público encontrado.
- FlexLLM/MTD (arXiv:2412.07672): sin repo público encontrado.
- CHASE/co-evolución (arXiv:2606.05523): paper de jun-2026, sin código.
- JailDAM (arXiv:2504.03770): único con repo (github.com/ShenzheZhu/JailDAM),
  pero es demo de investigación (Jupyter notebook + descarga manual de datos).

**Hallazgo clave — LLM Salting (Sophos, CAMLIS 2025):**
El comportamiento de rechazo de un LLM está controlado por una única dirección
en el espacio de activaciones. Sophos descubrió que una rotación pequeña y
dirigida de esa dirección invalida **todos** los jailbreaks precomputados contra
esa instancia — el atacante debe re-optimizar desde cero para cada instancia
salted. Sin coste computacional. Equivalente exacto al salt criptográfico contra
rainbow tables. Sin repo público pero con demostración en conferencia.

> **Conclusión del estado del arte:** la brecha paper→producción solo la han
> cruzado Anthropic y Microsoft. Las piezas más prometedoras (honeypot,
> inmunidad adaptativa, salting) existen como investigación sin implementación
> desplegada. Atlas puede ser el primero en integrarlas como sistema vivo.

---

## Disciplina de honestidad (invariante de este ADR)

Los números 94% / 68.77% / 43.2% salen de demos académicos en benchmarks, sin
presión adversarial adaptativa independiente. *The Attacker Moves Second*
[arXiv:2510.09023, verified 2026-06-18] demostró que exactamente esa clase de
número colapsa bajo ataque real. **Este ADR no reclama ninguna tasa de detección.
Nunca.**

---

## Las cuatro capas (L1–L4)

| Capa | Pieza | Origen | Build/Integrar | Límite honesto |
|---|---|---|---|---|
| **L1** | CC++ cascade | Anthropic (producción) | **Integrar** tras `ClassifierCascade` Protocol | bypass alto adaptativo |
| **L2** | **Polimorfismo causal + salting + log verificable** | LLM Salting (Sophos 2025) + ADR-053 | **Integrar** LLM Salting tras `SessionSalt` Protocol; log ya construido (1679 tests) | requiere acceso a activaciones; en API pura = hiperparámetros (FlexLLM); Session J (behavioral drift) registrada en L4 |
| **L3** | Señuelo + forense + gossip + evasion detection | HoneyTrap-style + RFC 9162 witnesses + ADR-053 L3c | **Stub** software para honeypot; activar solo tras causa confirmada (I1); witnesses integrados en L3b | cae ante sonda verificable (R1); L3c requiere baseline histórica |
| **L4** | **Log de campaña verificable + memoria inmune + diversidad externa** | **ADR-053 (log) + ADR-044 (lessons) + ADR-049 (conocimiento externo)** | **Ya construido** (1679 tests); build candidato para ADR-049 → ADR-054 feedback loop | no detecta per se; encarece + atribuye + aprende sin colapsar en diversidad (Session J observa drift) |

**El valor propio está en las capas 4 y 5 — las únicas no disponibles en ningún
sistema existente.**

### L2 ampliada: LLM Salting + co-firma monótona + log verificable (la combinación nueva)

El salt de cada sesión se registra en el log de ADR-053 como evento de configuración.
Consecuencias:
- El atacante no puede precomputar jailbreaks: cada sesión tiene superficie diferente.
- El log prueba que cada sesión tuvo su salt único → el operador no puede silenciosamente
  reutilizar la misma superficie para diferentes usuarios.
- El usuario puede verificar que su sesión fue efectivamente salted (su mitad del log).
Esta combinación (salt causal + log verificable) no está en ningún paper.

### L4: el lazo que no colapsa (memoria inmune + diversidad externa)

```
bypass observado / ataque externo (ADR-049)
         ↓
   LessonStore (ADR-044): lección con avoid_pattern + detection_heuristic
         ↓
   Panel adversarial (ADR-048): verifica que la lección generaliza
         ↓
   Decider/PDP (ADR-040): aprueba promoción a regla activa (I5)
         ↓
   Capa 1 mejorada → nuevo ciclo
         ↑
   Organismo de conocimiento (ADR-049): inyecta ataques externos nuevos
   [esto es lo que aporta diversidad externa que el auto-juego no genera]
```

El entrenamiento adversarial tiende a sobreajustarse a distribuciones de ataque
estrechas. CHASE (arXiv:2606.05523) lo aborda con co-evolución atacante-defensor,
pero requiere que el atacante mantenga diversidad de técnicas. El punto estructural
se mantiene: sin una fuente externa de diversidad de ataque, el defensor se estanca
en lo que ya vio. El organismo de conocimiento (ADR-049) es esa fuente externa. **Ningún
sistema publicado tiene esto porque ninguno tiene un organismo de conocimiento.**

---

## Invariantes

- **I1** — Señuelo (capa 3) solo tras causa confirmada. FP → bloqueo+alerta, no engaño.
- **I2** — Todo disparo de cualquier capa es evento registrable en ADR-053.
- **I3** — La memoria inmune (capa 5) aprende de ataques, nunca del contenido del usuario legítimo.
- **I4** — Ninguna capa reporta tasa de detección. La métrica es de campaña, no de intento:
  **C_attempts** (intentos co-firmados registrados antes del primer éxito de bypass),
  **C_sessions** (sesiones distintas consumidas, medible cuando capa 2 activa),
  **K_attribution** (umbral: ≥3 intentos consecutivos con similitud de patrón >0.7 → campaña flagged).
  Falsable: la defensa fue eficaz si el atacante necesitó C_attempts ≥ K_attribution antes de bypass;
  ineficaz si el bypass ocurrió en intento 1 (sin trail inocultable). Nunca un porcentaje de bloqueo.
- **I5** — Promover lección a regla activa pasa por el Decider (PDP) con tier ≥ MEDIUM. En modo autónomo
  (ATLAS_DECIDER=autonomous), el AutonomousDecider puede aprobar tier=LOW (reversible sin efecto en superficie
  de rechazo); una promoción que amplíe o restrinja la superficie de rechazo es tier=MEDIUM o superior y
  requiere revisión explícita (HumanDecider o hybrid). Sin auto-promoción silenciosa de tier MEDIUM+.

---

## Riesgos

- **R1** — Sonda verificable vacía el señuelo en dominio verificable (ciberofensiva).
  La capa 3 vale por la causa/forense que genera, no por engañar al adversario serio.
- **R2** — Sin ADR-049 cableado al red-team, el defensor se sobreajusta a distribuciones de ataque estrechas (CHASE, arXiv:2606.05523).
  Es la pieza de cierre crítica.
- **R3** — Inmunidad no es esterilizante: falla ante el ataque verdaderamente novel
  hasta exponerse. No se promete inmunidad total.
- **R4** — Acceso a activaciones para salting real requiere acceso al modelo en inferencia. Nemotron
  (modelo primario v0.12.0) es vía API externa — no hay acceso a activaciones. La implementación
  real de capa 2 es FlexLLM (randomización de hiperparámetros de decodificación por sesión):
  protección más débil que salting sobre activaciones, pero el único camino sin modelo self-hosted.
- **R5** — El witness network (protección split-view, RFC 9162) está diferido (no hay actores externos
  disponibles ahora). La protección de completitud actual funciona por co-firma del cliente con secuencia
  monótona: el usuario detecta lagunas unilateralmente. Split-view requiere ≥1 witness externo —
  límite honesto mientras sea single-node.
- **R5** — Coste de mantener capas 1-3 externas actualizadas (mitigado por ADR-049).

---

## Alcance de build

| Qué construir | Por qué |
|---|---|
| `SessionSalt` Protocol + impl software + registro en ADR-053 | Cierra capa 2 + la hace verificable; combinación nueva |
| `ArtifactKind.DECOY` + verificador (plausible ∧ inútil) + gating I1 | Cierra capa 3 correctamente |
| Lección de bypass → restricción de productor (LessonStore→ADR-048) | Cierra núcleo de capa 5 |
| Cableado ADR-049 → panel adversarial (diversidad externa) | Cierra R2; la pieza exclusiva |
| Métrica de campaña falsable (coste/atribución/diversidad) | Sin esto I4 es retórica |
| `ClassifierCascade` Protocol + stub software | Capa 1 tras interfaz sin reimplementar CC++ |

No construir: CC++ real, MTD real, HoneyTrap completo. Son motores intercambiables.

## Criterios de aceptación del núcleo

1. Señuelo sin causa confirmada → imposible (I1). Test.
2. Todo disparo → entrada co-firmada inocultable en ADR-053 (I2). Test.
3. Salt de sesión → registrado verificablemente; sesiones distintas tienen salts distintos. Test.
4. Bypass observado → lección → restricción de productor verificable en siguiente ciclo (capa 5). Test rojo/verde.
5. Promoción de lección a regla activa con cambio en superficie de rechazo (tier MEDIUM+) → pasa por
   Decider (I5). Test: AutonomousDecider rechaza auto-promover una lección que amplíe la superficie.
6. Métrica de campaña reportada, nunca tasa de detección (I4). Test de contrato de output.
