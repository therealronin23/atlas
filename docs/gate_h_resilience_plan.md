# Gate H Resilience And Software Synthesis Plan

**Source material:** distilled from the final review of `Gemini-Temporary Chat.md`.
**Status:** future planning note; not part of Gate F acceptance.

The Gemini chat contains one important thread that was not fully captured in
the Gate F docs: Atlas eventually needs to validate, repair and retire code it
generates dynamically. This is future Gate H material. Gate F should only keep
the hooks and evidence needed to reach it safely.

## Core Idea

Atlas should not become a bag of generated scripts. If it synthesizes task
specific tools, each generated artifact needs:

- a clear input/output contract;
- an execution sandbox;
- a dependency fingerprint;
- a performance record;
- a validity record;
- a safe retirement path.

The useful framing is "software synthesis under audit", not autonomous
self-modification.

## Future Gate H Pillars

### H1: Result Auditor

Generated tools must be judged by output validity, not only by exit code.

Future mechanism:

1. Save a truth snapshot: input, expected output shape and invariants.
2. Re-run old and new tool versions against the same truth snapshot.
3. Promote a new generated pattern only when the output remains valid.
4. Store failures in ErrorRegistry and approved patterns in
   ApprovedPatternStore.

This is the practical version of the "Shadow Runner" idea from the chat.

### H2: Reasoning Receipt

Atlas already records actions. Gate H should also record compact reasoning
receipts for high-impact generated tools.

Receipt requirements:

- why the tool is needed;
- what data it will touch;
- what permissions it needs;
- what safety checks were applied;
- what human approval, if any, was required.

Do not log raw hidden chain-of-thought. Store structured, concise decision
receipts suitable for audit.

### H3: Rebuildable Memory

KuzuDB should be treated as a high-value index, not the sole source of truth.
The stronger target is rehydration from append-only evidence.

Future mechanism:

1. MerkleLogger remains the audit source of truth.
2. KuzuDB stores derived graph/vector indexes.
3. A rebuild command can recreate derived memory from trusted logs and approved
   evidence.
4. Rebuilds produce their own Merkle entries.

### H4: Adaptive Fail-Safe

Atlas should degrade when generated tools repeatedly fail.

Future behavior:

- pause synthesis after repeated equivalent failures;
- allow only known-good tools in diagnostic mode;
- require human review before retrying risky generated actions;
- use TimeTravel checkpoints for rollback candidates.

### H5: Meta-Governance

Self-improvement must never be allowed to optimize away the safety model.

Non-negotiable constraints:

- no generated code can disable Merkle logging;
- no generated code can bypass capability tokens;
- no generated code can modify `governance.json`;
- no generated code can exfiltrate unredacted PII;
- high-impact actions remain human-approved.

This belongs above ordinary generated-code optimization.

### H6: Environment Sensor

Generated tools age. Dependencies, CVEs, APIs and provider behavior change.

Future mechanism:

- track dependency fingerprints for generated tools;
- monitor vulnerability and compatibility signals;
- mark stale generated patterns for re-validation;
- avoid silent reuse when the environment has changed materially.

## Operator Security Note

The chat included a warning about pasting a Tailscale auth key into a chat.
Treat any pasted API key, auth key or shared secret as potentially exposed.

Operational rule:

1. Prefer ephemeral tokens.
2. Rotate reusable secrets after exposure.
3. Never commit raw chat exports containing secrets.
4. Keep `.env` local and untracked.

## Relationship To Gate F

Gate F should not implement Gate H. It should prepare for it by making real
host actions auditable, permissioned and reproducible:

- BrowserTool and EditorTool must use AtlasExecutor.
- External effects must be Merkle logged.
- Browser/editor/voice smoke tests must cover real integration boundaries.
- Generated code must still pass AST Guard before execution.

Gate H starts only after Gate F proves Atlas can touch the host safely.
