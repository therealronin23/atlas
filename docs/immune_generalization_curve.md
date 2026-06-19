# Curva de generalización de la memoria inmune — Osmosis

<!-- Generado por scripts/redteam/generalization_curve.py (PASO 2). Reproducible. -->

Mide hasta dónde el reconocimiento de reformulaciones generaliza desde un ataque
visto y **dónde se rompe**. Semillas: 5; 20
variantes/semilla/distancia; umbral de reconocimiento 0.8.

## Curva (distancia de mutación → tasa de reconocimiento)
| distancia | reconocimiento |
|---|---|
| 0.0 | 100.0% |
| 0.1 | 100.0% |
| 0.2 | 100.0% |
| 0.3 | 100.0% |
| 0.4 | 100.0% |
| 0.5 | 100.0% |
| 0.6 | 59.0% |
| 0.7 | 54.0% |
| 0.8 | 40.0% |
| 0.9 | 22.0% |
| 1.0 | 16.0% |

**Punto de ruptura (recall < 50%): d=0.8**

## Procedencia auditable
Cadena Merkle de lecciones: **VERIFICADA**.
Cada lección sembrada queda anclada en el log → se puede probar qué se aprendió y
cuándo. Esto es el eje propio: adaptación verificable, no robustez bruta.

## Límites honestos
- Embedder = StubEmbedder (léxico-ish, sin red); la semántica real requiere un
  embedder real (inyectable, p.ej. LiteLLMEmbedder).
- Cubre **reformulación** de lo visto, **no** familias genuinamente nuevas.
- La curva **cae** con la distancia por diseño: es el límite medido, no un fallo.
- Lo puntero no es la tasa absoluta, sino que la adaptación es **verificable** y su
  **frontera está medida y publicada** — la mayoría de defensas la esconden.
