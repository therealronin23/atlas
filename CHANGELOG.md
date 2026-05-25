# Changelog

All notable changes to this project will be documented in this file.

## [0.6.1] - 2026-05-25

### Added

- `InferenceHub.infer()` now propagates the final response `mode` from the last provider attempt, including `auto-skip` when providers are skipped due to missing API keys.
- Added explicit documentation for the `InferenceHub auto` mode behavior in `docs/adr_016_inferencehub.md`.

### Fixed

- Ensured `InferenceHub` failure responses in `auto` mode retain the last provider attempt reason, improving observability for fallback and skip conditions.

### Testing

- Verified locally with the full test suite: `521 passed`.
