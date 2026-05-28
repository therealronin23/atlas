# Auditoría completa y postmortem — Atlas Core

**Fecha:** 2026-05-25  
**Rama auditada:** `codex/self-audit-loop`  
**Alcance:** proyecto completo: Gates A-I, ADR-024/025, Gate H, computer-use,
Hermes-VPS live, Telegram, SelfAuditLoop, documentación operativa y scripts.

---

## Veredicto

Atlas está en un estado muy sólido para operación local avanzada. La suite
completa pasa, mypy está verde, Hermes real responde por Tailscale, Telegram
funciona, Gate H valida síntesis auditada y Gate I expone health/service runner.

El riesgo ya no es "faltan piezas básicas"; el riesgo principal es madurez
reflexiva. Atlas observa y diagnostica mejor de lo que todavía se corrige a sí
mismo. La siguiente etapa debe cerrar el ciclo:

detectar -> proponer patch -> validar -> promover en worktree frío -> revisión
humana -> merge.

---

## Evidencia ejecutada

`docs/audit_complete_latest.json` fue regenerado con todos los checks activos:

| Check | Resultado |
|-------|-----------|
| Core suite | `564 passed, 25 deselected` |
| Computer-use suite | `25 passed, 564 deselected` |
| Total observado | `589 tests` |
| mypy | `Success: no issues found in 62 source files` |
| Gate I smoke | OK |
| Gate H smoke | OK |
| SelfAudit CLI smoke | OK |
| Operational smoke live | OK: Hermes REST + CLI approval + Telegram outbound |

Comando final:

```bash
set -a && source .env && set +a
ATLAS_AUDIT_LIVE=1 ATLAS_AUDIT_COMPUTER_USE=1 \
PYTHONPATH=src python scripts/audit_complete.py
```

---

## Problemas encontrados y corregidos

| ID | Problema | Corrección |
|----|----------|------------|
| ENV-01 | `capture_fingerprint()` reportaba `atlas_version=0.6.1` por defecto aunque el runtime está en `0.9.0`. | Default actualizado a `0.9.0` y test de entorno actualizado. |
| AUD-01 | `scripts/audit_complete.py` no auditaba SelfAuditLoop, computer-use ni live smoke opcional. | Añadidos SelfAudit smoke, `ATLAS_AUDIT_COMPUTER_USE=1`, `ATLAS_AUDIT_LIVE=1`, `generated_at` y skips explícitos. |
| DOC-01 | AGENTS.md tenía contadores antiguos. | Actualizado a `564 core + 25 computer_use = 589`. |

---

## Hallazgos no bloqueantes

| ID | Severidad | Hallazgo | Acción recomendada |
|----|-----------|----------|--------------------|
| REF-01 | Alta | SelfAuditLoop todavía genera candidatos, no patches ColdUpdate reales. | Gate J1: SelfAudit -> ColdUpdate proposal. |
| REF-02 | Alta | La auto-mejora no crea rama/worktree frío automáticamente desde hallazgos. | Gate J2: rama `codex/self-audit-YYYYMMDD-HHMM` + validación. |
| REF-03 | Media | Observability de proceso fresco aparece vacía hasta que hay actividad local. | Persistir y agregar métricas históricas por componente. |
| REF-04 | Media | `ATLAS_AUDIT_LIVE=1` puede enviar Telegram real. | Mantenerlo opt-in y documentado como smoke de host, no CI. |
| REF-05 | Media | `.claude/` es un árbol local enorme sin trackear. | Mantener fuera de git; SelfAudit debe seguir detectándolo y no tocarlo. |
| REF-06 | Baja | Docs históricas contienen lenguaje de "future work" ya superado. | Marcar docs antiguas como históricas o añadir índice de vigencia. |

---

## Postmortem técnico

La secuencia de gates fue correcta: primero core local y auditado; luego
Hermes/Telegram/Tailscale; después inferencia real, memoria, seguridad,
dashboard, voz, computer-use, operación 24/7 y observabilidad/update frío.

La arquitectura ya tiene los órganos necesarios para autonomía segura:

- MerkleLogger como memoria forense.
- ValidationRunner como sistema inmune.
- ColdUpdateManager como metabolismo frío.
- Gate H como auditor de síntesis.
- EnvironmentSensor como primer sentido del entorno.
- SelfAuditLoop como ciclo reflexivo inicial.

Lo que falta es **conectividad metabólica**: que esos órganos trabajen en una
cadena cerrada y repetible sin saltarse HITL.

La decisión de no permitir hot self-patching sigue siendo correcta. Atlas debe
mejorarse como un ingeniero prudente: patches pequeños, evidencia, validación,
rollback y revisión.

---

## Futuro recomendado

### Gate J — Reflexive Autonomy

Objetivo: que Atlas se conozca, se evalúe y proponga mejoras pequeñas sin
fusionarlas automáticamente en `main`.

Entregables:

1. SelfAuditLoop crea propuestas ColdUpdate reales (`origin=self_audit`).
2. Generador de patches limitado por budgets: una hipótesis, máximo 500 líneas,
   sin tocar secrets/governance/systemd.
3. Validación obligatoria: core, mypy, smokes afectados, benchmark si aplica.
4. Rama/worktree frío automático: `codex/self-audit-YYYYMMDD-HHMM`.
5. Reporte final con accepted/rejected/failed y razón.

### Gate K — Environment Intelligence

Objetivo: que Atlas reconozca su entorno y sus límites.

Entregables:

- Sensor de CPU/RAM/disk/GPU/battery/Tailscale/Hermes/provider quotas.
- Diagnóstico de "por qué no puedo hacer X" con remedios concretos.
- Health histórico: degradaciones, recovery time, flapping, provider cooldowns.
- Runbooks generados desde evidencia, no solo escritos a mano.

### Gate L — Resilience Drills

Objetivo: demostrar recuperación, no solo disponibilidad.

Entregables:

- Restore drill de memoria derivada desde Merkle.
- Simulación Hermes offline/reconnect.
- Rotación controlada de secrets de smoke.
- Rollback ColdUpdate probado en repo real temporal.
- Chaos tests locales de permisos, timeouts y fallos de proveedor.

### Gate M — Productized Autonomy

Objetivo: convertir Atlas de sistema local avanzado en producto operable.

Entregables:

- Dashboard de auditorías y propuestas.
- PR automation opcional.
- Prometheus/Grafana o export estable.
- Atlas Box/fleet protocol con identidad firmada.
- Políticas de retención y backup.

---

## Siguiente acción

Implementar **Gate J1: SelfAudit -> ColdUpdate proposal**.

Ese es el punto de palanca. Atlas dejará de ser solo auditable y empezará a ser
reflexivo de verdad, sin necesitar libertad peligrosa ni mutación caliente.
