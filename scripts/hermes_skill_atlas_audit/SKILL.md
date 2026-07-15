---
name: atlas-audit
description: Compatibility alias for auditing through the repository-owned atlas-twin skill.
---

# atlas-audit compatibility

This skill is superseded by `atlas-twin`, which is the single authority for
the signed transport. New deployments install only `atlas-twin`.

If this compatibility directory is still present, the old command delegates
to that client and retains the existing arguments:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_audit.py" \
  --action skill.run --result success --risk moderate \
  --payload '{"skill":"weather"}'
```

Do not construct an HMAC manually, use `curl`, or treat an audit failure as a
successful receipt. The returned `hash_self` is the evidence that Atlas
actually appended the record.
