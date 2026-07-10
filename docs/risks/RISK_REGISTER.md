# RISK_REGISTER — Atlas OS

Riesgos vivos del frente Atlas OS. Actualizar al abrir/cerrar cada fase.
Formato: ID | riesgo | impacto | mitigación | estado.

| ID | Riesgo | Impacto | Mitigación | Estado |
| --- | --- | --- | --- | --- |
| OS-R1 | Bridge instancia un segundo Orchestrator → corrupción de la cadena Merkle (bug documentado en dashboard.py) | crítico | v1 read-only sobre el core; cero Orchestrator en `src/atlas/api/`; test que lo afirma | ABIERTO (mitigado por diseño) |
| OS-R2 | Segundo sistema de eventos divergente del EventBus/contracts real | alto | canon OS es PROYECCIÓN del bus existente (bridge suscriptor), mapping único con test; contracts.py intocado | ABIERTO (mitigado por diseño) |
| OS-R3 | UI-maqueta: pantallas sin contrato, settings que no hacen nada | alto | contracts-first (schemas+fixtures antes de UI); cada setting cableado a permisos/eventos o no se añade; REAL vs SIMULATED visible en UI | ABIERTO |
| OS-R4 | node 18 EOL limita Vite a v5; deriva de dependencias npm | medio | pin de versiones en package.json; upgrade de node = decisión del operador (OPEN_QUESTIONS) | ABIERTO |
| OS-R5 | Builds npm/Tauri disparan presión de RAM/tmp (historial earlyoom, /tmp 4G) | medio | web-first sin Tauri en v1; builds fuera de /tmp; no correr build+suite a la vez | ABIERTO |
| OS-R6 | Drift del INDEX.yaml de docs (216 entradas limpias al inicio) | medio | `scripts/docs_index_audit.py --write` antes de cada commit con docs nuevos | ABIERTO |
| OS-R7 | Pisar cambios sin commitear del operador (12 rutas dirty, incl. WORK_LEDGER.md) | alto | nunca `git add -A`; add selectivo por ruta; WORK_LEDGER no se toca — diff propuesto en chat | ABIERTO |
| OS-R8 | El daemon del lazo corre contra este repo; pytest de sesión podría relanzarlo | medio | guardia ATLAS_NESTED_TEST_RUN ya cableada (041f3972); suites dirigidas, no la completa por defecto | MITIGADO |
| OS-R9 | Eventos OS con hashes de auditoría inventados (teatro de seguridad) | alto | `audit.merkle_hash` solo si viene del TransparencyLog real; si no, null + `simulated=true` | ABIERTO (regla de diseño) |
| OS-R10 | Conectores outbound (Gmail/WhatsApp) actúan sin gate | crítico | v1 specs+mock sin credenciales reales; acciones outbound bloqueadas por defecto (approval.required) | ABIERTO |
| OS-R11 | Puerto 7341 del bridge expuesto más allá de localhost | medio | bind 127.0.0.1 hardcodeado como el dashboard (7331); sin auth remota en v1 | ABIERTO (regla de diseño) |
