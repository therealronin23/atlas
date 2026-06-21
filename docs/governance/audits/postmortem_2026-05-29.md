# Postmortem — 2026-05-29

Dos incidentes en la misma jornada. Ambos resueltos sin pérdida de datos.
Documento de cierre de la auditoría completa solicitada por Tomás.

---

## Incidente 1 — Corrupción de la cadena Merkle (auto-infligido)

### Resumen
Smoke tests del CLI (`atlas blocks create/delete`) ejecutados contra el
workspace **vivo** (`~/atlas`) mientras `atlas-core.service` estaba corriendo
forkearon la cadena Merkle en el índice 423.

### Causa raíz
`MerkleLogger` era thread-safe (lock intra-proceso) pero **NO inter-proceso**.
El servicio mantenía `_last_hash` en memoria y siguió encadenando desde su hash,
ignorando los records que insertó el proceso CLI → dos ramas desde el mismo
`hash_prev`. Agravante: cualquier invocación del CLI construía un `Orchestrator`
completo que escribía `session.started` en el Merkle vivo, incluso comandos
read-only (`search`, `audit`).

### Resolución
1. **Reparación**: re-encadenado preservando contenido (marker `chain.repaired`,
   backup `merkle.jsonl.bak-20260529_074414`).
2. **Fix A**: `session.started` salió de `Orchestrator.__init__` a
   `log_session_start()`, llamado solo por `atlas serve`. El CLI one-shot ya no
   escribe al arrancar.
3. **Fix B**: `MerkleLogger.append` ahora toma `fcntl.flock` exclusivo, relee el
   último hash desde disco antes de encadenar, y hace `fsync`. Multi-proceso-safe.

Commit: `dc497c7`. Test de regresión:
`test_interleaved_writers_keep_chain_valid`.

### Lección
Nunca ejecutar el CLI `atlas` (que construye `Orchestrator`) contra `~/atlas`
con el servicio corriendo. Usar `ATLAS_HOME` aislado para smoke tests. Guardado
en memoria de feedback `feedback-no-cli-against-live-workspace`.

---

## Incidente 2 — Cuelgue del equipo + filesystem read-only (hardware)

### Resumen
Durante la sesión, el HP Omen se congeló y `/` (SSD `/dev/sda2`) se remontó en
**read-only**, bloqueando toda escritura (incluido `/tmp`, que dejó inoperante
el shell de la sesión de Claude). El usuario reinició.

### Causa raíz
`errors=remount-ro` en ext4 se dispara ante un error de I/O del dispositivo de
bloque. SMART del SSD: salud **PASSED**, 0 sectores reasignados, 0
uncorrectable, pero **`UDMA_CRC_Error_Count = 24`** — errores de CRC en el
enlace SATA (conexión/controladora, **no** medio degradado). Un pico de CRC
provoca un reset del enlace → error de I/O → remount-ro → procesos en estado D
→ apariencia de cuelgue. La causa exacta del kernel no es recuperable: journald
no era persistente y el boot congelado no quedó registrado.

### Impacto / verificación de daños
- **Cero pérdida de datos.** Cadena Merkle íntegra (528 records, CHAIN OK) — el
  `fsync` del Fix B garantizó durabilidad justo en este escenario.
- `fsck` limpió inodos huérfanos en `/home` (`/dev/sdb1`) al arrancar.
- Prometheus auto-reparó un segmento WAL corrupto (`segment=42`).
- `git` limpio, `atlas-core.service` sano (sin restart-loop). Nada estaba "en
  bucle"; la apariencia de bucle fue el freeze por I/O.

### Resolución / mitigaciones
- journald fijado a `Storage=persistent` (logs sobrevivirán al próximo reinicio).
- SSD vigilado: si reaparece `remount-ro`, reasentar el conector SATA interno.
- Pendiente menor: dos ficheros temporales root-owned en la raíz del repo
  (`tmp1ngoo7jg`, `tmpxmsp6xjf`, 11-may) requieren `sudo rm`.

---

## Auditoría completa — estado del proyecto (2026-05-29)

Revisión integral solicitada ("siento que hay cosas sueltas/rotas/incompletas").

| Área | Hallazgo | Estado |
|------|----------|--------|
| Tests | 691 passed, 25 deselected, exit 0 | ✅ verde |
| Routing factual git | keywords no cubrían "commits"/"cambios" → alucinación | ✅ arreglado |
| Grounding general | factual→inferencia puede alucinar (necesita loop agéntico) | 🟠 abierto (ver ROADMAP) |
| ADRs | todos SEALED/Accepted; ninguno abierto | ✅ |
| Deriva docs | ROADMAP v0.9 / AGENTS v0.10-11 desactualizados | ✅ ROADMAP+AGENTS al día |
| Doc "qué falta" | no existía | ✅ creado (ROADMAP §Pendientes) |
| Huérfanos | `memory/audit` orphan + `pytest-of-ronin/` | ✅ limpiado + gitignore |
| Runtime | servicio sano, git limpio, Merkle íntegra | ✅ |
| SSD | CRC link errors (no medio) | 🟡 vigilado |

Conclusión: el proyecto está sólido. Los cabos reales eran el grounding factual
(mitigado para git, pendiente la solución de fondo) y la deriva documental
(resuelta). No había nada roto en silencio en el core.
