# Evidence-retention gaps

No Semgrep scan was run in FR-000/FR-001.

CR-001 preserves four candidate-level summaries covering 16 historical MAJOR finding events, but not the raw events needed for individual triage:

| Candidate | Historical MAJOR count | Entrypoint | Classification |
| --- | ---: | --- | --- |
| `ai.adeu/adeu` | 7 | `adeu.server` | `HISTORICAL_FINDING_PRESENT`; `RAW_EVIDENCE_NOT_RETAINED`; `NOT_INDIVIDUALLY_TRIAGEABLE`; `REQUIRES_RESCAN_WITH_RAW_RETENTION` |
| `com.arcself/arc-security` | 4 | `./bin/arc-security-mcp.js` | `HISTORICAL_FINDING_PRESENT`; `RAW_EVIDENCE_NOT_RETAINED`; `NOT_INDIVIDUALLY_TRIAGEABLE`; `REQUIRES_RESCAN_WITH_RAW_RETENTION` |
| `com.atagon/kogiqa-mcp` | 4 | `index.js` | `HISTORICAL_FINDING_PRESENT`; `RAW_EVIDENCE_NOT_RETAINED`; `NOT_INDIVIDUALLY_TRIAGEABLE`; `REQUIRES_RESCAN_WITH_RAW_RETENTION` |
| `com.gitkraken/gk-cli` | 1 | `run-gk.js` | `HISTORICAL_FINDING_PRESENT`; `RAW_EVIDENCE_NOT_RETAINED`; `NOT_INDIVIDUALLY_TRIAGEABLE`; `REQUIRES_RESCAN_WITH_RAW_RETENTION` |

Missing per-event fields are `rule_id`, `path`, `line`, `fingerprint`, and raw scanner output. The candidate summary itself is retained and hashable; the original scanner evidence is not.

A future scan cannot silently substitute for the lost historical result. It must be recorded as a new observation with raw retention, while these CR-001 gaps remain historical.
