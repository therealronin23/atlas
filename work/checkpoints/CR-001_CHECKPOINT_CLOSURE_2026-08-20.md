# CR-001 — cierre estricto del checkpoint

**ESTO ES ATLAS 0.12.0 ANTES DE FRONTIER RECONCILIATION.**

Fecha de comprobación: 2026-08-20. Este documento cierra el estado observado;
no acepta producto, arquitectura nueva ni una decisión pendiente.

## Identidad y alcance

| Campo | Evidencia |
| --- | --- |
| Rama | `main` |
| SHA fuente auditada | `90864f77c320e2454409c6e770e4078553f73f00` |
| Base remota (`origin/main`) | `918cbdf0b5aac237e8094de2e22198a4f8184610` |
| Baseline CR-001 | `1d71eaa372072923305e46eee1793dd494dca0d9` (`cr001-baseline-20260815`) |
| Delta respecto a `origin/main` | 103 commits en `origin/main..90864f7`; no equivale a aceptación de producto |
| Delta desde baseline CR-001 | `49523fa`, `d9ce16d`, `90864f7` |
| Árbol antes del cierre documental | limpio; sin staged ni unstaged |

La corrección de cierre añadida a este árbol sólo actualiza dos expectativas de
Dashboard al identificador ya migrado y registra este checkpoint. El SHA final
que contiene este documento se comunica en el handoff/entrega, porque un
archivo no puede auto-incluir de forma estable el hash del commit que lo crea.

### A. Trabajo que ya pertenecía al checkpoint

- Migración del proveedor L1 retirado: `groq_llama_70b` a
  `groq_gpt_oss_120b` / `openai/gpt-oss-120b` (`d9ce16d`).
- Handoff generado correspondiente (`49523fa`, `90864f7`).
- Dos expectativas de `tests/test_dashboard.py` que seguían usando el nombre
  retirado y que la suite completa reprodujo como fallos.
- Registro de F2.6, gates, contradicciones y transferencia de este cierre.

### B. Fuera de alcance y sin mezclar

- No hay cambio de operador staged ni unstaged. Dos estados preservados están
  en `stash@{2026-08-20 21:06:41 +0200}` y
  `stash@{2026-08-20 21:07:44 +0200}`; no se aplicaron.
- Worktrees ajenos, propuestas ColdUpdate acumuladas, UI/UX con forks,
  Workbench/Cut 2, Android, Wave 5 y nuevas líneas de autonomía no se tocaron.
- No se creó ni aplicó una propuesta GoldenRoute de documento raíz en este
  cierre.

## Gates reproducidos

| Gate | Resultado | Clasificación |
| --- | --- | --- |
| `pytest tests/ -q` | PASS — `6023 passed, 6 skipped, 27 deselected, 1 warning`, 576.84 s | verificado |
| `pytest tests/ -q -m computer_use` | PASS — `27 passed, 6029 deselected`, 88.29 s | verificado |
| `mypy src/atlas/` | PASS — 361 ficheros | verificado |
| `scripts/check_canon.py --root .` | PASS — 2.118 JSONL records | verificado |
| `atlas audit --verify` | PASS — cadena Merkle íntegra | verificado |
| `git diff --check` | PASS | verificado |
| `atlas handoff --check` | PASS en `90864f7` antes del cierre documental | verificado en SHA fuente |
| `atlas reality --json` | graph `FRESH`, Merkle `ok`, daemon activo/no atrasado en `90864f7` | verificado en SHA fuente |
| `docs_index_audit.py --strict` | FAIL — 334 sin índice: 246 en `docs/archive/_graveyard`, 88 en otras rutas | PREEXISTING respecto al baseline CR-001; no resuelto |
| CI remoto | no existe run para `90864f7`; último run visible falla en `918cbdf` (2026-08-05) | PREEXISTING / no representa este árbol |

El warning de FastEmbed sobre mean pooling se conserva como **UNKNOWN**: no
falló el gate y esta corrida no mide su impacto semántico.

## F2.6 y evidencia de runtime

- Estado vivo: `due`; último resultado automático `fail` 1/6 en
  `90864f7`. No existe revisión semántica independiente ni `current`.
- Transcript conservado:
  `workspace/self_build/f26_runs/f26_run_20260820T195303959278+0000.txt`.
  El transcript registra como primera consulta de grafo una respuesta `STALE`.
  El grader automático falla; eso no prueba una incapacidad funcional de
  Atlas, pero tampoco permite aprobar F2.6.
- Reintento con Groq no es actualmente reproducible sin cambiar presupuesto:
  ledger local en 95% (`950619/1000000`), fail-closed antes de inferencia.
  OpenRouter devolvió crédito insuficiente para el máximo de salida solicitado.
  Ambos son **PROVIDER_BLOCKED**, no PASS ni fallo del producto.
- Runtime vivo en la comprobación fuente: Hermes local respondió; providers y
  MCP estaban configurados, pero `llm.inference` era sólo `configured`, no una
  demostración live de todos los proveedores.

## Fallos, incógnitas y contradicciones que permanecen

1. **PREEXISTING:** `docs_index_audit --strict` falla con 334 entradas. No se
   regeneró `docs/INDEX.yaml`: convertirlo en un diff masivo sería trabajo
   fuera de CR-001.
2. **PROVIDER_BLOCKED / OPEN:** F2.6 permanece `due` y `fail`; el presupuesto
   Groq y el crédito OpenRouter no permiten una repetición válida hoy.
3. **REQUIRES_OPERATOR / CONTRADICTED:** ADC-WO-107. El bridge 7341 conserva
   POST mutantes fuera de la excepción acotada de ADR-080 frente a ADR-058 y
   ADR-071. No se invocó un POST mutante, ni se eligió una de las dos salidas.
4. **HITL pendiente:** cuatro hallazgos MAJOR de Semgrep, registrados en el
   ledger; no se reclasificaron.
5. **Deliberadamente cerrado, no reabierto:** Cut 2 / Wave 5 por ADC-WO-108.
   ADC-WO-109 y ADC-WO-110 continúan `READY`, ADC-WO-111 y ADC-WO-100 requieren
   operador, y ADC-WO-104 sigue `BLOCKED`.
6. **Provisional, no falsificado con experimento nuevo:** ADR-057, ADR-058,
   ADR-069 y ADR-078. Una ADR aceptada no equivale a implementación, cableado,
   evidencia live ni aceptación de producto.
7. **Producto/UI:** el host CodeOSS/VSCodium y sus forks siguen decisión/delta
   de producto pendiente; no hay aceptación UX/UI ni implementación nueva en
   este cierre.

## Transferencia exacta a Frontier Reconciliation

- Decidir si financiar/proveer una sesión F2.6 L1 capaz; repetir rúbrica en
  checkout limpio, conservar transcript/receipts y obtener revisión semántica
  independiente. No reutilizar el 1/6 como aprobación.
- Resolver ADC-WO-107 mediante decisión explícita: restaurar bridge estrictamente
  read-only o aprobar una supersesión con contrato de mutación, identidad,
  auditoría y rollback por ruta.
- Triage humano de los cuatro MAJOR Semgrep.
- Clasificar/indexar la deriva documental sin un barrido narrativo y sin borrar
  evidencia archivada por hacer verde el auditor.
- Ejecutar los falsificadores ya registrados para ADR-057/058/069/078 antes de
  elevarlas de provisionales; medir Theia frente a CodeOSS sólo si se autoriza
  un corte de producto separado.
- Tratar UI/UX/forks, Wave 5 y Android como programas posteriores, no como
  tareas implícitas de este checkpoint.

## Artefactos modificados por el cierre

- `tests/test_dashboard.py`
- `WORK_LEDGER.md`
- `work/checkpoints/CR-001_CHECKPOINT_CLOSURE_2026-08-20.md`

No se abrió ninguna línea funcional nueva. Este cierre documenta límites,
reproduce gates y transfiere lo pendiente; no lo declara resuelto.
