# INTEGRATION_FABRIC — conectores Atlas OS

## Contrato

`schemas/connector.schema.json` + `schemas/account.schema.json`. Campos clave:
`credential_reference` (referencia opaca `env:*`, JAMÁS secretos),
`mode` (real|mock|sandbox — real solo con credenciales presentes),
`memory_policy`, `automation_policy` (manual_only|gated|rules_allowed),
`audit_policy`, `legal_notes`.

## Estado v1 (todo MOCK, por diseño)

| Conector | Riesgo | Nota |
| --- | --- | --- |
| conn_gmail | high | mail.send SIEMPRE tras gate_outbound + humano |
| conn_github | medium | lectura amplia; escritura gateada |
| conn_claude_import | low | import manual de export JSON; sin scraping |
| conn_local_files | low | lectura local con provenance |
| conn_whatsapp | critical | POLICY-ONLY: sin API personal (ToS); solo import de exports; envío automatizado PROHIBIDO |

Endpoints: `GET /connectors`, `POST /connectors/{id}/test`,
`POST /connectors/{id}/sync` (emiten eventos connector.*). UI: Integration
Fabric en el Control Plane con riesgo/credencial/avisos legales visibles.

## Relación con lo existente

El repo YA tiene fabric real para tools/MCP: el catálogo del trunk
(`mcp/`, sectores, `trunk_invoke*` con HITL) y SSRFBridge. Los conectores OS
son la cara de CUENTAS/servicios externos; cuando un conector pase a real,
su ejecución debe ir por las rutas existentes (capability pipeline + Merkle),
no por un camino nuevo. Gmail real tiene además prior art: el MCP
google-workspace ya está instalado a nivel de operador (45 tools OAuth) — la
decisión wrap-vs-nativo es un digest pendiente (research-before-deciding).

## Regla de oro

Nada actúa sin permiso; todo se vuelve evento+memoria+auditoría; revocación
documentada por conector.
