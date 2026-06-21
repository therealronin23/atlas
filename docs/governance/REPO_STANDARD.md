# REPO STANDARD — orden, ciclo de vida y saneamiento

Estándar de gobernanza del repo. Enlazado desde `AGENTS.md §OPERATING LOOP`. Objetivo:
orden explícito, nunca perder el hilo, saneamiento quirúrgico y cíclico. Lo escribimos
ANTES de mover nada (sin estándar, mover = caos).

## 1. Layout (taxonomía, no baroque)

```
src/ , tests/                código + su red de seguridad (los tests NO son ruido:
                             son lo que hace seguro borrar. Viajan con su código).
docs/governance/             matrioska SOLO de gobernanza: estándar, CAPABILITIES,
                             gates/ADR/fase + auditorías + docs de cierre (roll-up).
docs/reference/              durable: el paper, ADRs vigentes.
docs/design/                 design docs vivos.
docs/archive/_graveyard/     CUARENTENA: por fecha + MANIFEST.md (ruta, motivo, veredicto).
WORK_LEDGER.md (raíz)        estado vivo (autoridad del DÓNDE).
raíz: solo AGENTS, CLAUDE, README, CHANGELOG, ROADMAP, WORK_LEDGER, PLAN_PUBLICACION.
```
El **código** vive en `src/` por módulo — NUNCA dentro de la jerarquía de gobernanza
(mezclarlos es el desorden que eliminamos). La jerarquía Gate→ADR→Fase→Tipo es para
DOCUMENTOS de gobernanza y para no perder el hilo, no para reorganizar el código.

## 2. Ciclo de vida + roll-up de auditorías

Cada nodo (Tipo→Fase→ADR→Gate) al CERRARSE escribe una nota de cierre/auditoría breve.
El cierre **condensa hacia arriba**: tipo→fase→ADR→Gate. El Gate cierra con UN documento
de cierre que condensa la cadena; lo granular se archiva (no se borra — git + archive).
Autoridad por eje: ledger=DÓNDE · design docs=CÓMO · memoria=POR QUÉ. El estado NO se
duplica (vive solo en el ledger).

## 3. Saneamiento (cíclico, quirúrgico) — 3 cubos: KEEP / QUARANTINE / DELETE

- **Nunca borrado duro en una pasada.** Mover a `docs/archive/_graveyard/<fecha>/` con
  `MANIFEST.md` (qué, por qué, veredicto pendiente). Ciclo siguiente: rescatar o `git rm`.
- **Puerta de seguridad:** la suite queda VERDE tras cada movimiento. Borrar código =
  borrar sus tests; si un test falla, no estaba muerto.
- **Criterio "inservible":** sin referencias entrantes · superseded · volcado scratch ·
  duplicado · carpeta vacía · artefacto de build · **código sin importadores no-test**.
- **Auditoría de cableado (anti-vapor de sistema):** un módulo con 0 importadores no-test
  → revisar: **cablear o a cuarentena**. Comando: `grep -rln "import .*<mod>" src/ | grep -v test`.
- **Cíclico (automatizado):** `python3 scripts/sanitation_audit.py` (read-only) cada ciclo —
  al cerrar un Gate o ~mensual. Reporta: vapor de sistema (0 importadores no-test), cuarentena
  vencida (grace 30d → candidata a `git rm` si nadie la rescató), carpetas vacías, refs stale.
  El humano/agente decide KEEP/QUARANTINE/DELETE sobre el informe. El grueso fue la limpieza
  inicial (Gate de gobernanza 2026-06-21, ver `CLOSURE_governance_2026-06-21.md`).

## 4. Anti-vapor (regla `wire-before-claim`)

Un módulo no está "hecho" hasta que tiene un **consumidor no-test + integración**. Un test
contra un stub de una capacidad externa prueba el FLUJO, no la capacidad. Toda capacidad
declarada se anota honestamente en `CAPABILITIES.md` (real / andamiaje-software / no-cableado
/ no-existe). Nunca overclaim.
