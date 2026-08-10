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

> **ESTADO REAL DE ESTA MÁQUINA (2026-08-10) — leer antes de correr nada.**
>
> **No hay ningún venv de red-team montado.** El bloque de arriba es la
> instrucción a seguir, no una descripción de lo que existe: hay que crear los
> dos desde cero antes de correr una campaña.
>
> Cómo se llegó aquí, porque explica la trampa: durante un tiempo hubo **uno
> solo**, `.venv-redteam`, con garak 0.15.1 y pyrit 0.14.0 **juntos** — la
> separación que este documento exige se había deshecho y nadie actualizó el
> texto, así que cada orden de ejemplo fallaba al instante mientras el documento
> parecía correcto. Además la incompatibilidad que motivó separarlos seguía
> viva y violada en silencio (`garak requires datasets<4.0, but you have
> 5.0.0`): los imports aguantaban, y una campaña que cargase un dataset de
> verdad habría roto a mitad de corrida. Ese venv se borró el 2026-08-10 por
> decisión del operador, junto con `.venv-desktop`, y con él sus 13 avisos de
> CVE sin atender.
>
> **Consecuencia para las cifras de la tabla de abajo, y es la que importa:** se
> midieron con la separación intacta y **no son reproducibles hoy**. Antes de
> publicar una cifra nueva —o de citar las actuales— hay que rehacer los dos
> venvs como manda ADR-056 y volver a medir. Un `pip check` limpio en ambos es
> parte de la comprobación, no un detalle: es lo que faltó la última vez.

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
