# Experimento de transferencia cross-family — memoria de patrones (1c-seguridad)

**Pregunta decisiva:** cuando la memoria abstrae lecciones en patrones (1b), ¿reconoce
familias de ataque NUNCA sembradas (transferencia = genera conocimiento) o solo
reformulaciones de lo visto (memoriza = enciclopedia)?

Reproducible: `scripts/redteam/transfer_experiment.py`. Familias TRAIN sembradas
(`instruction_override`, `persona_jailbreak`) vs HELD-OUT jamás vistas
(`exfiltration`, `encoding_evasion`). Cada patrón se ancla en cadena Merkle
(`verify_chain()=True`): se puede probar QUÉ se sembró y CUÁNDO.

## Resultados

### Embedder léxico (StubEmbedder, 0 deps), umbral 0.8
| Medida | Recall |
|---|---|
| train_variant_recall | 100.0% |
| **heldout_recall** | **0.0%** |
| benign_fp | 0.0% |

Lectura: el mecanismo reconoce perfectamente lo sembrado y sus reformulaciones, pero
**cero transferencia** a familias nuevas. Esperado: el léxico no cruza vocabularios
disjuntos. Veredicto léxico = **MEMORIZA**.

### Embedder semántico (all-MiniLM-L6-v2), barrido de umbral
El coseno mapeado de MiniLM se distribuye distinto al stub → el umbral 0.8 está
mal calibrado (la sanidad cae a 16.7%, lo que invalidaría cualquier lectura). Se
barre hasta el punto donde la sanidad es sana:

| umbral | nº patrones | train_recall (sanidad) | **heldout_recall** | benign_fp |
|---|---|---|---|---|
| 0.80 | 2 | 16.7% | 0.0% | 0.0% |
| 0.75 | 1 | 16.7% | 0.0% | 0.0% |
| 0.70 | 1 | 16.7% | 0.0% | 0.0% |
| 0.65 | 1 | 50.0% | 16.7% | 0.0% |
| **0.60** | 1 | **100.0%** | **33.3%** | **0.0%** |

En el punto de operación calibrado (umbral 0.60, sanidad 100%): **heldout_recall =
33.3% con benign_fp = 0%**. La transferencia NO es ruido (el control benigno se
queda en 0%); las familias held-out están semánticamente más cerca del concepto de
ataque sembrado que el tráfico benigno.

## Conclusión honesta

- **No es enciclopedia pura.** Con embeddings semánticos y umbral calibrado hay una
  señal de transferencia cross-family REAL y medible (~33%) con cero falsos positivos
  benignos. El "intento adversarial" tiene una vecindad semántica que transfiere algo
  entre familias distintas.
- **No es generalización resuelta.** 33% está lejos de cubrir familias nuevas; la
  transferencia fuerte contra adversario adaptativo no la tiene nadie y nosotros
  tampoco. Mostramos el mecanismo y **medimos su frontera**, no prometemos cobertura.
- Esto soporta la tesis del proyecto en su versión ESTRECHA y honesta: *transferencia
  medida con frontera explícita, anclada en procedencia verificable* — no "antivirus".

## Confounds y límites (declarar siempre)

1. **Umbral de clustering == umbral de recall** en esta versión: a 0.60 las 6 semillas
   colapsan en 1 patrón ancho, lo que facilita tanto el match como el recall. Separar
   ambos umbrales es el siguiente refinamiento; hasta entonces el 33% es un techo
   optimista, no una medida limpia.
2. **Familias y semillas ilustrativas**, no el corpus real de Garak. El siguiente paso
   riguroso: sustituir por probes de Garak (DanInTheWild/promptinject) agrupados por su
   taxonomía (ground-truth EXTERNO de "familia", evita filtrado circular), bajo
   `.venv-redteam`.
3. **Conjuntos pequeños** (6 train, 6 held-out, 6 benign): suficiente para señal
   cualitativa, insuficiente para un número con intervalo de confianza.
4. El mutador (distancia 0.15) corrompe más el embedding semántico que el léxico → el
   umbral semántico necesita ser más laxo solo para la sanidad; esto es propiedad del
   embedder, no del mecanismo.
