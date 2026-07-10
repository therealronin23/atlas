# Research 02 — UI Tech Decision

Decision:

- `ui/atlas-shell` is Atlas Web Harness.
- Slint is primary candidate for native shell/control/workbench frames.
- wgpu is primary candidate for Living Core / Cognitive Surface.
- Tauri is fallback/hybrid/package/dev console.
- egui is developer/debug only.
- iced is secondary candidate.

Architecture:

```text
Atlas Core → OS Bridge / WS Events → Native Atlas Client
Native Client → Slint Shell + wgpu Cognitive Surface
```

Native spike must show Universal Bar, left nav, cognitive surface placeholder, inspector and bottom timeline.
