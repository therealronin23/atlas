<!-- GENERADO por atlas handoff 2026-07-22T16:03:33.985559+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

# Primeros 10 minutos — arranque en frío

Secuencia mínima para orientarse sobre Atlas antes de tocar nada:

1. Leer `AGENTS.md` completo (invariantes duros, no un resumen —
   ver también `02_INVARIANTES.md` de este mismo pack).
2. Leer `00_ESTADO.md` de este pack (bloque `## WHERE` más reciente
   de `WORK_LEDGER.md`) — estado vivo, no histórico.
3. Correr `atlas reality --json` — nunca asumir estado sin evidencia
   fresca (daemon vivo, grafo, proveedores, tests).
4. Ejecutar UNA ruta dorada de demo sobre un repo fixture (nunca el
   repo real la primera vez): `atlas golden-route request '<petición
   de texto libre>'` -> `atlas update validate <id>` -> `approve` ->
   `apply` — aprender la ceremonia completa (recibo en Merkle) antes
   de proponer nada real.
5. Solo entonces: proponer el primer cambio real, siempre por la ruta
   dorada/`atlas update`, nunca editando a mano lo que este pack ya
   genera (INDEX.yaml, docs/handoff/GENERATED/, etc.).

Un fallo en cualquier paso es SEÑAL, no un obstáculo a saltar: F2.6
(rúbrica de sucesión) existe exactamente para capturarlo.

