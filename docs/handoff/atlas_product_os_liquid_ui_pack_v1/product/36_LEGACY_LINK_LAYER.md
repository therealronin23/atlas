# Legacy Link Layer

If the user has an old CRM/ERP/POS/accounting system, Atlas links first and replaces only gradually.

Flow:

```text
Legacy System → Connector/Export/DB/Browser Assist/Computer Use → Data Mapping → Atlas Business Core → Read-only mirror → Partial sync → Atlas-native if safe
```

Modes:

- External canonical.
- Atlas canonical.
- Hybrid canonical.

Canonicality must be explicit.
