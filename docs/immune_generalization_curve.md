# Curva de generalización de la memoria inmune — Osmosis

<!-- Generado por scripts/redteam/generalization_curve.py (PASO 2). Reproducible. -->

Mide hasta dónde el reconocimiento de reformulaciones generaliza desde un ataque
visto y **dónde se rompe**. Embedder: **hf**; semillas: 5;
20 variantes/semilla/distancia; umbral de reconocimiento 0.6.

## Curva (distancia de mutación → tasa de reconocimiento)
| distancia | reconocimiento |
|---|---|
| 0.0 | 100.0% |
| 0.1 | 100.0% |
| 0.2 | 100.0% |
| 0.3 | 100.0% |
| 0.4 | 100.0% |
| 0.5 | 100.0% |
| 0.6 | 99.0% |
| 0.7 | 98.0% |
| 0.8 | 94.0% |
| 0.9 | 94.0% |
| 1.0 | 93.0% |

**Punto de ruptura (recall < 50%): no alcanzado en [0,1]**

## Control de falsos positivos (mismo umbral 0.6)
Texto benigno NO relacionado que matchea: **0/8 (0.0%)**.
Recall alto **solo vale con FP bajo**: si lo benigno también matcheara, la
"generalización" sería un umbral flojo, no reconocimiento real. (N pequeño: 8
controles; es un sanity-check, no un benchmark.)

## Procedencia auditable
Cadena Merkle de lecciones: **VERIFICADA**.
Cada lección sembrada queda anclada en el log → se puede probar qué se aprendió y
cuándo. Esto es el eje propio: adaptación verificable, no robustez bruta.

## Límites honestos
- Embedder = all-MiniLM-L6-v2 local (semántico, sin clave API) (inyectable). El léxico (StubEmbedder) se rompe pronto;
  el semántico generaliza mucho más — la curva de arriba depende de cuál se use.
- La generalización medida es frente a NUESTRO mutador determinista (sinónimos,
  leetspeak, reordenación); un adversario real muta de otras formas.
- El control de FP tiene N pequeño: sanity-check, no benchmark de producto.
- Cubre **reformulación** de lo visto, **no** familias genuinamente nuevas.
- La curva **cae** con la distancia por diseño: es el límite medido, no un fallo.
- Lo puntero no es la tasa absoluta, sino que la adaptación es **verificable** y su
  **frontera está medida y publicada** — la mayoría de defensas la esconden.
