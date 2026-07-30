# AVISO: este directorio es un SNAPSHOT HISTÓRICO, no el estado vigente

**Estado vigente = `docs/canon/`** (`implementation_registry.yaml`,
`open_questions.jsonl`, `conflict_registry.jsonl`).

Los ficheros de este directorio son el artefacto de entrega de una corrida del
canon-compiler del **2026-07-29** (anchor `fac6bca`). Se conservan intactos por
procedencia — **este fichero es nuevo y no modifica ninguno de ellos**. Pero ya
no describen el estado actual: el canon vivo se regeneró después
(`docs/canon/implementation_registry.yaml`, `generated_at: 2026-07-28`,
`base_commit: c95038c`) y en el árbol han entrado cambios posteriores.

## Divergencias verificadas contra el canon vivo (2026-07-30)

### 1. `ADC-WO-108` — el snapshot lo da BLOCKED; el canon vivo, READY

| Fuente | status | `operator_decision_required` |
|---|---|---|
| `DEFERRED_WORK_ORDERS.json` (aquí) | `BLOCKED` | `false` |
| `docs/canon/implementation_registry.yaml` | **`READY`** | `false` |

Importa porque `ADC-WO-108` es el **único** work order en `READY` de todo el
registro vivo (24 `DONE`, 6 `REQUIRES_OPERATOR`, 4 `BLOCKED`, 1 `REJECTED`), su
dependencia declarada ya está satisfecha ("operator execution authorization
recorded in WORK_LEDGER.md on 2026-07-29") y no requiere decisión de operador.
Leer el snapshot en vez del canon lleva a creer que no hay nada ejecutable.

### 2. `ADC-WO-124` no existe en este snapshot

`grep` sobre todos los ficheros de este directorio: **cero apariciones**. En el
canon vivo es `REQUIRES_OPERATOR` (`operator_decision_required: true`):
*"Admit the pinned desktop-control MCP through governed third-party execution"*
— admisión de `computer-control-mcp==0.3.10`, hoy un ejecutable de terceros sin
artefacto inmutable materializado ni hash verificado.

Consecuencia directa: **`OPERATOR_DECISIONS_REQUIRED.md` de este directorio
enumera 9 decisiones y deberían ser 10.** Es además la dependencia declarada de
los ítems de backlog `t3-1-universal-gui-operator` y `t3-2-gui-recipe-library`.

## Cómo usar este directorio

- Para **historia y procedencia** de la corrida del 2026-07-29: sirve tal cual.
- Para **decidir qué hacer ahora**: usar `docs/canon/`, no esto.
- No se regenera desde aquí: el artefacto pertenece a la herramienta que lo
  produjo, no a este repo.
