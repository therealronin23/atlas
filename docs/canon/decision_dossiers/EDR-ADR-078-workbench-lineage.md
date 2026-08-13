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

## Revalidation against Theia — 2026-08-12

Neither falsifier was executed, so fulfilment is **NOT VERIFIABLE**. The local Code OSS 1.132.0 spike proves that a
narrow Atlas bridge/protocol/privacy contribution can live on that baseline;
it does not prove every required Workbench contract. No evidence showed that a
required donor capability is impossible to isolate or lawfully reimplement.
The evidence qualification therefore remains `PROVISIONAL`.

Fresh upstream evidence also makes Eclipse Theia a real challenger:

- official releases were Code OSS
  [1.132.1](https://github.com/microsoft/vscode/releases/tag/1.132.1)
  (2026-08-11), VSCodium
  [1.126.04524](https://github.com/VSCodium/vscodium/releases/tag/1.126.04524)
  (2026-07-07) and Theia
  [v1.74.1](https://github.com/eclipse-theia/theia/releases/tag/v1.74.1)
  (2026-08-06). VSCodium's binary release was six VS Code minors and 35.39
  days behind the Code OSS release; that weakens it as a host-cadence oracle,
  not as a source of build/privacy/packaging discipline;
- the official [VS Code/Theia comparator](https://eclipse-theia.github.io/vscode-theia-comparator/status.html)
  says Theia 1.74.1 supports the VS Code API through 1.130.0. Parsing its 2,655
  current rows yielded 2,400 Supported, 24 Partial and 231 Stubbed; several
  Chat/Language Model entries are stubbed;
- a one-off query of non-truncated GitHub recursive trees reported 17,143 blobs and 147,371,996
  TS/TSX bytes for Code OSS 1.132.1 versus 4,128 blobs and 22,795,957 bytes for
  Theia v1.74.1: 4.153× and 6.465× respectively. These are source-surface
  proxies, **not** comparative maintenance cost. The exact API responses and
  parser command were not preserved in the repository, so this measurement is
  **reported, not reproducible from the checkout**;
- Theia documents compile-time extensions with full internal access through
  [dependency injection](https://theia-ide.org/docs/extensions/), so a custom
  product need not imply a core fork. It now has
  [Workspace Trust](https://theia-ide.org/docs/workspace_trust/) gates for MCP,
  tasks, debugging and AI, correcting the earlier assumption that it lacked
  the feature; its own docs also say `limited` extension support is currently
  treated as trusted;
- Theia's [security policy](https://raw.githubusercontent.com/eclipse-theia/theia/v1.74.1/SECURITY.md)
  says fixes land in the next release and are not backported.

The local Code OSS branch `spike/pin-1.132.0` remains clean in tracked files at
`f7c27192aa938d42ac186bc2ca0e9a83cc06a29c`: six files, `+588/-1`; only
`app.ts` changes host core (`+8/-1`), while 580 additions are under
`contrib/atlas`. A one-off 1.132.0→1.132.1 comparison reported 10 commits and
28 files, but its exact response and command were not preserved. Seam
non-overlap is therefore **reported without confirmation**, and 1.132.1 was
not built or started here.

One procedure failure must not be normalized: during this audit a delegated
subagent ran the already-built third-party Node contract tests (21/21) without
explicit third-party execution consent. No clone, fetch or edit occurred and
the checkout remained clean, but that run violated invariant 9 and was logged
retrospectively in Merkle receipt `7dc82337-becf-4d38-afab-de2bcc2b116f`.
It is not used as authorization or as the basis for this verdict.

The future decision gate, only when Cut 2 is authorized, is an isomorphic Theia
spike: same governed bridge and contract corpus, full build/start, host-core
delta, one upstream upgrade, packaging and runtime-resource measurements. Pick
on measured maintenance delta and authority fit, not repository size or sunk
cost. This revalidation does not open Cut 2.
