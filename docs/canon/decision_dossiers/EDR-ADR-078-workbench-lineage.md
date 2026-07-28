# EDR-ADR-078 — Engineering Workbench lineage assimilation

**Decision:** ADR-078
**Program:** P08 — Product OS and UI/UX
**Evidence state:** `PROVISIONAL`
**Decision disposition authority:** `docs/canon/decision_registry.jsonl`

## Question

Which parts of Code OSS, VSCodium, Void and Zed should Atlas assimilate to
build an updateable Workbench without turning the product into an unmaintainable
fork fusion?

## Constraints

- Atlas Core remains the unique authority for policy, memory, tasks and audit.
- The browser shell remains a harness; it is not the final dedicated product.
- Third-party code and extensions are untrusted until vetted.
- Licensing and distribution compatibility are hard gates, not afterthoughts.

## Observed evidence

- `EVD-LOCAL-ADR-078` records the operator-selected product lineage.
- `EVD-EXT-VSCODIUM` describes a reproducible Code OSS build/configuration
  pipeline rather than a separate editor fork to merge.
- `EVD-EXT-VOID` reports paused IDE maintenance, making Void unsuitable as the
  maintained upstream host while retaining value as a capability donor.
- `EVD-EXT-ACP` supplies an editor–agent interoperability boundary.
- `EVD-EXT-ZED-LICENSE` records that Zed is primarily GPL-3.0-or-later and
  therefore code import requires specific license review.

## Alternatives compared

1. Merge the four source trees into a single Atlas editor fork. This appears
   comprehensive but combines incompatible upstream histories, licenses and
   maintenance cadences.
2. Maintain a current Code OSS host line; use VSCodium build discipline,
   selectively port Void capabilities, and use ACP/Zed interaction patterns
   through explicit Atlas bridges. This requires disciplined integration but
   preserves updateability and Core authority.

## Recommendation

Use the second alternative. The Workbench host follows current Code OSS;
VSCodium informs sovereign build and packaging; Void is a versioned donor; ACP
is the agent/editor contract; Zed contributes patterns and protocol knowledge,
not an indiscriminate code import. Extensions and hosts remain untrusted clients
that propose governed commands to Core.

No editor host has been imported or declared product-complete by this dossier.

## Confidence and limits

**Confidence:** high for rejecting a monolithic fork merge; medium for the
precise host cut until an integration baseline and license inventory are pinned.

**Falsifiers:** a current Code OSS baseline cannot host the necessary Atlas
contracts, or a required donor capability cannot be isolated or lawfully
reimplemented under the intended distribution model.

**Revisit triggers:** a material upstream host change, a packaging constraint,
or a Workbench contract that cannot be represented through the selected host
boundary.

## Security, licensing and rollback

Every donor port has an independent provenance, license, test and rollback
record. Failed ports remain isolated and reversible; a host experiment cannot
acquire Atlas Core authority or weaken extension/MCP vetting.

## Evidence IDs

`EVD-LOCAL-ADR-078`, `EVD-EXT-VSCODIUM`, `EVD-EXT-VOID`, `EVD-EXT-ACP`,
`EVD-EXT-ZED-LICENSE`.
