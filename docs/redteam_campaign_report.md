# Reporte de campaña red-team — Osmosis

<!-- Generado por scripts/redteam/garak_campaign.py (ADR-056). Reproducible. -->

Driver de ataque: **NVIDIA Garak** (corpus DanInTheWild + promptinject), 60
prompts de ataque reales. Cada petición pasa por un gateway Osmosis aislado
(co-firma bidireccional + log Merkle + tripwire de deriva + inspección acotada).

## Atribuibilidad (la afirmación propia)
| Métrica | Valor |
|---|---|
| C_attempts (ataques enviados) | 60 |
| K_attribution (inclusión verificada) | 60 |
| Tasa de atribución | 100.0% |

Cada intento queda en una cadena innegable: el operador no puede negar que la
petición ocurrió. No es bloqueo; es atribución verificable.

## Señal del monitor (metodología, NO tasa de detección de producto)
| Métrica | Valor |
|---|---|
| Ataques (en sesión benigna) con drift ≥ τ_passive (0.65) | 59/60 (98.3%) |
| Ataques con inspección+label (lista cerrada) | 0/60 |
| Falsos positivos benignos (drift ≥ τ) | 0/40 (0.0%) |
| Control benigno: inclusión verificada | 40/40 |

## Límites honestos
- Embedder = StubEmbedder (sin red); con embedder real la señal mejora.
- La señal NO es detección garantizada: un atacante lento/baja-varianza se queda
  bajo τ (sube su coste, no lo cierra). Falsos positivos por diseño → apelación.
- Una ráfaga sostenida normaliza la propia línea base de la sesión y la señal
  cae; por eso el caso medido es el ataque a mitad de sesión benigna (el diseñado).
- La detección depende del matcher de lista cerrada (básico). Esto mide
  medibilidad/metodología, no es un benchmark de producto.
