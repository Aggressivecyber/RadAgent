# TUI Copilot Model Options Design

## Goal

Make the Ctrl+P options panel able to change the active Copilot model and its
context window directly, instead of only showing `/model` command examples.

## Current Behavior

The TUI service layer already exposes `pro_model` and
`pro_context_window_tokens` through `RadAgentAppService.update_model_config()`.
The `/model` command can persist those values, but the Ctrl+P options panel only
has selectable rows for language and theme. The model section is static help
text, so keyboard users cannot switch Copilot settings from the panel.

## Design

Add two selectable rows to the Ctrl+P options panel:

- `Copilot Model`: cycles through model names built from the current `pro`
  model, current `lite`/`max` model names, and common MiMo Copilot candidates.
- `Copilot Window`: cycles through `100k`, `200k`, `500k`, and `1m`, seeded
  from the current `pro_context_window_tokens` when it matches one of those
  values.

The panel keeps the existing interaction model:

- Up/Down selects an option row.
- Left/Right changes the selected draft value.
- Enter applies all changed draft values at once.

Applying model or window changes calls the existing service API with
`{"pro_model": ..., "pro_context_window_tokens": ...}`. That keeps persistence,
process environment updates, gateway reset, and `model_config_updated` events in
the application service layer.

## Out Of Scope

The panel will not edit API keys, base URLs, per-tier timeouts, or max-token
limits. Those remain available through `/model ...` because free-form secrets
and endpoint URLs are better handled by explicit command input.

## Testing

Add focused Textual pilot tests that open Ctrl+P, navigate to the Copilot model
and window rows, change values with Right, apply with Enter, and assert that the
project `.env` contains the corresponding `RADAGENT_MODEL_PRO` and
`RADAGENT_PRO_CONTEXT_WINDOW_TOKENS` values.
