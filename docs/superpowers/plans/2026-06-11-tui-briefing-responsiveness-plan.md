# TUI Briefing Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make startup status explicit, keep the current simulation task visible in a right-side context frame, make slow simulation briefing feel alive, expose a collapsed model trace, ask one guided question at a time, compact historical briefing memory with the lite model when it exceeds 75% of the configured Copilot context window, and keep job workspace names compact with a UUID plus creation timestamp.

**Architecture:** The TUI owns visible interaction state: startup status frame, right-side task context, Copilot context usage bar, workflow step rail, pending rows, spinner text, trace inspector, and shortcut handling. `RadAgentAppService` owns frontend-safe runtime/model status so UI code never probes secrets or tools ad hoc. `TUIController` remains the workflow state machine for intent, briefing, approval, latest context-window usage, and compact state. `SimulationBriefingPlanner` returns a guided briefing schema and uses lite `CONTEXT_SUMMARY` to compact older historical briefing memory before MAX calls once estimated usage exceeds 75% of the selected context window.

**Tech Stack:** Python async, Textual pilot tests, Pydantic schemas, `ModelGateway`, existing `RadAgentAppService` event stream.

---

## File Map

- Modify `agent_core/tui/models.py`: add row kinds and optional detail payload conventions for `thinking` and `model_trace`.
- Modify `agent_core/tui/adapters.py`: render compact pending/thinking rows, collapsed trace rows, approved task summaries, and workflow step rail without polluting the main transcript.
- Modify `agent_core/tui/app.py`: render the startup RadAgent status frame, add the right-side task context frame, run controller handling in a background worker, add a reserved-width spinner row, add `Ctrl+T` trace inspector, and keep `/logs` as the full debug view.
- Modify `agent_core/tui/controller.py`: return visible stage metadata, keep guided briefing state, trigger lite task-summary generation after approval, and trigger compaction before long MAX briefing calls.
- Modify `agent_core/chat/briefing.py`: replace bulk-question rendering with a guided `next_question` schema, add lite compaction helper, and keep approval command generation unchanged.
- Modify `agent_core/app/schemas.py`: add frontend-safe runtime status schemas for Geant4, TCAD, ngspice, and active model tiers.
- Modify `agent_core/app/service.py`: expose `get_startup_status()`, pass workflow context and compact briefing state through `brief_simulation`, and surface model trace data when available.
- Modify `agent_core/models/schemas.py`, `agent_core/models/client.py`, `agent_core/models/gateway.py`: preserve provider `reasoning_content` as a public model trace field when returned.
- Modify `agent_core/naming.py`: generate job workspace IDs as `job_<uuid8>__YYYYMMDD_HHMMSS` with no semantic title suffix.
- Modify model config/environment surfaces: expose context window tokens and allow common `100k/200k/500k/1m` shortcuts plus custom `k` unit values.
- Test: `tests/unit/test_tui_textual_app.py`, `tests/unit/test_tui_controller.py`, `tests/unit/test_simulation_briefing.py`, `tests/unit/test_model_gateway.py`, `tests/unit/test_model_tiers.py`.

---

### Task 1: Startup RadAgent Status Frame

**Files:**
- Modify: `agent_core/app/schemas.py`
- Modify: `agent_core/app/service.py`
- Modify: `agent_core/tui/i18n.py`
- Modify: `agent_core/tui/app.py`
- Modify: `agent_core/tui/adapters.py`
- Test: `tests/unit/test_app_service.py`
- Test: `tests/unit/test_tui_textual_app.py`

- [ ] **Step 1: Write the failing service test**

Add a test that constructs `RadAgentAppService`, calls `get_startup_status()`, and asserts it returns frontend-safe fields only:

```python
def test_startup_status_reports_tools_and_models_without_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_MODEL_LITE", "lite-test")
    monkeypatch.setenv("RADAGENT_MODEL_PRO", "pro-test")
    monkeypatch.setenv("RADAGENT_MODEL_MAX", "max-test")
    monkeypatch.setenv("RADAGENT_API_KEY", "secret-value")
    monkeypatch.setenv("NGSPICE_BIN", "/usr/bin/ngspice")
    monkeypatch.setenv("TCAD_INSTALL_DIR", "/opt/synopsys/tcad")

    service = RadAgentAppService(workspace_root=tmp_path)
    status = service.get_startup_status()

    assert status.product_name == "RadAgent"
    assert status.tools["geant4"].label == "Geant4"
    assert status.tools["tcad"].configured is True
    assert status.tools["ngspice"].path == "/usr/bin/ngspice"
    assert status.models["lite"].model_name == "lite-test"
    assert status.models["pro"].model_name == "pro-test"
    assert status.models["max"].model_name == "max-test"
    assert status.models["lite"].api_key_configured is True
    assert "secret-value" not in status.model_dump_json()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/unit/test_app_service.py::test_startup_status_reports_tools_and_models_without_secrets`

Expected: FAIL because `get_startup_status()` and schemas do not exist.

- [ ] **Step 3: Add frontend-safe schemas**

In `agent_core/app/schemas.py`, add:

```python
class RuntimeToolStatus(BaseModel):
    label: str
    configured: bool = False
    available: bool = False
    path: str = ""
    detail: str = ""


class StartupModelStatus(BaseModel):
    tier: str
    model_name: str
    base_url_configured: bool = False
    api_key_env: str = "RADAGENT_API_KEY"
    api_key_configured: bool = False
    thinking_default: bool = False


class StartupStatusView(BaseModel):
    product_name: str = "RadAgent"
    project: str = "default"
    execution_mode: str = "strict"
    run_mode: str = "strict"
    tools: dict[str, RuntimeToolStatus] = Field(default_factory=dict)
    models: dict[str, StartupModelStatus] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement `get_startup_status()`**

In `agent_core/app/service.py`, call `load_environment(self.env_path)` and `get_model_config()`. Report:

- `geant4`: configured when `geant4_config_bin` or `geant4_install_dir` is set; available when `geant4_config_bin` is executable or `Geant4Runner().geant4_available` is true; detail includes `cmake` configured/missing.
- `tcad`: configured when any TCAD install/tool/container value is set; available when an install dir exists or one TCAD tool path is executable; detail names `sde`, `svisual`, `swb`, and `docker` presence.
- `ngspice`: configured when `ngspice_bin` is set; available when it is executable; detail is the path or `set NGSPICE_BIN`.
- `models`: lite/pro/max model name, key env name, key configured boolean, base URL configured boolean, and thinking default.

- [ ] **Step 5: Write failing TUI frame test**

Add a Textual pilot test that mounts the app and asserts the first timeline row is a framed brand/status row:

```python
@pytest.mark.asyncio
async def test_startup_renders_radagent_status_frame(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        first = app._rows[0]
        assert first.kind == "brand"
        assert "RadAgent" in first.summary
        assert "Geant4" in first.summary
        assert "TCAD" in first.summary
        assert "ngspice" in first.summary
        assert "Models" in first.summary
        assert "lite" in first.summary
        assert "pro" in first.summary
        assert "max" in first.summary
```

- [ ] **Step 6: Render the status frame**

Replace the current raw logo-only startup row with a compact ASCII frame generated from `service.get_startup_status()`. Keep it small enough for 80-column terminals:

```text
+ RadAgent --------------------------------+
| project default  mode strict             |
| Geant4   ok      cmake ok                |
| TCAD     config  sde/svisual/swb mixed   |
| ngspice  missing set NGSPICE_BIN         |
| Models   lite mimo-v2.5 | pro mimo...    |
+------------------------------------------+
```

Use status words `ok`, `config`, `missing`, and `off` so color is not required. Add an Options line that tells users `Ctrl+P` reopens runtime status; keep `/status` for active job status so command semantics stay stable.

- [ ] **Step 7: Verify**

Run:

```bash
python -m pytest -q tests/unit/test_app_service.py::test_startup_status_reports_tools_and_models_without_secrets
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py::test_startup_renders_radagent_status_frame
python -m ruff check agent_core/app/schemas.py agent_core/app/service.py agent_core/tui tests/unit/test_app_service.py tests/unit/test_tui_textual_app.py
```

Expected: PASS.

---

### Task 1.5: Job Workspace Naming Without Semantic Suffixes

**Files:**
- Modify: `agent_core/naming.py`
- Test: `tests/unit/test_naming.py`

- [ ] **Step 1: Write the failing naming test**

Assert generated job IDs use only UUID and creation time, and do not call model/title generation:

```python
result = await build_job_id("", "proton detector")
assert result == "job_abcdef12__20260611_150405"
```

The suffix is local creation time in `YYYYMMDD_HHMMSS` 24-hour format. User-provided `base_id` remains unchanged.

- [ ] **Step 2: Implement the naming contract**

In `agent_core/naming.py`, keep legacy title helpers available for compatibility, but make `build_job_id()` return:

```text
job_<uuid8>__YYYYMMDD_HHMMSS
```

Do not call the lite model or append semantic words to directories under `workspace/jobs`.

- [ ] **Step 3: Verify**

Run:

```bash
python -m pytest -q tests/unit/test_naming.py
```

Expected: PASS.

---

### Task 2: Right-Side Task Context And Workflow Step Rail

**Files:**
- Modify: `agent_core/tui/app.py`
- Modify: `agent_core/tui/adapters.py`
- Modify: `agent_core/tui/i18n.py`
- Modify: `agent_core/tui/controller.py`
- Modify: `agent_core/chat/briefing.py`
- Modify: `agent_core/app/service.py`
- Test: `tests/unit/test_tui_textual_app.py`
- Test: `tests/unit/test_tui_adapters.py`
- Test: `tests/unit/test_tui_controller.py`
- Test: `tests/unit/test_simulation_briefing.py`
- Test: `tests/unit/test_app_service.py`

- [ ] **Step 1: Write the failing layout test**

Add a Textual pilot test that mounts the app and asserts a right-side task context frame exists separately from the main timeline:

```python
@pytest.mark.asyncio
async def test_task_context_side_frame_mounts_without_covering_composer(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        workbench = app.query_one("#workbench")
        timeline = app.query_one("#timeline")
        prompt = app.query_one("#prompt")
        task_context = app.query_one("#task-context")

        assert task_context.region.x > timeline.region.x
        assert task_context.region.y >= workbench.region.y
        assert task_context.region.height <= workbench.region.height
        assert prompt.region.y + prompt.region.height < app.query_one("#footer").region.y
        assert "Task" in str(task_context.content)
        assert "Workflow" in str(task_context.content)
```

- [ ] **Step 2: Write the failing workflow rail test**

Add a test that starts from a fake status at `g4_modeling` with completed phases through `task_planning`, then asserts the right frame shows the job id, approved short summary, and previous/current/next workflow nodes:

```python
from agent_core.app import JobStatus


@pytest.mark.asyncio
async def test_task_context_marks_previous_current_and_next_workflow_steps(tmp_path) -> None:
    class _WorkflowService(RadAgentAppService):
        def get_status(self) -> JobStatus:
            return JobStatus(
                job_id="job_he3",
                user_query="Build a He3 tube neutron detector simulation.",
                status="running",
                current_phase="g4_modeling",
                current_phase_idx=3,
                completed_phases=["prepare_workspace", "context", "task_planning"],
                execution_mode="strict",
                run_mode="strict",
                workspace_root=str(tmp_path),
                state={
                    "task_summary_short": {
                        "zh": "He3管热中子探测效率仿真",
                        "en": "He3 tube thermal-neutron efficiency",
                    }
                },
            )

    app_cls = create_app_class()
    app = app_cls(service=_WorkflowService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        content = str(app.query_one("#task-context").content)
        assert "job_he3" in content
        assert "He3 tube thermal-neutron efficiency" in content
        assert "prev  Task planning" in content
        assert "now   G4 modeling" in content
        assert "next  Human confirmation" in content
```

- [ ] **Step 3: Write the failing pre-approval summary test**

Add a test that puts the controller in briefing state before approval and asserts the side frame shows only the id area and workflow, with no generated simulation summary line:

```python
@pytest.mark.asyncio
async def test_task_context_hides_simulation_summary_before_plan_approval(tmp_path) -> None:
    class _BriefingOnlyService(RadAgentAppService):
        def get_status(self) -> JobStatus:
            return JobStatus(
                job_id="job_pending",
                status="idle",
                current_phase="",
                current_phase_idx=0,
                completed_phases=[],
                execution_mode="strict",
                run_mode="strict",
                workspace_root=str(tmp_path),
                state={},
            )

    app_cls = create_app_class()
    app = app_cls(service=_BriefingOnlyService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        content = str(app.query_one("#task-context").content)
        assert "job_pending" in content
        assert "仿真" not in content
        assert "plan" not in content.lower()
        assert "summary" not in content.lower()
```

- [ ] **Step 4: Write the failing lite summary test**

Add a controller or briefing test proving approval triggers a lite-model short summary from the approved simulation plan:

```python
@pytest.mark.asyncio
async def test_approval_generates_lite_bilingual_short_task_summary() -> None:
    class _SummaryService(_FakeService):
        async def summarize_approved_simulation_plan(self, briefing_context: dict[str, Any]) -> dict[str, str]:
            assert "Build a Geant4 silicon detector" in briefing_context["final_query"]
            return {
                "zh": "硅探测器沉积能量仿真",
                "en": "Silicon detector edep simulation",
            }

    service = _SummaryService()
    controller = TUIController(service)
    await controller.handle_text("我要仿真一个硅探测器")

    result = await controller.handle_text("确定")
    await result.operation

    context = service.started_jobs[0]["briefing_context"]
    assert context["task_summary_short"] == {
        "zh": "硅探测器沉积能量仿真",
        "en": "Silicon detector edep simulation",
    }
    assert len(context["task_summary_short"]["zh"]) <= 50
    assert len(context["task_summary_short"]["en"]) <= 50
```

- [ ] **Step 5: Add lite plan-summary helper**

In `agent_core/chat/briefing.py`, add a lite summarizer that uses `ModelTask.CONTEXT_SUMMARY` on `ModelTier.LITE` and returns JSON with `zh` and `en`, each no longer than 50 characters:

```python
class ApprovedPlanSummarizer:
    def __init__(self, *, gateway_factory: Callable[[], Any] = get_model_gateway) -> None:
        self._gateway_factory = gateway_factory

    async def summarize(self, briefing_context: Mapping[str, Any]) -> dict[str, str]:
        gateway = self._gateway_factory()
        result = await gateway.call(
            task=ModelTask.CONTEXT_SUMMARY,
            tier=ModelTier.LITE,
            system_prompt=(
                "Summarize the approved simulation plan for a TUI side panel. "
                "Return only one concise phrase, <=50 characters. "
                "No markdown, no punctuation-heavy explanation."
            ),
            user_prompt=json.dumps(briefing_context, ensure_ascii=False),
            response_format="json",
            temperature=0.0,
            max_tokens=128,
            metadata={"module_name": "tui_task_summary"},
        )
        if result.error:
            raise RuntimeError(f"Task summary failed: {result.error}")
        return {
            "zh": _clip_task_summary(result.parsed_json.get("zh", "")),
            "en": _clip_task_summary(result.parsed_json.get("en", "")),
        }
```

Implement `_clip_task_summary()` so tests can verify the hard cap without depending on model obedience.

- [ ] **Step 6: Trigger summary only after approval**

In `TUIController._handle_briefing_reply()`, when `_is_approval(text)` succeeds and before `service.start_job(...)`, call `service.summarize_approved_simulation_plan(briefing_context)` if the service exposes it. Store the returned bilingual dict as `briefing_context["task_summary_short"]`. If the lite summary call fails, skip the summary and continue starting the job; the side frame should never block approval/start on a summary failure.

Add `RadAgentAppService.summarize_approved_simulation_plan()` as the service wrapper around `ApprovedPlanSummarizer`, then in `RadAgentAppService.start_job()` copy `briefing_context["task_summary_short"]` into `self.state["task_summary_short"]` so `get_status()` exposes it in `status.state`. Also copy `context_window_stats` into `state["copilot_context_usage"]`.

- [ ] **Step 7: Add render helpers**

In `agent_core/tui/adapters.py`, add pure helpers:

```python
def render_task_context(status: JobStatus) -> str:
    summary_map = status.state.get("task_summary_short", {})
    summary = summary_map.get(language, "") if isinstance(summary_map, dict) else ""
    lines = [
        "Task",
        f"job   {status.job_id or 'no-job'}",
    ]
    if summary:
        lines.append(_clip_line(summary, 50))
    lines.extend(
        [
            "",
            "Workflow",
            *_workflow_step_lines(status),
        ]
    )
    return "\n".join(
        lines
    )
```

Use `PIPELINE_PHASES` and a local label map:

```python
_PHASE_LABELS = {
    "prepare_workspace": "Prepare workspace",
    "context": "Context",
    "task_planning": "Task planning",
    "g4_modeling": "G4 modeling",
    "human_confirmation": "Human confirmation",
    "g4_codegen": "G4 codegen",
    "patch": "Patch",
    "gate": "Gate checks",
    "artifact": "Artifacts",
    "report": "Report",
}
```

Render exactly three adjacent rows when there is an active phase:

```text
prev  Task planning        ok
now   G4 modeling          run
next  Human confirmation   wait
```

When no job is active, render:

```text
prev  -
now   Briefing / idle      wait
next  Prepare workspace    wait
```

- [ ] **Step 8: Update the Textual layout**

Change the workbench from a single vertical region into a horizontal body:

```python
with vertical(id="workbench"):
    with horizontal(id="main-split"):
        with vertical(id="conversation-pane"):
            yield vertical_scroll(id="timeline")
            with horizontal(id="composer"):
                yield input_widget(...)
        yield static("", id="task-context", markup=False)
```

CSS requirements:

- `#main-split` takes `height: 1fr`.
- `#conversation-pane` takes `width: 1fr`.
- `#task-context` has a fixed width around `34`, `border: heavy`, and padding `1`.
- On narrow terminals, hide or collapse `#task-context` before allowing composer overlap. The first implementation can use `display: none` under a Textual CSS narrow-width rule if supported; if not, keep width `30` and enforce existing prompt/footer geometry tests.

- [ ] **Step 9: Refresh the side frame on state changes**

Add `_refresh_task_context()` in `app.py` and call it from:

- `on_mount`
- `_refresh_header`
- `_add_event_row`
- after `_show_options()` language changes
- after starting and finishing operations

The method should read `self.service.get_status()` and update `#task-context` with `render_task_context(status)`.

- [ ] **Step 10: Verify**

Run:

```bash
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py::test_task_context_side_frame_mounts_without_covering_composer
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py::test_task_context_marks_previous_current_and_next_workflow_steps
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py::test_task_context_hides_simulation_summary_before_plan_approval
python -m pytest -q tests/unit/test_tui_controller.py::test_approval_generates_lite_short_task_summary
python -m pytest -q tests/unit/test_tui_adapters.py
python -m pytest -q tests/unit/test_simulation_briefing.py
python -m pytest -q tests/unit/test_app_service.py
```

Expected: PASS.

---

### Task 3: Visible Pending State For Slow Intent And Briefing

**Files:**
- Modify: `agent_core/tui/app.py`
- Modify: `agent_core/tui/models.py`
- Modify: `agent_core/tui/adapters.py`
- Test: `tests/unit/test_tui_textual_app.py`

- [ ] **Step 1: Write the failing test**

Add a Textual pilot test that blocks `brief_simulation` on an `asyncio.Event`, submits `我想要 he3 管仿真`, and asserts a running row appears before the event is released:

```python
def _ready_guided_briefing() -> object:
    class _Briefing:
        status = "ready_for_approval"
        ready_for_approval = True
        understanding = "用户想做 He3 管中子探测仿真。"
        questions: list[str] = []
        recommendations = ["先用热中子源和小事件数验证几何。"]
        draft_plan = {"objective": "He3 tube neutron detection response"}
        missing_critical_fields: list[str] = []
        assumptions = ["默认采用热中子源。"]
        risks = ["He3 气压和管壁材料会影响探测效率。"]
        final_query = "Build a Geant4 He3 tube neutron detector simulation."
        approval_request = {
            "requires_human_approval": True,
            "summary": "Start He3 tube simulation.",
            "risks": risks,
        }

        def summary_text(self) -> str:
            return self.approval_request["summary"]

    return _Briefing()


@pytest.mark.asyncio
async def test_slow_briefing_shows_pending_row_before_model_returns(tmp_path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowBriefingService(RadAgentAppService):
        async def classify_intent(self, text: str) -> IntentResult:
            return IntentResult(
                intent="simulation_work",
                confidence=0.95,
                routing_reason="simulation request",
                normalized_user_query=text,
                intent_detail="simulation_request",
                requires_job=True,
                requires_simulation_pipeline=True,
            )

        async def brief_simulation(self, user_message: str, *, conversation: list[dict]) -> object:
            started.set()
            await release.wait()
            return _ready_guided_briefing()

    app_cls = create_app_class()
    app = app_cls(service=_SlowBriefingService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt").value = "我想要 he3 管仿真"
        await pilot.press("enter")
        await started.wait()
        await pilot.pause()

        assert any(row.kind == "thinking" and row.status == "running" for row in app._rows)
        assert any("分析仿真需求" in row.summary or "Analyzing" in row.summary for row in app._rows)

        release.set()
        await pilot.pause()
        assert any(row.title == "Simulation briefing" for row in app._rows)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py::test_slow_briefing_shows_pending_row_before_model_returns`

Expected: FAIL because no `thinking` row is appended until `brief_simulation` returns.

- [ ] **Step 3: Implement minimal pending-row support**

Add `kind="thinking"` rendering in `adapters.py`, then change `_dispatch_controller_text` in `app.py` so plain text immediately appends a running row and starts a worker. Use a fixed spinner label such as `"[run] Copilot analyzing..."`; update the same row or replace it when the controller result returns. Reserve the spinner width so layout does not shift.

- [ ] **Step 4: Verify**

Run:

```bash
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py::test_slow_briefing_shows_pending_row_before_model_returns
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py
```

Expected: PASS.

---

### Task 4: Collapsed Model Trace Inspector

**Files:**
- Modify: `agent_core/models/schemas.py`
- Modify: `agent_core/models/client.py`
- Modify: `agent_core/models/gateway.py`
- Modify: `agent_core/tui/app.py`
- Modify: `agent_core/tui/adapters.py`
- Test: `tests/unit/test_model_gateway.py`
- Test: `tests/unit/test_tui_textual_app.py`

- [ ] **Step 1: Write failing gateway test**

Add a test that provider payload with `message.reasoning_content` becomes `ModelCallResult.reasoning_content`:

```python
assert result.reasoning_content == "public reasoning summary"
assert result.usage.get("reasoning_content") is None
```

- [ ] **Step 2: Implement trace capture**

Add `reasoning_content: str = ""` to `ModelCallResult`. In `client.py`, return usage without `reasoning_content` and a third value for reasoning. In `gateway.py`, write the reasoning content to the transcript and result field. Do not synthesize hidden chain-of-thought; only preserve provider-returned reasoning text.

- [ ] **Step 3: Write failing TUI trace test**

In `tests/unit/test_tui_textual_app.py`, emit a fake assistant/model result with `payload={"reasoning_content": "checked He3 tube requirements"}` and press `ctrl+t`. Assert the main row is collapsed/light and the inspector shows the trace.

- [ ] **Step 4: Implement `Ctrl+T`**

Bind `Ctrl+T` to `show_trace`. Store latest trace snippets from assistant/briefing rows. Render them in the inspector with title `Model Trace`; keep `/logs` as the full raw event log.

- [ ] **Step 5: Verify**

Run:

```bash
python -m pytest -q tests/unit/test_model_gateway.py
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py
python -m ruff check agent_core/models agent_core/tui tests/unit/test_model_gateway.py tests/unit/test_tui_textual_app.py
```

Expected: PASS.

---

### Task 5: Guided One-Question Briefing

**Files:**
- Modify: `agent_core/chat/briefing.py`
- Modify: `agent_core/tui/controller.py`
- Modify: `agent_core/tui/app.py`
- Test: `tests/unit/test_simulation_briefing.py`
- Test: `tests/unit/test_tui_controller.py`
- Test: `tests/unit/test_tui_textual_app.py`

- [ ] **Step 1: Write failing schema test**

Add a test where MAX returns:

```json
{
  "status": "needs_input",
  "understanding": "用户想做 He3 管中子探测仿真。",
  "next_question": {
    "field": "source",
    "question": "你主要想模拟哪种入射中子？",
    "choices": ["热中子", "单能快中子", "能谱源", "先用默认热中子"]
  },
  "hidden_questions": ["管长和半径？", "He3 气压？"]
}
```

Assert `briefing.next_question.question` is populated and `summary_text()` returns only that one question.

- [ ] **Step 2: Update prompt and schema**

Add `BriefingQuestion` with `field`, `question`, `choices`, `why`. Replace user-visible bulk question behavior with `next_question`; keep full `hidden_questions` for trace/details only. Update system prompt to ask exactly one highest-impact question unless ready for approval.

- [ ] **Step 3: Update controller**

When `pending_brief` exists, treat free text as answer to `next_question`; accept `1`, `2`, `3`, `4` as choice shortcuts and append the resolved answer to conversation. Continue briefing until `ready_for_approval`.

- [ ] **Step 4: Update TUI rendering**

Show only understanding, one question, and choices in the main briefing row. Put hidden questions, assumptions, and risks behind `Ctrl+T` trace/details.

- [ ] **Step 5: Verify**

Run:

```bash
python -m pytest -q tests/unit/test_simulation_briefing.py tests/unit/test_tui_controller.py
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py
```

Expected: PASS.

---

### Task 6: Lite Compact For Historical Briefing Memory

**Files:**
- Modify: `agent_core/chat/briefing.py`
- Modify: `agent_core/tui/controller.py`
- Modify: `agent_core/models/registry.py`
- Test: `tests/unit/test_simulation_briefing.py`
- Test: `tests/unit/test_model_tiers.py`

- [ ] **Step 1: Write failing compaction test**

Create a fake gateway that records calls and exposes `profiles[ModelTier.MAX].context_window_tokens`. Pass historical briefing memory whose estimated token usage is over 75% of that context window. Assert first call uses `ModelTask.CONTEXT_SUMMARY` on `ModelTier.LITE`, then the MAX briefing prompt includes `compacted_briefing_memory`, `context_window_stats`, only the recent raw turns, and the unchanged latest user message.

- [ ] **Step 2: Implement compaction helper**

Add `BriefingContextCompactor` in `briefing.py`. It compacts only historical briefing memory, not the latest user message and not workflow context. It returns JSON with:

```json
{
  "stable_facts": [],
  "answered_fields": {},
  "open_questions": [],
  "rejected_options": [],
  "latest_user_intent": "",
  "risk_notes": []
}
```

Trigger compaction when estimated historical briefing memory tokens exceed 75% of the selected Copilot context window. Context windows come from model configuration (`context_window_tokens`) and support common options `100k`, `200k`, `500k`, `1m`, plus custom values expressed in `k` units such as `750k` or bare `750` meaning `750k`. Keep the latest 4 historical turns uncompressed.

- [ ] **Step 3: Preserve compact state and usage status**

Store compacted memory in `PendingBrief`. Include it in `briefing_context()` so approved jobs retain the decision trail without sending the full transcript to future model calls. Store `context_window_stats` as `state["copilot_context_usage"]`. The right-side status frame renders a looping Copilot context bar:

```text
Copilot context [########--] 76% cycle 2 200k
Copilot context compacting cycle 3 500k
```

When a compaction cycle is running, show `compacting`. After completion, return to normal usage display for the next cycle while incrementing `cycle`.

- [ ] **Step 4: Verify**

Run:

```bash
python -m pytest -q tests/unit/test_simulation_briefing.py tests/unit/test_tui_controller.py tests/unit/test_model_tiers.py
python -m ruff check agent_core/chat/briefing.py agent_core/tui/controller.py tests/unit/test_simulation_briefing.py tests/unit/test_tui_controller.py
```

Expected: PASS.

---

### Task 7: End-To-End Regression

**Files:**
- Modify only files touched by previous tasks if regressions appear.
- Test: existing TUI and service tests.

- [ ] **Step 1: Run focused regression**

```bash
python -m pytest -q tests/unit/test_tui_commands.py tests/unit/test_tui_i18n.py tests/unit/test_tui_adapters.py tests/unit/test_tui_controller.py tests/unit/test_simulation_briefing.py tests/unit/test_chat_agent_context.py tests/unit/test_app_service.py tests/unit/test_model_tiers.py
/tmp/radagent-tui-venv/bin/python -m pytest -q tests/unit/test_tui_textual_app.py
```

Expected: all pass.

- [ ] **Step 2: Run static checks**

```bash
python -m ruff check agent_core/tui agent_core/chat/briefing.py agent_core/models tests/unit/test_tui_textual_app.py tests/unit/test_simulation_briefing.py tests/unit/test_model_gateway.py
python -m ruff check agent_core/app/schemas.py agent_core/app/service.py tests/unit/test_app_service.py
python -m compileall -q agent_core/tui agent_core/chat agent_core/models tests/unit
```

Expected: all pass.

- [ ] **Step 3: Manual smoke**

Launch `radagent-tui`, verify the first screen contains the RadAgent status frame with Geant4/TCAD/ngspice/model rows, verify the right-side frame shows `Task`, `Copilot context`, and `Workflow`, type `我想要 he3 管仿真`, verify the task frame shows only the id before approval, approve the plan, verify the lite-generated <=50-character language-specific simulation summary appears under the job id with adjacent workflow steps, verify a pending row appears immediately, `Ctrl+T` opens the trace panel, and the first briefing response asks one guided question instead of dumping every missing field. Verify `/options` shows context window options `100k`, `200k`, `500k`, `1m`, and notes custom values use `k`.
