# TUI Copilot Model Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add keyboard-selectable Copilot model and context-window controls to the Ctrl+P TUI options panel.

**Architecture:** Keep UI draft state in `agent_core/tui/app.py` and persist changes through `RadAgentAppService.update_model_config()`. Do not bypass the service layer or expose secrets in the options panel.

**Tech Stack:** Python, Textual pilot tests, pytest.

---

### Task 1: Add Failing TUI Tests

**Files:**
- Modify: `tests/unit/test_tui_textual_app.py`

- [ ] **Step 1: Write the failing test**

Add tests that open Ctrl+P, navigate to `Copilot Model` and `Copilot Window`,
change each with Right, apply with Enter, and assert the project `.env` values.

- [ ] **Step 2: Verify red**

Run:

```bash
python -m pytest -q tests/unit/test_tui_textual_app.py::test_options_panel_keyboard_updates_copilot_model tests/unit/test_tui_textual_app.py::test_options_panel_keyboard_updates_copilot_context_window
```

Expected: tests fail because the panel has no selectable Copilot model/window
rows yet.

### Task 2: Implement Draft State And Apply Logic

**Files:**
- Modify: `agent_core/tui/app.py`

- [ ] **Step 1: Extend option rows**

Add `copilot_model` and `copilot_window` after `theme` in `_OPTION_ROWS`.

- [ ] **Step 2: Initialize draft values from service config**

When opening Ctrl+P, read `service.get_model_config()` and seed draft values
from the `pro` tier.

- [ ] **Step 3: Cycle values with Left/Right**

Use current config plus common MiMo candidates for model names, and
`100k/200k/500k/1m` for context windows.

- [ ] **Step 4: Apply changed values through service**

On Enter, call `service.update_model_config()` only when model or window values
changed, then refresh the options state and add the existing success row.

### Task 3: Verify

**Files:**
- Test: `tests/unit/test_tui_textual_app.py`

- [ ] **Step 1: Run focused tests**

```bash
python -m pytest -q tests/unit/test_tui_textual_app.py::test_ctrl_p_opens_selectable_options_panel tests/unit/test_tui_textual_app.py::test_options_panel_keyboard_updates_theme_and_language tests/unit/test_tui_textual_app.py::test_options_panel_keyboard_updates_copilot_model tests/unit/test_tui_textual_app.py::test_options_panel_keyboard_updates_copilot_context_window
```

- [ ] **Step 2: Run model parser regression tests**

```bash
python -m pytest -q tests/unit/test_tui_commands.py tests/unit/test_app_service.py::test_service_updates_model_config_for_frontend
```

- [ ] **Step 3: Review diff**

Confirm the diff only touches the planned files and does not revert unrelated
dirty work.
