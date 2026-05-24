# Fleet Security Plan

**Source material:** distilled from `Gemini-Temporary Chat.md`.
**Status:** future architecture note.

Atlas is currently a strong single-node runtime. The next architectural jump is
not "more tools"; it is secure fleet management: multiple Atlas nodes that can
receive work, prove their state and preserve local governance.

## Goal

Move from node-level security to network-level security without weakening local
sovereignty.

## Pillars

### 1. Node Identity

Every Atlas node needs a durable identity.

Future requirements:

- node certificate or keypair;
- signed enrollment;
- key rotation;
- revocation;
- no command execution from unauthenticated control planes.

This connects naturally to ADR-024 if audit receipts and key rotation become
part of logging v2.

### 2. Signed Commands

Commands from a control plane or Hermes-like coordinator should be signed.

Node behavior:

1. verify command signature;
2. verify command freshness/nonce;
3. verify local Governance L0 permits the action;
4. issue capability token;
5. execute through AtlasExecutor;
6. log result locally.

Remote authority never bypasses local governance.

### 3. Governance State Sync

If governance or policy changes, nodes must not blindly `git pull`.

Future pattern:

- policy bundle is signed;
- bundle declares version and hash;
- node verifies signature and compatibility;
- node records policy update in MerkleLogger;
- stale/offline nodes enter a safe/degraded mode until reconciled.

### 4. Merkle Root Aggregation

Each node keeps its own MerkleLogger. A fleet controller should not ingest all
logs by default. Instead, nodes can periodically submit root hashes or compact
receipts.

Benefits:

- central proof of non-tampering;
- low bandwidth;
- local logs remain sovereign;
- later forensic pull is possible when needed.

### 5. Checkpoint and Recovery

If a task fails mid-execution, the node should report:

- task id;
- last Merkle hash;
- TimeTravel/checkpoint id if available;
- SandboxResult or failure class;
- retry safety classification.

The coordinator can then decide whether to retry locally, move the task to
Hermes, or require human approval.

## Non-Goals For Now

- No Kubernetes-style cluster control in Gate F.
- No Byzantine consensus.
- No automatic remote policy override.
- No public control plane.

## First Practical Step

Add a future backlog item after Gate F hardening:

`NodeIdentity`: a small local identity module that can generate a node keypair,
export a public identity document and sign heartbeat/audit receipts.

