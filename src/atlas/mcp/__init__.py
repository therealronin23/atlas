"""Cliente MCP (Model Context Protocol) — ADR-035.

Atlas como cliente: conecta a servidores MCP externos (Calendar, n8n…),
expone sus tools al loop agéntico, audita cada llamada en Merkle. Diseño
hybrid-ready: stdio JSON-RPC 2.0 con stdlib ahora; SDK como hueco futuro.

Postura de seguridad (ADR-036/037):
  - **Mutate/HITL por defecto**; allowlist explícita marca tools de lectura.
  - Procedencia ``untrusted`` automática (prefijo ``mcp__``) → envoltura
    ADR-037 + taint del loop.
  - Secretos por server desde config NO commiteada; nunca al Merkle/contexto.
"""

from atlas.mcp.config import McpServerConfig, load_servers
from atlas.mcp.registry import McpRegistry
from atlas.mcp.transport import McpProtocolError, McpTransport, StdioTransport

__all__ = [
    "McpProtocolError",
    "McpRegistry",
    "McpServerConfig",
    "McpTransport",
    "StdioTransport",
    "load_servers",
]
