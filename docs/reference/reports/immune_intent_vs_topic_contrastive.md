# Muro intención-vs-tema — ataque por contrastive de prototipos (tipo-3)

**El muro (hallazgo de 1c):** el recall por coseno-a-centroide reconoce PROXIMIDAD
TEMÁTICA, no "ataque-idad" → confunde ataques cross-family con benigno legítimo que
roza el tema. ¿Se puede rodear sin entrenar nada?

**El ataque (falsable, sin deps):** *contrastive por prototipos.* Sembrar prototipos
de ATAQUE y de BENIGNO-adyacente y clasificar por **margen** `sim(ataque) − sim(benigno)`
en vez de "cercanía a ataque" a secas. Sin fuga: los prototipos benignos se siembran de
`BENIGN_TRAIN`, el FP se mide sobre `BORDERLINE_BENIGN` (conjuntos distintos).
Reproducible: `transfer_experiment.py --scorer contrastive --margin M`.

## Resultado (HF MiniLM, corpus Garak real, held-out por familia)

| scorer | heldout_recall | borderline_fp | **gap (ho − bo)** |
|---|---|---|---|
| coseno (baseline 1c, recall 0.62) | 50% | 33% | **+17** |
| contrastive, margin 0.02 | 90% | 33% | **+57** |
| contrastive, margin 0.05 | 58% | 33% | **+25** |

(sanidad train = 100% en todos.) Métrica robusta = el **gap**; los FP absolutos son
ruidosos (sets benignos de 6).

## Veredicto honesto: el muro se MOVIÓ, no cayó

- **La hipótesis era correcta.** El contrastive **duplica/triplica la separación**
  intención-vs-tema (gap +17 → +25–57). El mecanismo ayuda de verdad: mirar la distancia
  RELATIVA a benigno, no solo a ataque, recupera parte de la "intención" que el coseno
  crudo pierde.
- **Pero no es un detector usable.** El `borderline_fp` se queda en ~33% en los puntos de
  operación con recall alto. Rodeamos PARTE del muro; sigue habiendo muro. La detección de
  intención fiable a FP bajo NO está resuelta — aquí tampoco.
- **Disciplina:** en un barrido previo salió `borderline_fp=0%` a margin 0.05; con más
  variantes (15 vs 5) se reveló ~33% → era SUERTE DE MUESTRA PEQUEÑA. No cantar victoria con
  n pequeño; el 0% no era real.

## Implicación

Confirma la dirección maestra: la memoria aporta **separación parcial y medible** con
procedencia auditable, no un clasificador de intención. El contrastive es una mejora real
del eje de detección, pero el eje ganador sigue siendo **atribución + contención +
auditabilidad** (`project-adaptive-defense-reframe`), no la detección.

## Límites declarados

- Sets benignos pequeños (6) → FP absolutos ruidosos; el **gap** es la señal, no el FP exacto.
- El contrastive exige MANTENER prototipos benignos (cobertura = problema móvil propio).
- Familias Garak ilustrativas del split; sin intervalos de confianza.
- Margen calibrado por embedder (como el umbral de recall).
