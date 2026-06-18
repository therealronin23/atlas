# OSM-054 — Behavioral Drift Detection: Tres ángulos de observación + investigación

Fecha: 2026-06-18 · Estado: **Difusión** (investigación en curso) ·
Origen: Respuesta a 6.10 paper (post-inspection capability masking) ·
Contexto: `src/atlas/security/behavioral.py`, paper §6.11, Session J demo ·
Referencias: [[OSM-042]] (shadow model), [[OSM-028]] (causa de inspección).

---

## Contexto

La fase 2 (output inspection completa) garantiza que toda inspección se realizó y quedó
registrada en el log de forma verificable. Sin embargo, **no cierra behavioral
faithfulness**: un modelo podría pasar la inspección ("decision: allow") y luego
degradarse silenciosamente en respuestas — mascaramiento de capacidad post-inspección.

Este límite honesto (§6.10, paper) es irreductible a nivel del protocolo. Pero existen
**tres ángulos de observación** independientes que, combinados, pueden servir como
señales de investigación (no cierre absoluto).

---

## La idea

### Tres ángulos (A, B, C)

#### A — Behavioral Delta: observación de cambios frente a baseline

Mantener un conjunto de "canary prompts" — preguntas reveladores de capacidad, inmutables.

En un tiempo T₀ capturar un baseline: ejecutar cada canary, registrar:
- Hash SHA-256 de la respuesta
- Latencia (ms)

En tiempo T₁, repetir y comparar:
- content_changed: baseline_hash ≠ actual_hash
- latency_delta_ms: (actual − baseline)

Un BehavioralDelta es "anómalo" si content_changed ∨ |latency_delta| > 100 ms.

**Falsos positivos:** cambios legítimos de wording en la respuesta (fixes, recalibración
de tone); cambios en latencia por sobrecarga del servidor.

**Falsos negativos:** degradación sutil (token probability reducida <1%, respuesta
técnicamente correcta pero más cautelosa); capability masking que no afecta canaries
elegidas.

**v0, probabilístico.** No detecta con certeza. Señal de alerta temprana.

#### B — Ex-post Consistency Proof (open problem)

Complemento teórico: si el modelo está formalmente prohibido de output X, ¿podemos
probar retroactivamente que todas sus respuestas son consistentes con esa prohibición?

```
¿Existe restricción implícita R?
  → Recolectar todas las respuestas del modelo al conjunto de prompts P.
  → ¿Son consistentes con R?
  → Inferir presencia de R.
```

**El problema abierto:** la respuesta es underconstrained. Múltiples restricciones R₁,
R₂, ... son compatibles con el mismo historial de respuestas. No hay forma de elegir
una única R canónica sin hipótesis adicionales sobre la semántica del modelo.

Esta línea es investigación pura. No implementada.

#### C — Shadow Divergence: comparativo real vs. shadow (OSM-042)

Desplegar un modelo "shadow" (mismo setup, opcionalmente sin las restricciones
sospechadas). Ejecutar ambos sobre los mismos canaries.

```
real_hash = SHA-256(real_respond(canary_i))
shadow_hash = SHA-256(shadow_respond(canary_i))
divergence = (real_hash ≠ shadow_hash)
```

Si la divergencia es alta en muchos canaries, sugiere que el modelo real está
degradando respuestas intencionalmente.

**El falso positivo conocido (OSM-042):** el shadow típicamente usa un system prompt
distinto al real (diseño por defecto). Diferencias en tono, formalidad, rigor son
legítimas, no prueba de mascaramiento.

**Contexto necesario:** una ingeniería cuidadosa del shadow (matching system prompt
cuando sea posible, o separación explícita de "tono" de "contenido") reduce ruido.

---

## Encaje en Atlas

### Implementación

| Componente | Ubicación | Rol |
|---|---|---|
| `CanaryPrompt` | `src/atlas/security/behavioral.py` | Prompt inmutable + capability objetivo |
| `DEFAULT_CANARIES` | `src/atlas/security/behavioral.py` | 3 sondas builtin (self-awareness, refusal, harmful-info) |
| `capture_baseline()` | `src/atlas/security/behavioral.py` | Captura T₀ de hashes + latencias |
| `BehavioralMonitor` | `src/atlas/security/behavioral.py` | Ejecuta canaries, compara con baseline |
| `detect_covert_change()` | `src/atlas/security/behavioral.py` | Filtra deltas anómalos (ángulo A) |
| `shadow_divergence()` | `src/atlas/security/behavioral.py` | Compara real vs. shadow (ángulo C) |

### Capas y bucles

**Capa de investigación:** los ángulos A y C son herramientas de observación,
típicamente ejecutadas en modo manual o en cron periódico. No cierran ningún veredicto
automático.

**Integración con red team (OSM-042):** el componente shadow de OSM-042 puede
alimentarse con canaries de OSM-054. Si shadow_divergence detecta divergencia elevada,
la firma se escala a revisión de especialista humano.

**Bucle de captura:** en modo de auditoría, cada sesión puede capturar baselines
antes/después de cambios de política. Comparación posterior revela impacto conductual.

---

## Correcciones de verificación

1. ✓ `detect_covert_change()` actualizado: docstring honesto sobre heurística v0 y
   falsos positivos/negativos.
2. ✓ `shadow_divergence()` actualizado: mención explícita de falso positivo conocido
   (system prompt distinto = divergencia legítima).
3. ✓ Módulo docstring: referencia a "tres ángulos", v0, "no cierra behavioral
   faithfulness."
4. ✓ Paper §6.11 integrado: 300 palabras, enlaza a behavioral.py, marca como
   future work / open problem.

---

## Criterios de compuerta

Antes de escalar OSM-054 como cierre de behavioral faithfulness:

- [ ] Demostración de ángulo B (ex-post consistency proof) con resultado afirmativo
  o rechazo formal.
- [ ] Validación de tasa de falsos positivos en ángulo A (A1 — ¿qué % de canaries
  se ven afectadas por cambios legítimos?).
- [ ] Calibración del shadow en ángulo C: separación clara de system prompt effects
  de capability effects.
- [ ] Integración con red team real (OSM-042) en modo live: ¿escaladas a humanos
  coinciden con verdaderos cambios conductuales detectados offline?

---

## Límites honestos

**No cierra behavioral faithfulness.** Los tres ángulos son observacionales,
probabilísticos, para investigación. No garantizan detección ni cierran el espacio de
posibles restricciones covert.

**Ángulo A — Falsos positivos/negativos alto.** Un modelo legítimamente mejorado
fallará canaries elegidas arbitrariamente. Una restricción sutil (probabilidad de
token reducida <1%) pasará desapercibida.

**Ángulo B — Underconstrained.** Múltiples restricciones son compatibles con el
mismo histórico. Elegir una canónica requiere hipótesis semánticas que están fuera
del alcance de la prueba.

**Ángulo C — Ruido del shadow.** System prompt diferente genera divergencia legítima.
Solo se puede aislar capability masking con un shadow perfectamente alineado, lo cual
es imposible sin acceso a los pesos exactos.

**Caso de uso real:** Este es un conjunto de herramientas para especialistas de
seguridad investigando sospechas de degeneración de modelo, no un detector automático
apto para producción.

---

## Referencias

- `src/atlas/security/behavioral.py` — implementación A + C
- Papel §6.11 — límites honestos de behavioral drift
- [[OSM-042]] — shadow model (base para ángulo C)
- Session J, demo completeness — integración con harness de prueba
