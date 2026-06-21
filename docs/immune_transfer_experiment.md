# Experimento de transferencia cross-family — memoria de patrones (1c-seguridad)

**Pregunta decisiva:** cuando la memoria abstrae lecciones en patrones (1b), ¿reconoce
familias de ataque NUNCA sembradas (transferencia = genera conocimiento) o solo
reformulaciones de lo visto (memoriza = enciclopedia)?

Reproducible: `scripts/redteam/transfer_experiment.py`. Familias TRAIN sembradas
(`instruction_override`, `persona_jailbreak`) vs HELD-OUT jamás vistas
(`exfiltration`, `encoding_evasion`). Cada patrón se ancla en cadena Merkle
(`verify_chain()=True`): se puede probar QUÉ se sembró y CUÁNDO.

**Refinamiento clave (2026-06-21):** se separó el umbral de *clustering* (cómo de
apretado se agrupan ejemplos en un patrón) del umbral de *recall* (cómo de cerca
debe estar una query para contar match). Antes eran el mismo parámetro → a 0.60 las
6 semillas colapsaban en 1 patrón ancho, inflando la transferencia. Ahora se agrupa
fino (cluster=0.80 → 2 patrones, uno por familia: abstracción limpia) y se calibra
solo el recall.

## Resultados

### Embedder léxico (StubEmbedder, 0 deps)
train 100% · **heldout 0%** · benign 0% → **MEMORIZA** (el léxico no cruza vocabularios
disjuntos). Esperado.

### Embedder semántico (all-MiniLM-L6-v2), clustering fino (0.80, 2 patrones), barrido de recall
| recall_thr | sanidad (train) | **heldout_recall** | benign_fp |
|---|---|---|---|
| 0.70 | 33.3% | 0.0% | 0.0% |
| 0.65 | 66.7% | 16.7% | 0.0% |
| **0.62** | **100.0%** | **16.7%** | 0.0% |
| 0.60 | 100.0% | 50.0% | 0.0% |
| 0.58 | 100.0% | 66.7% | 0.0% |

Punto de operación conservador = 0.62 (primer recall con sanidad 100%): **transferencia
16.7% con 0% FP**. Aflojando el recall, la transferencia sube (50%, 66.7%) mientras el
control benigno **se mantiene en 0%**: las familias held-out viven en una vecindad
semántica claramente distinta del tráfico benigno.

## Conclusión honesta

- **No es enciclopedia.** Con el confound de clustering eliminado, la transferencia
  cross-family sobrevive y es REAL: en un rango de operación con sanidad 100% y FP
  benigno 0%, el sistema reconoce entre el 17% y el 67% de ataques de familias NUNCA
  sembradas. El "intento adversarial" tiene una firma semántica que transfiere entre
  familias distintas.
- **No es generalización resuelta.** Es una frontera, no una cobertura: el rango
  depende del punto de operación, y la transferencia fuerte vs adversario adaptativo no
  la tiene nadie. Mostramos el mecanismo y **medimos su frontera**.
- Soporta la tesis ESTRECHA y honesta del proyecto: *transferencia medida con frontera
  explícita + procedencia verificable* — no "antivirus".

## Confounds y límites (declarar siempre)

1. **RESUELTO:** clustering vs recall ya están separados → el 50% a recall 0.60 no es
   artefacto de un patrón ancho (hay 2 patrones, uno por familia).
2. **Set benigno pequeño y fácil** (6 ejemplos, temáticamente lejanos: capitales,
   recetas, git). El 0% de FP es alentador pero NO está estresado: con benigno
   *fronterizo* (peticiones legítimas que rozan el tema de seguridad) el FP subiría al
   aflojar el recall. El suelo de FP necesita un set adversarialmente benigno.
3. **Semillas ilustrativas, no Garak real.** Siguiente paso riguroso: probes de Garak
   agrupados por su taxonomía (ground-truth EXTERNO de familia, evita filtrado circular).
4. **Conjuntos pequeños** (6/6): señal cualitativa, sin intervalo de confianza.
5. El umbral de recall es propiedad del embedder (MiniLM mapea distinto al stub); debe
   recalibrarse por embedder, no es un número universal.
