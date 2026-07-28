# Product Lineage Reconciliation Report

Date: 2026-07-28
Canonical target: `atlas-core` candidate branch
Method: semantic capability comparison, never topology-only merge

## Result

No disconnected precursor commit needs to be cherry-picked into Cut 0. The
substantive Doc0 backend and shell capabilities already exist in the canonical
repository. The editor repositories preserve real product work for the later,
comprehensive Atlas Workbench convergence.

| Source | Verified content | Disposition |
|---|---|---|
| Doc0 capability precursor `d01d4b9` | ACP, coding bridge, Git checkpoints, Home Assistant, image/video generation, lesson lifecycle and NebulaGraph | `PRESENT_CANONICALLY` |
| Doc0 canon precursor `3284d61` | governance and hosted-convergence precursor documents | `HISTORICAL_PRECURSOR`; reconcile semantically |
| Void baseline `d8e96ed` | Atlas provider-role and bridge baseline | `PORT_LATER` |
| Void forward port `34803da` | port 7342 service, lifecycle ownership/supervision and tests; 443 insertions/22 deletions across eight files | `PORT_LATER` |
| Code OSS `8a7abeba` | current host spike without Atlas commits | `HOST_BASELINE` |
| Zed `c9e8e611` | ACP/client and product-interaction reference | `PATTERN_ONLY` |
| Self-build `9ffbf78` | `atlas update status` HITL next-step recipe and tests | `PRESENT_CANONICALLY` |
| Worktrees whose commits are ancestors of `c95038c` | maintenance, discovery, provider, audit and GUI precursor commits | `ALREADY_INTEGRATED` |

## Doc0 capability evidence

| Capability | Canonical implementation | Test evidence | Fresh result |
|---|---|---|---|
| ACP adapter | `src/atlas/acp/server.py` | `tests/test_acp_server.py` | `OPTIONAL_DEPENDENCY_MISSING`: seven tests require the `acp` extra |
| Coding bridge | `src/atlas/api/coding_server.py` | no dedicated direct test | `CODE_PRESENT`; contract-test gap retained |
| Git checkpoints | `src/atlas/core/git_checkpoint.py` | checkpoint and agentic wiring tests | pass |
| Home Assistant | `src/atlas/tools/home_assistant_tool.py` | `tests/test_home_assistant_tool.py` | pass |
| Image generation | `src/atlas/tools/image_gen_tool.py` | `tests/test_image_gen_tool.py` | pass |
| Video generation | `src/atlas/tools/video_gen_tool.py` | `tests/test_video_gen_tool.py` | pass |
| Lesson lifecycle | canonical lesson store/recaller paths | `tests/test_lesson_lifecycle.py` | pass |
| NebulaGraph | `ui/atlas-shell/src/components/NebulaGraph.tsx`, wired by `App.tsx` | UI build gate | final Cut 0 build pending |

The focused command produced 60 passing tests and seven ACP failures caused by
`ModuleNotFoundError: acp`. `agent-client-protocol` is already a declared
optional extra and CI installs it. No dependency was installed merely to turn
the local result green.

## Workbench source boundary

The Void forward port is real code, not research prose. It remains outside
`atlas-core` in Cut 0 because its destination is the product host, not the
Python kernel. Cut 2 is not constrained to a minimal or bounded port: its exact
comprehensive convergence will be designed after the internal engineering
contracts of Cut 1 are accepted.

Code OSS and Zed are not merged into the current candidate. Code OSS supplies
the host baseline; VSCodium supplies the privacy/build/update discipline; Void
supplies implemented Atlas bridge capabilities; Zed supplies ACP capabilities
and product patterns. Each remains untrusted until its dedicated licensing,
dependency, security, test, update and rollback gates pass.

## Rollback

This reconciliation moves no external source tree. Reverting its canon commit
removes only classifications and reports; every source repository/worktree
remains independently recoverable.
