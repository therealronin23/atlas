# Red-team & defense demos — reproducibility

<!-- Doc interno (dev/red-team). NO es entregable público (menciona detalles internos). -->

Cuatro demos reproducibles que respaldan el Apéndice B del paper. Todas corren en
un `ATLAS_HOME` temporal aislado (nunca contra el servicio vivo) y miden sobre el
log co-firmado. **No son benchmarks de producto**: miden atribución y metodología.

## Requisitos

```bash
# venv aislado de tooling (NO entra en las deps del paquete; ADR-056)
python3 -m venv .venv-redteam
.venv-redteam/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-redteam/bin/pip install garak pyrit
# atacante/maestro vía API: las claves se leen de .env (GROQ_API_KEY, NVIDIA_API_KEY)
```

Todas se ejecutan con `PYTHONPATH=src .venv-redteam/bin/python ...`.

## Demos

| Script | Qué mide | Cifra de la corrida de referencia |
|---|---|---|
| `garak_campaign.py` | Atribución bajo ataque (corpus Garak → gateway aislado) | C=60, K=60 → **100% inclusión verificada**; FP benignos 0/40 |
| `generalization_curve.py` | Frontera de generalización de la memoria inmune + control de FP | léxico rompe d=0.7; **semántico sin ruptura en [0,1]**, FP 0/8 |
| `pyrit_crescendo.py` | Multi-turn adaptativo (PyRIT Crescendo, atacante API) → trayectoria del tripwire | gradual evade; salto brusco dispara; **atribución 100%/turno** |
| `frontier_debate.py` | Maestro propone lecciones → el sistema arbitra (corrobora/contradice/acepta) | contradice al maestro cuando afirma que un ataque conocido es benigno |

Ejemplos:

```bash
PYTHONPATH=src .venv-redteam/bin/python scripts/redteam/garak_campaign.py --attacks 60 --benign 40 --out docs/audits/reports/redteam_campaign_report.md
PYTHONPATH=src .venv-redteam/bin/python scripts/redteam/generalization_curve.py --embedder hf --threshold 0.7 --out docs/audits/reports/immune_generalization_curve.md
CRESCENDO_OUT=docs/audits/reports/pyrit_crescendo_report.md PYTHONPATH=src .venv-redteam/bin/python scripts/redteam/pyrit_crescendo.py
TEACHER_PROVIDER=nvidia DEBATE_OUT=docs/audits/reports/frontier_debate_report.md PYTHONPATH=src .venv-redteam/bin/python scripts/redteam/frontier_debate.py
```

## Límites honestos (válidos para todas)

- El "modelo objetivo" suele ser un stub: se mide el canal de seguridad, no contenido.
- Embedder/atacante/maestro estocásticos → cifras *ilustrativas de una corrida*, no benchmark.
- Cubren reformulación/atribución, **no** robustez frente a familias de ataque nuevas.
- Los reportes generados (`docs/*report*.md`, `docs/audits/reports/immune_generalization_curve.md`) son
  artefactos reproducibles, no afirmaciones de cobertura.
