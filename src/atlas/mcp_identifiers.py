"""Dependency-light validation shared by MCP config, registry and Sentinel."""

from __future__ import annotations

import re


_MCP_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def is_valid_mcp_identifier(value: str) -> bool:
    """Identifier safe for ``mcp__<server>__<tool>`` namespacing and snapshots."""
    return bool(_MCP_IDENTIFIER.fullmatch(value)) and "__" not in value
