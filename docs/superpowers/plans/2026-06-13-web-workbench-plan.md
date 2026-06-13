# RadAgent Web Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a commercial-quality RadAgent web client with an animated Home surface for workflow capability storytelling and a Web Workbench that covers the current TUI command set through `RadAgentAppService`.

**Architecture:** Use a React/Vite/TypeScript single-page client for Home and Workbench, backed by a thin Python API layer that adapts web requests to the existing UI-neutral `RadAgentAppService`. Home owns immersive animation and project storytelling; Workbench owns dense operational UI: timeline, command composer, status header, side navigation, and inspector drawers for jobs, artifacts, gates, model settings, projects, revisions, logs, confirmations, build, simulation, and visual review.

**Tech Stack:** React 19, Vite 8, TypeScript, Canvas 2D for the suixiang-inspired particle sphere, Python stdlib HTTP server for the first local API slice, existing Pydantic schemas from `agent_core.app.schemas`, pytest for backend TDD, npm/Vite build verification for frontend.

---

## Research Baseline

- `sui-xiang.com/home` uses a public Home route with an immersive hero and a protected console route family (`/dashboard`, `/keys`, `/usage`, `/admin`). The Home page performs brand/config/auth routing and then hands authenticated users into the console.
- The Home sphere is Canvas 2D, not Three.js. It uses a Fibonacci-sphere point distribution, z-depth front/back canvas layers, latitude/longitude guide rings, pointer tilt/repulsion, mobile point-count reduction, and a one-time intro reveal stored in session storage.
- Its console/workbench area switches from immersive storytelling to a restrained operational shell: fixed sidebar, sticky header, content cards, charts/tables, quick actions, user/account controls, notifications, and route-level page metadata.
- RadAgent should use the same cooperation pattern: Home explains workflow capability and completed projects; Workbench is a logged-in-style professional tool surface. The Geant4 visual canvas/workbench remains a later feature inside Workbench, not the main Web Workbench itself.

## File Structure

- Create `agent_core/web/api.py`: pure Python command catalog, command parsing adapter, JSON-safe model conversion, and service method dispatch for Web Workbench.
- Create `agent_core/web/server.py`: local development HTTP server exposing `/api/*` endpoints and serving built Vite assets when present.
- Create `agent_core/web/__init__.py`: package marker and public exports.
- Modify `pyproject.toml`: add `radagent-web` script for launching the local web server.
- Create `tests/unit/test_web_workbench_api.py`: TDD coverage for command catalog, service dispatch, error handling, and JSON-safe responses.
- Create `web_workbench/package.json`: Vite/React/TypeScript scripts and dependencies.
- Create `web_workbench/index.html`: SPA root.
- Create `web_workbench/tsconfig.json`, `web_workbench/tsconfig.node.json`, `web_workbench/vite.config.ts`: TypeScript/Vite configuration.
- Create `web_workbench/src/main.tsx`: React root.
- Create `web_workbench/src/App.tsx`: Home/Workbench view shell and route-like state.
- Create `web_workbench/src/lib/api.ts`: typed API client.
- Create `web_workbench/src/lib/commands.ts`: command metadata used by palette/composer.
- Create `web_workbench/src/lib/commands.test.ts`: frontend metadata coverage.
- Create `web_workbench/src/components/HeroSphere.tsx`: Canvas 2D sphere animation inspired by the observed Home behavior, implemented independently.
- Create `web_workbench/src/components/HomePage.tsx`: workflow capability sections and completed project showcase.
- Create `web_workbench/src/components/WorkbenchShell.tsx`: operational shell with sidebar, status header, timeline, composer, and inspector region.
- Create `web_workbench/src/components/InspectorPanel.tsx`: jobs/artifacts/gates/logs/model/projects/revisions/status display panels.
- Create `web_workbench/src/styles.css`: product-grade visual system with neutral workspace palette, warm red accent, compact controls, responsive sizing, and reduced-motion handling.

## Command Coverage Contract

The Web Workbench must expose all current TUI command names, even when a command initially opens an inspector panel rather than executing a long-running operation:

```text
run, approve, check, open, report, demo, help, history, jobs, job, artifacts,
inspect, status, mode, resume, retry, revise, revisions, artifact, build,
chat, confirm, credibility, exit, gates, logs, memory, model, options,
project, projects, accept-revision, ask-more, reject-revision, reject,
revision, simulate, visual-approve, visual-reject, workbench, step
```

Commands map to `RadAgentAppService` directly. Do not call `agent_core.repl.RadAgentREPL` from Web code.

## Task 1: Web API Command Adapter

**Files:**
- Create: `tests/unit/test_web_workbench_api.py`
- Create: `agent_core/web/__init__.py`
- Create: `agent_core/web/api.py`

- [ ] **Step 1: Write the failing backend tests**

```python
import pytest

from agent_core.app.schemas import JobStatus, RadAgentEvent
from agent_core.web.api import build_command_catalog, dispatch_web_command


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def get_status(self) -> JobStatus:
        self.calls.append(("get_status", None))
        return JobStatus(job_id="job-1", status="paused", current_phase="g4_modeling")

    def list_jobs(self, *, include_all_projects: bool = False) -> list[dict[str, object]]:
        self.calls.append(("list_jobs", include_all_projects))
        return [{"job_id": "job-1", "status": "paused"}]

    def list_artifacts(self, job_id: str | None = None) -> list[object]:
        self.calls.append(("list_artifacts", job_id))
        return []

    def recent_events(self, limit: int = 80) -> list[RadAgentEvent]:
        self.calls.append(("recent_events", limit))
        return [RadAgentEvent(event_type="job_started", summary="started")]

    async def chat(self, message: str) -> dict[str, object]:
        self.calls.append(("chat", message))
        return {"message": f"reply:{message}", "commands": []}


def test_command_catalog_covers_tui_commands() -> None:
    names = {row["name"] for row in build_command_catalog()}

    assert {
        "run",
        "chat",
        "jobs",
        "artifacts",
        "confirm",
        "build",
        "simulate",
        "model",
        "projects",
        "revisions",
        "workbench",
        "visual-approve",
        "visual-reject",
    }.issubset(names)


@pytest.mark.asyncio
async def test_dispatch_panel_commands_return_json_safe_payloads() -> None:
    service = FakeService()

    status = await dispatch_web_command(service, "/status")
    jobs = await dispatch_web_command(service, "/jobs")
    logs = await dispatch_web_command(service, "/logs")

    assert status["ok"] is True
    assert status["command"] == "status"
    assert status["view"] == "status"
    assert status["data"]["job_id"] == "job-1"
    assert jobs["data"] == [{"job_id": "job-1", "status": "paused"}]
    assert logs["data"][0]["event_type"] == "job_started"
    assert service.calls == [
        ("get_status", None),
        ("list_jobs", True),
        ("recent_events", 80),
    ]


@pytest.mark.asyncio
async def test_dispatch_plain_text_uses_chat_service() -> None:
    service = FakeService()

    result = await dispatch_web_command(service, "explain the current run")

    assert result["ok"] is True
    assert result["command"] == "chat"
    assert result["view"] == "timeline"
    assert result["data"]["message"] == "reply:explain the current run"
    assert service.calls == [("chat", "explain the current run")]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest tests/unit/test_web_workbench_api.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'agent_core.web'`.

- [ ] **Step 3: Implement the minimal adapter**

Create `agent_core/web/__init__.py`:

```python
"""Web client support for RadAgent."""
```

Create `agent_core/web/api.py` with:

```python
from __future__ import annotations

import inspect
from collections.abc import Awaitable
from typing import Any

from pydantic import BaseModel

from agent_core.tui.commands import CommandParseError, command_suggestions, parse_command


PANEL_COMMANDS: dict[str, str] = {
    "check": "tools",
    "inspect": "tools",
    "status": "status",
    "jobs": "jobs",
    "artifacts": "artifacts",
    "gates": "gates",
    "logs": "logs",
    "model": "model",
    "projects": "projects",
    "revisions": "revisions",
    "confirm": "confirmation",
    "credibility": "credibility",
    "memory": "memory",
    "help": "help",
    "options": "options",
}


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


def build_command_catalog() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for suggestion in command_suggestions("", limit=80):
        head, _, description = suggestion.partition(" ")
        name = head.strip().removeprefix("/")
        if name and name not in seen:
            rows.append({"name": name, "description": " ".join(description.split())})
            seen.add(name)
    required = {
        "approve": "Approve active human confirmation",
        "build": "Build generated code",
        "chat": "Ask RadAgent directly",
        "confirm": "Open confirmation review",
        "credibility": "Open credibility report",
        "exit": "Exit the workbench",
        "gates": "Open gate results",
        "logs": "Open service event log",
        "memory": "Open workflow memory",
        "model": "View or update model settings",
        "options": "Open workbench options",
        "project": "Switch project",
        "projects": "List projects",
        "revision": "Open one revision",
        "simulate": "Run the generated simulator",
        "step": "Run the next pipeline phase",
        "visual-approve": "Approve G4 visual review",
        "visual-reject": "Reject G4 visual review",
    }
    for name, description in required.items():
        if name not in seen:
            rows.append({"name": name, "description": description})
    return sorted(rows, key=lambda row: row["name"])


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def dispatch_web_command(service: Any, text: str) -> dict[str, Any]:
    try:
        command = parse_command(text)
    except CommandParseError as exc:
        return {"ok": False, "error": str(exc), "view": "composer"}

    try:
        match command.name:
            case "chat":
                data = await _maybe_await(service.chat(command.args))
                view = "timeline"
            case "status":
                data = service.get_status()
                view = "status"
            case "jobs":
                data = service.list_jobs(include_all_projects=True)
                view = "jobs"
            case "artifacts":
                data = service.list_artifacts(None)
                view = "artifacts"
            case "logs":
                data = service.recent_events(80)
                view = "logs"
            case _ if command.name in PANEL_COMMANDS:
                data = {"panel": PANEL_COMMANDS[command.name], "args": command.args}
                view = PANEL_COMMANDS[command.name]
            case _:
                return {
                    "ok": False,
                    "command": command.name,
                    "error": f"Command /{command.name} is not wired in the web adapter yet.",
                    "view": "composer",
                }
    except Exception as exc:
        return {"ok": False, "command": command.name, "error": str(exc), "view": "timeline"}

    return {
        "ok": True,
        "command": command.name,
        "args": command.args,
        "view": view,
        "data": to_jsonable(data),
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest tests/unit/test_web_workbench_api.py -q
```

Expected: `3 passed`.

## Task 2: Local Web Server

**Files:**
- Create: `agent_core/web/server.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_web_workbench_api.py`

- [ ] **Step 1: Add HTTP handler tests**

Append a test that constructs the app handler with a fake service and confirms `GET /api/commands` and `POST /api/command` return JSON. Use `ThreadingHTTPServer` in a background thread with an ephemeral port.

- [ ] **Step 2: Run server tests to verify RED**

Run:

```bash
pytest tests/unit/test_web_workbench_api.py -q
```

Expected: fail because `agent_core.web.server` is missing.

- [ ] **Step 3: Implement server**

`agent_core/web/server.py` should:

- instantiate `RadAgentAppService(execution_mode="strict")`
- expose `GET /api/startup`, `GET /api/status`, `GET /api/events`, `GET /api/commands`
- expose `POST /api/command` with body `{"text": "/status"}`
- serve `web_workbench/dist/index.html` and static assets when the frontend is built
- return JSON errors with HTTP 400 for malformed input and HTTP 404 for unknown API paths

- [ ] **Step 4: Add launcher script**

Add to `pyproject.toml`:

```toml
radagent-web = "agent_core.web.server:main"
```

- [ ] **Step 5: Run backend verification**

Run:

```bash
pytest tests/unit/test_web_workbench_api.py -q
python -m agent_core.web.server --help
```

Expected: tests pass and help text shows host/port/static-root options.

## Task 3: Vite React Workbench Skeleton

**Files:**
- Create: `web_workbench/package.json`
- Create: `web_workbench/index.html`
- Create: `web_workbench/tsconfig.json`
- Create: `web_workbench/tsconfig.node.json`
- Create: `web_workbench/vite.config.ts`
- Create: `web_workbench/src/main.tsx`
- Create: `web_workbench/src/App.tsx`
- Create: `web_workbench/src/lib/api.ts`
- Create: `web_workbench/src/lib/commands.ts`
- Create: `web_workbench/src/lib/commands.test.ts`
- Create: `web_workbench/src/styles.css`

- [ ] **Step 1: Write frontend metadata test**

Create `web_workbench/src/lib/commands.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { coreCommandNames, isCoreCommand } from './commands'

describe('workbench command metadata', () => {
  it('covers the current TUI command surface', () => {
    expect(coreCommandNames).toEqual(
      expect.arrayContaining([
        'run',
        'chat',
        'jobs',
        'artifacts',
        'confirm',
        'build',
        'simulate',
        'model',
        'projects',
        'revisions',
        'workbench',
        'visual-approve',
        'visual-reject',
      ]),
    )
  })

  it('recognizes slash-command names without accepting arbitrary strings', () => {
    expect(isCoreCommand('/status')).toBe(true)
    expect(isCoreCommand('status')).toBe(true)
    expect(isCoreCommand('/unknown')).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cd web_workbench && npm test -- --run
```

Expected: fail because the frontend package and command module do not exist.

- [ ] **Step 3: Create Vite package and command metadata**

Use dependencies verified on 2026-06-13:

```json
{
  "name": "radagent-web-workbench",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 127.0.0.1",
    "test": "vitest"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "vite": "^8.0.16",
    "typescript": "^5.8.0",
    "react": "^19.2.7",
    "react-dom": "^19.2.7",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "vitest": "^2.1.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0"
  }
}
```

Create `web_workbench/src/lib/commands.ts` with the complete command-name array listed in the Command Coverage Contract and an `isCoreCommand(value: string): boolean` helper.

- [ ] **Step 4: Create the minimal SPA**

`App.tsx` should render two views: `home` and `workbench`. Use buttons to switch views and call `fetchCommandCatalog()` from `api.ts` on Workbench mount.

- [ ] **Step 5: Run frontend verification**

Run:

```bash
cd web_workbench && npm install && npm test -- --run && npm run build
```

Expected: Vitest passes and Vite emits `dist/`.

## Task 4: Home Page And Particle Sphere

**Files:**
- Create: `web_workbench/src/components/HeroSphere.tsx`
- Create: `web_workbench/src/components/HomePage.tsx`
- Modify: `web_workbench/src/App.tsx`
- Modify: `web_workbench/src/styles.css`

- [ ] **Step 1: Add interaction-safe animation behavior**

`HeroSphere.tsx` should:

- use two `<canvas>` layers inside one hero visual region
- generate particles with a Fibonacci sphere distribution
- split front/back rendering by z-depth
- add pointer tilt/repulsion
- reduce particle count on narrow screens
- skip animation loops when `prefers-reduced-motion: reduce` is active
- store the one-time intro state as `sessionStorage["radagent-home-intro-seen"]`

- [ ] **Step 2: Build Home content**

`HomePage.tsx` should include:

- first viewport with product name, concise value proposition, primary action entering Workbench, secondary action for project examples
- workflow capability band: intent capture, physics modeling, code generation, gates, build/simulation, artifacts/revisions
- completed project section with compact project cards using concrete RadAgent-style outcomes
- no marketing-only landing page that blocks access to the usable Workbench

- [ ] **Step 3: Verify visual behavior**

Run:

```bash
cd web_workbench && npm run build
```

Then start the dev server and use a browser smoke check at desktop and mobile widths. The canvas must be nonblank, the Home CTA must enter Workbench, and no text should overflow controls.

## Task 5: Workbench Operational Shell

**Files:**
- Create: `web_workbench/src/components/WorkbenchShell.tsx`
- Create: `web_workbench/src/components/InspectorPanel.tsx`
- Modify: `web_workbench/src/App.tsx`
- Modify: `web_workbench/src/lib/api.ts`
- Modify: `web_workbench/src/styles.css`

- [ ] **Step 1: Implement the TUI-equivalent layout**

`WorkbenchShell.tsx` should render:

- left sidebar with command sections: Run, Jobs, Artifacts, Gates, Logs, Model, Projects, Revisions
- sticky status header with project, active job, phase, execution mode, and confirmation state
- primary timeline region for service events and command responses
- bottom composer with slash-command palette and send button
- right inspector region that switches between status, jobs, artifacts, gates, logs, model, projects, revisions, confirmation, and help

- [ ] **Step 2: Wire composer to backend command dispatch**

`api.ts` should expose:

```ts
export async function sendCommand(text: string): Promise<WebCommandResponse>
export async function fetchStatus(): Promise<JobStatus>
export async function fetchEvents(): Promise<RadAgentEvent[]>
export async function fetchCommandCatalog(): Promise<CommandCatalogEntry[]>
```

- [ ] **Step 3: Preserve command semantics**

Plain text must dispatch as chat. Slash commands must use the backend parser, so Web and TUI reject unknown commands the same way.

- [ ] **Step 4: Verify shell build**

Run:

```bash
cd web_workbench && npm test -- --run && npm run build
pytest tests/unit/test_web_workbench_api.py -q
```

Expected: frontend and backend checks pass.

## Task 6: Long-Running Operations And Inspector Panels

**Files:**
- Modify: `agent_core/web/api.py`
- Modify: `agent_core/web/server.py`
- Modify: `tests/unit/test_web_workbench_api.py`
- Modify: `web_workbench/src/components/InspectorPanel.tsx`
- Modify: `web_workbench/src/components/WorkbenchShell.tsx`

- [ ] **Step 1: Add dispatch coverage**

Add tests for `/run`, `/step`, `/resume <job_id>`, `/retry <job_id>`, `/build`, `/simulate 1000`, `/workbench 100`, `/project <slug>`, `/revise <request>`, `/accept-revision <id>`, `/reject-revision <id>`, `/visual-approve`, and `/visual-reject <reason>`.

- [ ] **Step 2: Implement command wiring**

Map commands to service methods:

```text
/run -> await service.start_job(args, run_mode=service.execution_mode, auto_continue=True)
/step -> await service.step()
/resume -> service.resume_job(args)
/retry -> service.resume_job(args), then await service.run_until_blocked()
/build -> await service.build_generated_code()
/simulate -> await service.run_simulation(events=count)
/workbench -> await service.prepare_visualization_workbench(events=count, launch=True)
/project -> service.set_current_project(args)
/revise -> service.create_revision(args)
/accept-revision -> await service.accept_revision(args)
/reject-revision -> service.reject_revision(revision_id, reason="")
/visual-approve -> service.record_visual_verdict(approved=True)
/visual-reject -> service.record_visual_verdict(approved=False, notes=args)
```

- [ ] **Step 3: Add polling event refresh**

Until SSE is introduced, Workbench should poll `/api/events?limit=80` every 2 seconds while the tab is visible and pause polling when hidden.

- [ ] **Step 4: Verify operation behavior with fake services**

Run:

```bash
pytest tests/unit/test_web_workbench_api.py -q
cd web_workbench && npm run build
```

Expected: command wiring tests pass and frontend builds.

## Task 7: Product Polish And Browser Verification

**Files:**
- Modify: `web_workbench/src/styles.css`
- Modify: `web_workbench/src/components/HomePage.tsx`
- Modify: `web_workbench/src/components/HeroSphere.tsx`
- Modify: `web_workbench/src/components/WorkbenchShell.tsx`
- Modify: `web_workbench/src/components/InspectorPanel.tsx`

- [ ] **Step 1: CSS audit**

The visual system must avoid one-note palettes. Use neutral canvas colors, black/ink text, warm red accent, green/amber status tones, and restrained borders. Do not use decorative gradient orbs.

- [ ] **Step 2: Responsive audit**

Check:

- desktop 1440x900
- laptop 1280x800
- tablet 900x1100
- mobile 390x844

Home text, Workbench sidebar, composer, inspector tabs, and cards must not overlap or overflow.

- [ ] **Step 3: Motion audit**

Set reduced motion in the browser and confirm the particle sphere renders a static high-quality state without a running animation loop.

- [ ] **Step 4: Final verification commands**

Run:

```bash
pytest tests/unit/test_web_workbench_api.py -q
cd web_workbench && npm test -- --run && npm run build
```

Expected: all verification commands exit 0.

## Self-Review

- Spec coverage: Home/Workbench cooperation is represented explicitly; the Web Workbench targets the full TUI command surface; `RadAgentAppService` is the only backend integration point; the Geant4 visual workbench/canvas is scoped as a later panel, not the main workbench.
- Placeholder scan: no task depends on unspecified UI magic. Each task names files, commands, expected verification, and concrete command mappings.
- Type consistency: backend response shape is consistently `{ ok, command, args, view, data | error }`; frontend API uses the same shape; command names match `agent_core.tui.commands`.
