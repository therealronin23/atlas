# Experimento de transferencia cross-family — memoria de patrones (1c-seguridad)

**Pregunta decisiva:** cuando la memoria abstrae lecciones en patrones (1b), ¿reconoce
familias de ataque NUNCA sembradas (transferencia = genera conocimiento) o solo
reformulaciones de lo visto (memoriza = enciclopedia)?

Reproducible: `scripts/redteam/transfer_experiment.py`. Cada patrón se ancla en cadena
Merkle (`verify_chain()=True`): se puede probar QUÉ se sembró y CUÁNDO.

Rigor acumulado (2026-06-21):
1. Umbral de *clustering* separado del de *recall* (un solo parámetro inflaba).
2. Control benigno FRONTERIZO (legítimo que roza el tema) además del fácil → estresa el
   suelo de falsos positivos.
3. **Corpus REAL de Garak** además del ilustrativo: cada probe = familia (ground-truth
   EXTERNO, evita filtrado circular). TRAIN: `promptinject.HijackHateHumans`,
   `phrasing.PastTense`. HELD-OUT: `web_injection.MarkdownURIImageExfilExtended`,
   `snowball.Primes` (mecanismos maximalmente distintos = test más duro).

## Resultado con CORPUS REAL de Garak (HF MiniLM, cluster 0.80, 20 prompts/familia)

| recall_thr | sanidad | **heldout** | benign_fp (fácil) | **borderline_fp** | margen |
|---|---|---|---|---|---|
| 0.70 | 100% | 0.0% | 0% | 0.0% | 0 |
| 0.65 | 100% | 27.1% | 0% | 16.7% | **+10.4** |
| 0.62 | 100% | 27.5% | 0% | 50.0% | −22.5 |
| 0.60 | 100% | 50.0% | 0% | 50.0% | 0 |
| 0.58 | 100% | 57.5% | 33% | 50.0% | +7.5 |
| 0.55 | 100% | 80.0% | 0% | 83.3% | −3.3 |

(margen = heldout − borderline_fp.) Léxico (stub) sobre el mismo corpus: heldout 0% →
memoriza puro.

## Veredicto consolidado (honesto)

**El corpus real CONFIRMA el hallazgo del ilustrativo, más crudo aún.** Con familias de
ataque reales y muy distintas:

- **No hay punto de operación usable.** El mejor margen heldout−borderline es solo **+10
  puntos** (recall 0.65: caza 27% de ataques nuevos a costa de 17% de falsos positivos
  fronterizos). En el resto del barrido el margen es ~0 o negativo (a 0.62 el sistema
  marca MÁS benigno fronterizo (50%) que ataques held-out (27%)).
- **El detector reconoce PROXIMIDAD TEMÁTICA, no "ataque-idad".** El FP fronterizo sube
  en paralelo al heldout. Coseno-a-centroide sobre patrones NO es un clasificador de
  intención fiable.
- **Lo que SÍ funciona, robusto:** la sanidad es 100% en todo el barrido → la memoria
  reconoce con fiabilidad reformulaciones de lo YA visto (near-duplicates auditables).
  Eso es su valor real y honesto, no la detección de familias nuevas.

**Implicación estratégica (con datos propios):** no apostar a la DETECCIÓN (el segundo
jugador gana; ver `project-adaptive-defense-reframe`). La memoria aporta **reconocimiento
AUDITABLE de variantes con procedencia en cadena**, no un antivirus. La transferencia
cross-family fuerte no la tiene nadie; aquí se MIDE su ausencia, no se disimula.

## Qué haría falta para una señal usable (futuro, NO prometido)

- Discriminación intención-vs-tema con contrastive learning (pares ataque/benigno-adyacente),
  no coseno crudo a centroide.
- Señal de trayectoria (drift) combinada con la de contenido.
- Sets mayores + intervalos de confianza (estos números son ruidosos: n pequeño).

## Límites declarados

- 20 prompts/familia, 6 benignos por set: señal cualitativa, sin IC; los saltos del
  benign_fp (0%→33%→0%) son ruido de muestra pequeña.
- Umbral de recall es propiedad del embedder (recalibrar por embedder).
