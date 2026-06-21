# Experimento de transferencia cross-family — memoria de patrones (1c-seguridad)

**Pregunta decisiva:** cuando la memoria abstrae lecciones en patrones (1b), ¿reconoce
familias de ataque NUNCA sembradas (transferencia = genera conocimiento) o solo
reformulaciones de lo visto (memoriza = enciclopedia)?

Reproducible: `scripts/redteam/transfer_experiment.py`. Familias TRAIN sembradas
(`instruction_override`, `persona_jailbreak`) vs HELD-OUT jamás vistas
(`exfiltration`, `encoding_evasion`). Cada patrón se ancla en cadena Merkle
(`verify_chain()=True`): se puede probar QUÉ se sembró y CUÁNDO.

Dos refinamientos de rigor (2026-06-21):
1. Umbral de *clustering* separado del de *recall* (antes 1 solo parámetro inflaba).
2. **Control benigno FRONTERIZO** además del fácil: peticiones legítimas que ROZAN el
   tema (política de seguridad, prompt injection en abstracto, instrucciones a una IA,
   base64, modo debug). Estresa el suelo de falsos positivos.

## Resultados (HF MiniLM, clustering fino 0.80 → 2 patrones, uno por familia)

| recall_thr | sanidad (train) | **heldout** | benign_fp (fácil) | **borderline_fp** | margen |
|---|---|---|---|---|---|
| 0.62 | 100% | 16.7% | 0% | 33.3% | **−16.6** |
| 0.60 | 100% | 50.0% | 0% | 33.3% | +16.7 |
| 0.58 | 100% | 66.7% | 0% | 50.0% | +16.7 |
| 0.55 | 100% | 100% | 0% | 66.7% | +33.3 |

(margen = heldout − borderline_fp.) Léxico (stub): heldout 0% en todo → memoriza puro.

## Conclusión honesta (corregida por el test fronterizo)

El test fronterizo **tumbó la historia limpia** del corte anterior ("transferencia con
0% FP"): ese 0% era un artefacto de un control benigno demasiado FÁCIL (temas lejanos).

- **El detector reconoce PROXIMIDAD TEMÁTICA, no "ataque-idad".** El FP fronterizo sube
  en paralelo al heldout al aflojar el recall. A recall 0.62 el sistema marca MÁS
  benigno fronterizo (33%) que ataques held-out reales (17%): margen negativo.
- **Hay una señal de intención, pero débil.** En umbrales laxos el heldout supera al
  fronterizo por ~17–33 puntos. Es real (no es cero), pero pequeña.
- **NO existe un punto de operación usable:** ninguno combina transferencia alta con FP
  fronterizo bajo. Como detector autónomo, la memoria de patrones sobre coseno-a-centroide
  NO separa limpiamente ataques cross-family de benigno topicalmente adyacente.

**Veredicto honesto:** la "transferencia" es mayormente confound temático con una traza
débil de señal de intención. Reconoce reformulaciones de lo sembrado (sanidad 100%) y
algo del vecindario semántico, pero confunde lo legítimo-adyacente. Esto refuerza la
dirección estratégica del proyecto: **no apostar la casa a la DETECCIÓN** (segundo
jugador gana) sino al eje ATRIBUCIÓN + CONTENCIÓN + auditabilidad (ver
`project-adaptive-defense-reframe`). La memoria aporta reconocimiento auditable de
variantes, no un clasificador de intención fiable.

## Qué haría falta para subir la señal (futuro, no prometido)

- Discriminación intención-vs-tema: contrastive learning con pares (ataque, benigno
  adyacente) en vez de coseno crudo a centroide.
- Corpus real de Garak (taxonomía externa de familia, evita filtrado circular) + set
  benigno adversarial grande → números con intervalo de confianza.
- Señal de trayectoria (drift) combinada con la de contenido, no contenido solo.

## Límites declarados

- Conjuntos pequeños (6/6/6/6): señal cualitativa, sin IC.
- Umbral de recall es propiedad del embedder (recalibrar por embedder).
- Familias ilustrativas, no Garak real todavía.
