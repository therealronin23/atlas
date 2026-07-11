# ADR-063 — Gate Engine real (ceremonia de decisión humana auditable)

- Estado: aceptado (2026-07-11)
- Contexto: Fase 15 dejó `BusinessCore.activation.gate_id` como un string
  descriptivo (NEW_GAPS_FOUND #3): "gated" no era un objeto auditable, solo
  un flag. El pack (`backend/GATE_ENGINE.md`) exige "human decision
  ceremonies for risky actions". `approve_activation` confiaba en un
  `approved_by` sin registro separado ni ciclo de vida.

## Decisión

Se añade un **Gate Engine** (`src/atlas/fabric/gates.py`) con un objeto
`GateTicket` (`schemas/gate_ticket.schema.json`) de ciclo de vida explícito:

1. `open → approved | rejected`. Un ticket nace `open` y **solo un humano lo
   resuelve** (`resolved_by` obligatorio, `GateTicketError` si vacío).
   Resolver un ticket ya resuelto es un error (no hay doble resolución).
2. `BusinessCoreEngine.request_activation` **abre un ticket real**
   (`gate_business_activation`) y guarda su `gate_ticket_id` en
   `activation.gate_ticket_id`. `approve_activation` **aprueba el ticket**
   por el Gate Engine (audita quién/cuándo/evidencia) antes de activar.
   Nuevo `reject_activation` rechaza el ticket y devuelve el core a `draft`.
3. Persistencia JSON con lock (mismo patrón `_Store` de `core_engine.py`).
   El Gate Engine **hereda el aislamiento del path del core**: en tests
   (tmp_path) los tickets quedan junto al estado, nunca en `$ATLAS_HOME`
   real. `BusinessCoreEngine.gates` expone el motor.
4. Cada transición emite evento (`gate.opened` con `status=waiting_user`,
   `gate.approved`/`gate.rejected`). API: `GET /gates/open`,
   `GET /gates/{id}`, `POST /business/core/reject`. CLI: `atlas gates list`.

## Consecuencias

- "Gated" pasa de promesa a mecanismo: hay una cola de decisiones humanas
  (`/gates/open`) con quién pidió qué, cuándo, y la resolución con evidencia.
- El contrato de `approve_activation` se mantiene (mismos parámetros +
  `decision_note`/`evidence` opcionales) — no rompe los tests de Fase 15.
- `activation.gate_ticket_id` es opcional en el schema (paridad intacta): un
  core creado a mano sin pasar por `request_activation` no tiene ticket.
- Pendiente Fase 17: generalizar el Gate Engine a TODA acción gateada
  (email.send, computer_use...), no solo activación de Business Core; hoy
  el PolicyEngine devuelve `require_gate` pero no abre ticket automáticamente.
