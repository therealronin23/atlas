# Red-team & defense demos — reproducibility

<!-- Doc interno (dev/red-team). NO es entregable público (menciona detalles internos). -->

Cuatro demos reproducibles que respaldan el Apéndice B del paper. Todas corren en
un `ATLAS_HOME` temporal aislado (nunca contra el servicio vivo) y miden sobre el
log co-firmado. **No son benchmarks de producto**: miden atribución y metodología.

## Requisitos

```bash
# Dos venvs aislados: sus rangos de `datasets` son incompatibles (ADR-056).
python3 -m venv .venv-redteam-garak
.venv-redteam-garak/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-redteam-garak/bin/pip install -e '.[redteam-garak]'

python3 -m venv .venv-redteam-pyrit
.venv-redteam-pyrit/bin/pip install -e '.[redteam-pyrit]'
# atacante/maestro vía API: las claves se leen de .env (GROQ_API_KEY, NVIDIA_API_KEY)
```

Las campañas Garak usan `.venv-redteam-garak`; Crescendo usa
`.venv-redteam-pyrit`. Las demos sin esas herramientas pueden usar el venv principal.

> **ESTADO REAL DE ESTA MÁQUINA (medido el 2026-08-10) — leer antes de correr nada.**
>
> Ninguno de los dos venvs de arriba existe. Lo que hay es **uno solo**,
> `.venv-redteam`, con **garak 0.15.1 y pyrit 0.14.0 juntos**. Es decir: la
> separación que este documento exige se deshizo en algún momento y nadie
> actualizó el texto. Cada orden de ejemplo de más abajo, tal y como está
> escrita, falla al instante con «no such file or directory».
>
> Y la incompatibilidad que motivó la separación **sigue viva y ahora está
> violada**, no resuelta:
>
> ```
> $ .venv-redteam/bin/python -m pip check
> garak 0.15.1 has requirement datasets<4.0,>=3.0.0, but you have datasets 5.0.0
> ```
>
> Los imports de garak funcionan (`garak.probes.dan`, `garak.resources`,
> `datasets.load_dataset`), así que no revienta al arrancar. Lo que no está
> comprobado es una campaña completa que cargue un dataset de verdad: ahí es
> donde un salto de major de `datasets` suele romper, y sería a mitad de una
> corrida larga.
>
> **Antes de publicar una cifra nueva de estas demos**, rehaz los dos venvs como
> dice el bloque de arriba —es la configuración que respalda las cifras de
> referencia de la tabla— o mide de nuevo desde cero y sustituye la tabla. Las
> cifras actuales se obtuvieron con la separación intacta; no son reproducibles
> con el entorno tal y como está hoy.
>
> Las CVEs de `.venv-redteam` (pillow, pyasn1, pypdf, setuptools) siguen sin
> tocar a propósito: es un venv que hoy no invoca ningún camino de runtime, y
> subirlas sin rehacer la separación mezclaría dos problemas distintos.

## Demos

| Script | Qué mide | Cifra de la corrida de referencia |
|---|---|---|
| `garak_campaign.py` | Atribución bajo ataque (corpus Garak → gateway aislado) | C=60, K=60 → **100% inclusión verificada**; FP benignos 0/40 |
| `generalization_curve.py` | Frontera de generalización de la memoria inmune + control de FP | léxico rompe d=0.7; **semántico sin ruptura en [0,1]**, FP 0/8 |
| `pyrit_crescendo.py` | Multi-turn adaptativo (PyRIT Crescendo, atacante API) → trayectoria del tripwire | gradual evade; salto brusco dispara; **atribución 100%/turno** |
| `frontier_debate.py` | Maestro propone lecciones → el sistema arbitra (corrobora/contradice/acepta) | contradice al maestro cuando afirma que un ataque conocido es benigno |

Ejemplos:

```bash
PYTHONPATH=src .venv-redteam-garak/bin/python scripts/redteam/garak_campaign.py --attacks 60 --benign 40 --out docs/audits/reports/redteam_campaign_report.md
PYTHONPATH=src .venv-redteam-garak/bin/python scripts/redteam/generalization_curve.py --embedder hf --threshold 0.7 --out docs/audits/reports/immune_generalization_curve.md
CRESCENDO_OUT=docs/audits/reports/pyrit_crescendo_report.md PYTHONPATH=src .venv-redteam-pyrit/bin/python scripts/redteam/pyrit_crescendo.py
TEACHER_PROVIDER=nvidia DEBATE_OUT=docs/audits/reports/frontier_debate_report.md PYTHONPATH=src .venv/bin/python scripts/redteam/frontier_debate.py
```

## Límites honestos (válidos para todas)

- El "modelo objetivo" suele ser un stub: se mide el canal de seguridad, no contenido.
- Embedder/atacante/maestro estocásticos → cifras *ilustrativas de una corrida*, no benchmark.
- Cubren reformulación/atribución, **no** robustez frente a familias de ataque nuevas.
- Los reportes generados (`docs/*report*.md`, `docs/audits/reports/immune_generalization_curve.md`) son
  artefactos reproducibles, no afirmaciones de cobertura.
