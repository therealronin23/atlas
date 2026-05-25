# ADR-016 Extension: InferenceHub `auto` mode behavior

Status: Updated

Context
-------
ADR-016 defines the role of LiteLLM as the inference backend. The project supports three operation modes for `InferenceHub`: `auto`, `live`, and `stub`.

Decision
--------
This note documents a clarification and a minor behavioural change introduced to `InferenceHub.infer()`:

- When `mode="auto"`, `InferenceHub` will attempt to run providers live when possible (e.g. when provider API keys are present or for local L0 providers such as Ollama). If a provider cannot be used because no API key is configured, the provider call is *skipped* with an `auto-skip` result instead of silently returning a stub success.

- If all providers fail or are skipped, the final `InferenceResponse.mode` will reflect the reason from the last provider attempt (for example `auto-skip`, `live`, or `stub`). This makes it easier to diagnose why `infer()` returned no live response.

Consequences
------------
- Test coverage was added to assert the `auto` mode behaviour both inside and outside pytest, including:
  - `auto` in pytest -> stub responses (preserves hermetic tests)
  - `auto` outside pytest with provider keys -> live calls
  - `auto` outside pytest without keys -> responses indicate `auto-skip`

- `InferenceHub.infer()` now propagates the `mode` string from the last provider response when constructing the final failure response.

- The change is backwards compatible: callers that previously inspected `InferenceResponse.mode` will see more informative values in failure cases.

Notes
-----
- Tests: `tests/test_inference_hub_real.py` was extended; the full test suite passes locally (`521 passed`).
- If you want the PR to target a different base branch than `main`, specify it when creating the PR.

Signed-off-by: Atlas CI
