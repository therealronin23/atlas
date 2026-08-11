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

> **ESTADO REAL DE ESTA MÁQUINA (2026-08-11) — leer antes de correr nada.**
>
> **Los dos venvs existen y funcionan**, rehechos hoy según ADR-056 con los
> extras de `pyproject.toml`:
>
> | venv | contenido | tamaño | `pip check` | ejecuta |
> |---|---|---|---|---|
> | `.venv-redteam-garak` | garak 0.15.1 + torch 2.13.0+cpu | 1,9 GB | limpio | `garak --version` → `v0.15.1`, rc=0 |
> | `.venv-redteam-pyrit` | pyrit 0.14.0 | 1,0 GB | limpio | los 12 símbolos que importa `pyrit_crescendo.py` resuelven |
>
> Comprobado ejecutando, no sólo instalando: un `pip check` limpio dice que las
> dependencias son consistentes, no que la herramienta arranque. Son cosas
> distintas y aquí se verifican las dos.
>
> **Lo que había antes, porque explica por qué la separación importa:** durante
> un tiempo hubo **uno solo**, `.venv-redteam`, con garak y pyrit **juntos** —
> la separación que este documento exige se había deshecho y nadie actualizó el
> texto, así que cada orden de ejemplo fallaba al instante mientras el documento
> parecía correcto. Y la incompatibilidad que motivó separarlos seguía viva y
> violada en silencio (`garak requires datasets<4.0, but you have 5.0.0`): los
> imports aguantaban, y una campaña que cargase un dataset de verdad habría roto
> a mitad de corrida. Ese venv se borró el 2026-08-10 por decisión del operador.
> Con la separación restaurada, ese conflicto ya no aparece — de ahí que el
> `pip check` limpio sea parte de la comprobación y no un detalle.
>
> **REMEDIDO EL 2026-08-11 (t14): dos de las cuatro reproducen, una NO.**
>
> | Demo | ¿Reproduce? | Medido hoy |
> |---|---|---|
> | `garak_campaign.py` | **Sí, exacto** | C=60, K=60 → 100% atribución; FP benignos 0/40; control benigno 40/40 |
> | `generalization_curve.py` | **NO** | rompe en **d=0,6** (recall 17%), no "sin ruptura en [0,1]". FP 0/8 sí reproduce |
> | `pyrit_crescendo.py` | sin medir | necesita atacante por API y la cuota diaria está agotada (ver `docs/audits/reports/fitness_2026-08-11.md`) |
> | `frontier_debate.py` | sin medir | mismo motivo: maestro por API |
>
> La que no reproduce se dice con esas palabras en vez de dejar la vieja. La
> cifra antigua ("semántico sin ruptura en [0,1]") se midió con **otro
> embedder**, y cuál era no quedó escrito — que es precisamente por qué no se
> puede comparar. Con `--embedder hf` (all-MiniLM-L6-v2, el que documenta el
> ejemplo de abajo) la curva cae a partir de 0,5. El reporte nuevo está en
> `docs/audits/reports/immune_generalization_curve.md`.
>
> Lección de método, no de resultado: una cifra sin la configuración que la
> produjo no es reproducible aunque el script siga ahí.

## Demos

| Script | Qué mide | Cifra de la corrida de referencia |
|---|---|---|
| `garak_campaign.py` | Atribución bajo ataque (corpus Garak → gateway aislado) | **2026-08-11**: C=60, K=60 → **100% inclusión verificada**; FP benignos 0/40 |
| `generalization_curve.py` | Frontera de generalización de la memoria inmune + control de FP | **2026-08-11** (`--embedder hf`): ruptura en **d=0.6** (recall 17%), FP 0/8. La cifra anterior "sin ruptura en [0,1]" NO reproduce — ver aviso arriba |
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
