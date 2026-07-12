# MCP / Tool Security Study

Risks:

- tool poisoning;
- descriptor shadowing;
- rug pull;
- capability escalation;
- prompt injection through tool output;
- credential exfiltration.

Rules:

- Tool descriptors versioned and hashed.
- No auto-update for critical tools.
- Capability scopes explicit.
- MCP servers must be registered and reviewed.
- Descriptor changes trigger re-review.
