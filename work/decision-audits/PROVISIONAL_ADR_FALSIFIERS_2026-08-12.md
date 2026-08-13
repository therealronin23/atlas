# Provisional ADR falsifier audit — 2026-08-12

Scope: evidence qualification for ADR-057, ADR-058, ADR-069 and ADR-078. An
accepted ADR and a `PROVISIONAL` evidence qualification are not contradictory:
the operator decision remains authority while its empirical claims retain
limits.

## Verdicts

### ADR-057 — governed memory promotion

- **Falsifier fulfilled? NOT VERIFIABLE / not run.** The falsifier requires an
  A/B benchmark of the proposed automatic promotion policy against temporal
  correctness, privacy lineage and abstention. There is no governed automatic
  promoter to execute; the graph found stores, indexes and abstractors, but no
  canonical promoter/registry module.
- **Fresh evidence:** `tests/test_authority_memory_owners.py` passed 13/13.
  A read-only query of `/home/ronin/atlas/memory/kuzu/atlas.kuzu` returned
  `Pattern=0`, `Failure=0`, `Evidence=0`; ADR-057's original >100-row bridge
  revisit trigger is not met.
- **What would move it:** implement a disabled-by-default promoter fixture with
  source lineage, sensitivity and withdrawal; run matched baseline/promotion
  cases with temporal and privacy deletion assertions. Do not activate it to
  obtain the measurement.
- **Operator-decision challenge:** marking ADC-WO-103 `DONE` proves the
  authority map was decided, not that the accepted promotion contract exists.
  Treating those as the same would turn an evidence gap into a status label.

### ADR-058 — read projection plus governed command plane

- **Falsifier fulfilled? NOT VERIFIABLE / not run.** Its falsifier asks whether
  local IPC can preserve identity, idempotency and approval receipts across a
  desktop-host restart. No such IPC command plane is implemented.
- **Fresh evidence:** 42 OS API/mission-boundary tests passed. They validate
  current HTTP/CLI behavior and timeouts, not the missing IPC contract.
  ADC-WO-107 independently demonstrates that the executable 7341 surface has
  drifted further from the recommended read projection.
- **What would move it:** a minimal local IPC spike must propagate an
  authenticated identity, reject duplicate idempotency keys, enforce
  `expected_version`, survive host restart and tie admission/effect to a
  verifiable receipt.
- **Operator-decision challenge:** preserving mutating 7341 because clients
  already use it is compatibility evidence, not evidence that the command
  plane is impossible. Conversely, recommending IPC without a spike is still
  architecture, not capability.

### ADR-069 — selective durable work history

- **Falsifier fulfilled? NOT VERIFIABLE / not run. Previous dossier claim
  corrected.** Nine focused
  GoldenRoute/recovery tests passed; three recovery tests round-trip the
  existing file-backed `TaskPersistence` in separate processes. Source search
  and the fresh graph found no selective Mission/Task/command/effect journal.
  Therefore those tests do not execute the matrix falsifier.
- **What would move it:** implement a minimal append-only work journal; kill
  the writer after admission and after an ambiguous effect; reconstruct
  Mission, Task, approval, command and receipt projections in a new process
  without reading legacy mutable owners; then reconcile at-least-once effects.
- **Operator-decision challenge:** three green recovery tests are real evidence
  for Task snapshots, but relabelling their subject as the proposed journal is
  precisely the authority ambiguity ADR-069 is supposed to remove.

### ADR-078 — Code OSS incumbent versus Theia challenger

- **Falsifiers fulfilled? NOT VERIFIABLE / not run; coverage incomplete.** The partial Code OSS
  spike disproves “the selected host obviously cannot carry any Atlas seam”,
  but does not prove every Workbench contract. No required donor capability
  was shown impossible to isolate or reimplement lawfully.
- **Fresh upstream evidence:** Code OSS 1.132.1, VSCodium 1.126.04524 and Theia
  v1.74.1 are the latest stable releases observed. Since 2026-05-14 their
  official release APIs returned 19, 2 and 9 stable releases respectively
  (plus one Theia `next` prerelease). Counts describe cadence, not TCO.
- **Theia evidence:** its official comparator covers 2,655 API rows at v1.74.1
  (2,400 Supported, 24 Partial, 231 Stubbed) through VS Code 1.130.0. Its
  recursive tree was reported as 4.153× smaller by blob count and 6.465× by
  TS/TSX bytes than Code OSS 1.132.1. Those are surface proxies, and the exact
  API response/parser was not preserved in-repo, so the measurement is not
  reproducible from this checkout. Theia supports modular
  compile-time extensions and Workspace Trust, but has explicit trust gaps,
  no security backports, a two-minor API lag and no Atlas spike.
- **Operator-decision challenge:** the working Code OSS bridge creates sunk
  cost; repository size creates an opposite simplicity bias toward Theia.
  Neither is maintenance evidence. When authorized, run an isomorphic Theia
  spike and compare full build/start, contract parity, host delta, an upstream
  upgrade, packaging and runtime resources.
- **Disposition:** retain Code OSS/VSCodium as provisional incumbent and Theia
  as measured challenger. Do not open Cut 2 while today's operator stop holds.

Primary sources: [Code OSS release](https://github.com/microsoft/vscode/releases/tag/1.132.1),
[VSCodium release](https://github.com/VSCodium/vscodium/releases/tag/1.126.04524),
[Theia release](https://github.com/eclipse-theia/theia/releases/tag/v1.74.1),
[Theia comparator](https://eclipse-theia.github.io/vscode-theia-comparator/status.html),
[Theia extensions](https://theia-ide.org/docs/extensions/),
[Workspace Trust](https://theia-ide.org/docs/workspace_trust/) and
[Theia security policy](https://raw.githubusercontent.com/eclipse-theia/theia/v1.74.1/SECURITY.md).

## Cónclave

Full high-risk deliberation returned **UNKNOWN**, not `BLOCKING`: only two of
three required lineages were reachable. Llama and Hermes both raised `MAJOR`
concerns that merely retaining `PROVISIONAL` could become passive unless each
ADR named a next experiment. Mistral was rejected for insufficient OpenRouter
credit at the requested output cap; Qwen rate-limited and Ollama timed out.
The two reachable objections motivated the explicit “what would move it”
contracts above; they did not supply evidence that any falsifier passed.

## Cycle 6 — challenge to the operator thesis

The literal thesis “audit apparatus with a runtime inside” is rejected as a
strong security claim. RFC 9162 protects inclusion/consistency but leaves
inconsistent-view remedies out of scope; SCITT/RFC 9943 says registered
statements can be false or selectively omitted; METR observed routing and
subagent gaps before monitoring; AISI found a weaker synchronous monitor safer
than its best asynchronous one in deployment simulations. A Merkle tree may
therefore remain intact while being incomplete.

The evidence-supported replacement is “an untrusted runtime behind an
externally imposed control/evidence plane”: synchronous effect admission for
high or irreversible actions, bounded execution, separate statements/receipts
and independently operated witness quorum. Atlas has useful local primitives,
but external witnesses, privilege/key independence and off-path completeness
are **NOT VERIFIABLE**. Full evidence and primary links:
`work/research/OVERSIGHT_TRANSPARENCY_MCP_VETTING_2026-08-12.md`.

## Commands and evidence classes

- `scripts/check_canon.py --root .`: exit 0 (before this report).
- Kuzu read-only label counts: exit 0, 0/0/0.
- ADR-057 authority suite: exit 0, 13 passed. An earlier command named the
  nonexistent `tests/test_memory_promotion.py` and exited 4; no product test
  ran in that attempt.
- ADR-058 focused suite: exit 0, 42 passed.
- ADR-069 focused suite: exit 0, 9 passed.
- Cónclave transport: exit 0; verdict UNKNOWN due to reachable diversity 2/3.
- Official GitHub release/tree/compare API queries and Theia comparator parser:
  exit 0. Code OSS/VSCodium/Theia stable counts 19/2/9; tree measurements and
  API-support counts are recorded above and in the ADR-078 dossier.
- Code OSS checkout read-only status/diff: exit 0, tracked clean, 6 files
  `+588/-1`. The delegated Node test execution returned 21/21 but was
  procedurally non-compliant and retrospectively Merkle-recorded.
- RFC/AISI/METR/SCITT/Sigstore/MCP/SLSA/in-toto primary-source reads: network
  success; C2SP witness/cosignature fetch returned HTTP 200, command exit 0.
- Fresh MCP structure calls: success at graph/head/server `4fab366`; no witness
  or SCITT module, and no graph edge joining the two local Merkle trees.

Classification: test results and source/runtime observations are **VERIFIED**;
the unimplemented falsifiers are **NOT VERIFIABLE**; the 2026-07-31 manual PID
check and the historical full Code OSS build/start are
**REPORTED-SIN-CONFIRMAR** in this session. TCO and Atlas/Theia integration are
**NOT VERIFIABLE** without the future spike.
