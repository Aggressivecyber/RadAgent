# RadAgent

RadAgent is an agentic radiation-simulation coding system for turning natural
language requirements into reviewable Geant4 projects. It combines a LangGraph
pipeline, retrieval context, model planning, human confirmation, module-level
C++ generation, validation gates, artifact collection, and persistent workspace
metadata.

The current implementation is focused on Geant4 detector/model generation.
Geant4 and TCAD knowledge-base assets exist in the repository. SPICE support is
reserved for external tooling and later pipeline work.

## What It Does

RadAgent can:

- classify user intent and route simulation requests through a structured pipeline;
- retrieve Geant4 context from local RAG sources and optional web context;
- build a Geant4 Model IR with geometry, materials, sources, physics, sensitive
  detectors, scoring, and output contracts;
- pause for human confirmation when generated assumptions need approval;
- generate a Geant4 C++ project through independent module agents;
- validate generated code with layer consistency checks, global integration,
  runtime execution auditing, physics review, build/smoke/data-contract gates,
  and report generation;
- persist jobs, projects, resume snapshots, events, artifacts, and copilot context
  in a workspace SQLite database;
- expose the same core operations through CLI, REPL, and a UI-neutral
  application service layer.

## Pipeline

The main graph is a scheduler. Domain work lives in subgraphs and service
modules, while the main state mostly stores paths and status fields.

```text
user request
  -> intent / response handling
  -> prepare_workspace
  -> context
  -> task_planning
  -> g4_modeling
  -> human_confirmation
  -> g4_codegen
  -> patch
  -> gate
  -> artifact
  -> report
```

The phase order is shared by the CLI/REPL and `RadAgentAppService`:

| Phase | Purpose |
| --- | --- |
| `prepare_workspace` | Create the job workspace and register it in metadata storage. |
| `context` | Retrieve and score RAG/web evidence. |
| `task_planning` | Convert user requirements into a task spec. |
| `g4_modeling` | Build and validate the Geant4 Model IR. |
| `human_confirmation` | Ask the user to approve or edit uncertain assumptions. |
| `g4_codegen` | Generate module-scoped Geant4 C++ and integrate it. |
| `patch` | Validate and apply the proposed patch/package. |
| `gate` | Run validation gates and classify failures. |
| `artifact` | Collect reviewable outputs. |
| `report` | Produce the final job report. |

## Interfaces

### One-Shot CLI

```bash
python -m agent_core.main "simulate a 10 MeV proton beam incident on a silicon detector"
python -m agent_core.main --job-id my_job --status
python -m agent_core.main --list-jobs
```

Execution mode can be selected with:

```bash
python -m agent_core.main --mode strict "..."
```

Supported modes are `strict`, `test`, `acceptance`, and `production`.

### Interactive REPL

```bash
python -m agent_core.main -i
```

Useful commands:

```text
/run <query>          start a new pipeline job
/step                 run the next phase
/status               show current phase and key statuses
/confirm              review and submit human confirmation
/model                inspect the current Model IR
/code                 list generated source files
/build                configure and build generated Geant4 code
/sim [events]         run the built simulation
/results              list simulation outputs
/gates                inspect gate results
/jobs                 list jobs in the current project
/resume <job_id>      restore the latest persisted job snapshot
/projects             list workspace projects
/project new <name>   create and switch to a project
/project use <slug>   switch projects
/chat <message>       ask the workflow-aware copilot
```

### Professional TUI Workstation

RadAgent also ships a Textual terminal workstation:

```bash
./start-radagent-tui.sh
./start-radagent-tui.sh --theme slate-workstation
./start-radagent-tui.sh --theme neon-lab
./start-radagent-tui.sh --theme minimal-terminal
```

The launcher creates `.venv` if needed, installs the TUI optional dependency,
and runs `python -m agent_core.tui` from that environment. Use
`./start-radagent-tui.sh --check` to verify the local TUI install.

The TUI uses a fixed workstation layout: global status bar, transcript timeline,
right-side Task/Context/Runtime/Workflow panel, bottom command composer, and
drawer-style inspectors. Useful commands and shortcuts:

```text
/run <query>          create and run a simulation task
/check                inspect Geant4 / TCAD / ngspice paths and status
/artifacts            browse logs, reports, plots, and output files
/open [name]          preview a matching artifact or output collection
/report               preview the active report artifact
/jobs                 list saved jobs
/job <job_id>         show job detail, output path, and resume/retry commands
/resume <job_id>      restore the latest persisted job snapshot
/retry <job_id>       resume a job and continue execution
/demo geant4          play a safe Geant4 demo workflow without relying on tools
/mode run             switch the composer into simulation-run input mode
/options              switch language/theme and context-window options

Ctrl+L input  Ctrl+P options  Ctrl+I inspect  Ctrl+T trace
Ctrl+O artifacts  Ctrl+R history  F1 help  Ctrl+C stop
```

The default `slate-workstation` theme follows a restrained research workstation
palette: dark gray panels, weak borders, semantic ready/warning/error colors,
and purple only for focused or brand accents.

### Application Service Layer

`agent_core.app.service.RadAgentAppService` is a UI-neutral facade for TUI, web,
or API frontends. It owns session state, emits structured events, and
provides operations for jobs, phases, artifacts, build, and simulation without
depending on Rich or prompt-toolkit.

Minimal example:

```python
import asyncio
from agent_core.app.service import RadAgentAppService


async def main() -> None:
    service = RadAgentAppService(execution_mode="strict")
    status = await service.start_job(
        "simulate a proton beam through an aluminum shield and silicon detector",
        auto_continue=True,
    )
    print(status.job_id, status.status, status.current_phase)


asyncio.run(main())
```

## Workspace And Persistence

By default, RadAgent writes runtime data under:

```text
simulation_workspace/
  radagent.db
  jobs/
    <job_id>/
      00_input/
      01_context/
      02_task_plan/
      03_model_ir/
      04_human_confirmation/
      05_codegen/
      06_patch/
        geant4_project/
      07_gate_validation/
      08_artifacts/
      09_report/
      logs/
```

Set a different workspace root with:

```bash
export RADAGENT_WORKSPACE_ROOT=/path/to/workspace
```

`radagent.db` is a SQLite metadata database. It stores:

- projects and current-project selection;
- jobs and their lifecycle status;
- phase snapshots for `/resume`;
- artifact indexes pointing to files on disk;
- structured events;
- copilot sessions/messages and tool-call records.

Large outputs remain as files. The database is the control plane, not a blob
store.

## Architecture

Key packages:

```text
agent_core/
  agent_loop/          generic native tool-calling agent loop (build-fix cycles)
  agent_tools/         reusable agent tool registry, selection, and execution helpers
  app/                 UI-neutral service layer and Pydantic response schemas
  artifacts/           artifact collection graph, manifests, and schemas
  chat/                workflow-aware copilot with RAG/web/job context
  config/              environment, workspace, model endpoint, and runtime settings
  context/             RAG and web-context retrieval nodes
  dev_tools/           sandboxed file/shell/build tools for agentic codegen loops
  g4_codegen/          coarse module agents, integration, runtime audit, physics review
  g4_modeling/         Model IR schemas, modeling nodes, validators, and reports
  gates/               validation gate runners and schemas
  graph/               LangGraph main graph, routes, subgraph builders, main state
  human_confirmation/  confirmation request/response handling
  intent/              intent schemas, fallback rules, router, response routing
  models/              model gateway, tier profiles, mock model, tool-call logging
  observability/       job-scoped events and failure bundles
  patching/            patch contract review and application
  planning/            task-spec planning graph and schemas
  policies/            packaged YAML runtime policies
  pipeline.py          canonical pipeline phase order shared by CLI, REPL, app, and storage
  reports/             final report nodes and schemas
  revision/            isolated revision sandboxes and acceptance checks
  response/            non-pipeline response handling
  schemas/             shared cross-module schemas
  space_radiation/     AP8/AE8 trapped-radiation source packaging
  storage/             SQLite workspace metadata repository
  tools/               web search and Geant4 build/run wrappers
  tui/                 Textual terminal frontend
  validators/          shared file, patch, code, and schema validators
  visualization/       graph visualization helpers
  workflow/            copilot-visible workflow context and memory schemas
  workspace/           job directory and stage path management
```

Runtime flow:

```text
frontend/CLI/TUI
  -> app service or agent_core.main
  -> intent routing
  -> graph/main_graph
  -> context -> planning -> g4_modeling -> human_confirmation
  -> g4_codegen -> patching -> gates -> artifacts -> reports
  -> storage/workspace/observability
```

Module responsibilities and links:

| Module | Role | Upstream callers | Downstream dependencies |
| --- | --- | --- | --- |
| `agent_core.agent_tools` | Registers and executes reusable tools exposed to agent loops. | model gateway tool-call flows, future agents. | `space_radiation`, LangChain tool interfaces. |
| `agent_core.agent_loop` | Generic native tool-calling loop: model + dev toolkit + dispatch + feed-back until natural finish or budget. | `g4_codegen` agentic repair. | `dev_tools`, `models`. |
| `agent_core.app` | Stable facade for frontends, model settings, copilot, job/artifact/build/simulation/revision operations. | TUI, future web/API frontends. | `chat`, `config`, `graph`, `models`, `storage`, `tools`, `workspace`, `workflow`, `revision`. |
| `agent_core.chat` | Workflow-aware copilot with RAG, web search, and workspace/job context. | `app`, REPL, response nodes. | `context`, `models`, `storage`, `tools`, `workspace`. |
| `agent_core.config` | Environment, run-mode, external tool, concurrency, and workspace configuration. | Most runtime packages. | `models.schemas`, `workspace.paths`. |
| `agent_core.context` | RAG/web context retrieval and context decision graph. | main graph, chat, codegen context coordination. | `config`, `tools.web_search_tool`. |
| `agent_core.dev_tools` | Sandboxed read/edit/write/bash/build/smoke tools bound to a project workdir, for agentic codegen loops. | `agent_loop`, `g4_codegen` agentic repair. | `tools.geant4_runner`. |
| `agent_core.planning` | Converts user request and context into a scoped task spec. | main graph, graph viewer. | `config`. |
| `agent_core.g4_modeling` | Builds and validates structured Geant4 Model IR before code generation. | main graph, gates. | `config`, `models`. |
| `agent_core.human_confirmation` | Captures user approval/edits for uncertain model assumptions. | main graph, gates. | `config`. |
| `agent_core.g4_codegen` | Generates coarse Geant4 code modules, coordinates cross-module context, runs integration, runtime audit, and physics review. | main graph, gates, maintenance scripts. | `context`, `gates`, `models`, `observability`, `tools`, `knowledge_base.geant4`. |
| `agent_core.patching` | Validates and applies proposed file changes inside allowed workspace zones. | main graph, graph viewer. | `config`, `validators`. |
| `agent_core.gates` | Runs validation gates and classifies failures for retry routing. | main graph, app build/simulation helpers, Geant4 runner. | `g4_modeling`, `g4_codegen`, `human_confirmation`, `tools`, `validators`, `observability`. |
| `agent_core.artifacts` | Collects reviewable outputs, manifests, and final artifact indexes. | main graph. | `config`, workspace files. |
| `agent_core.reports` | Writes final human-readable job reports from state, gates, and artifacts. | main graph, graph viewer. | `config`. |
| `agent_core.revision` | Creates isolated revision sandboxes and checks whether candidates may be accepted back into a job. | app service, TUI. | `patching`, `workspace`. |
| `agent_core.response` | Handles non-pipeline responses and delegates copilot answers. | main graph. | `chat`. |
| `agent_core.graph` | Owns the LangGraph main graph, routing, state schema, and subgraph adapters. | CLI, REPL, app service, scripts. | all pipeline subgraphs above. |
| `agent_core.models` | Unified OpenAI-compatible model gateway, tier selection, MiMo thinking defaults, mock model, and model-call logs. | chat, intent, modeling, codegen, app config. | `config`, `observability`. |
| `agent_core.observability` | Writes job-scoped events, redacted artifacts, and failure bundles. | model gateway, codegen, gates. | `config`. |
| `agent_core.policies` | Ships static YAML policies, currently file-access zones used by validators. | package resources. | none. |
| `agent_core.schemas` | Shared schema objects used across validators and simulation contracts. | validators, pipeline state helpers. | none. |
| `agent_core.space_radiation` | Packages AP8/AE8 trapped-radiation environments into Geant4 source inputs. | planning, Geant4 source modeling. | `knowledge_base.space_radiation`. |
| `agent_core.storage` | SQLite control-plane repository for projects, jobs, snapshots, events, artifacts, and chat. | app, chat, CLI/REPL. | `workspace`. |
| `agent_core.tools` | External tool wrappers for web search, Geant4 build/run, and simulation contracts. | chat, context, gates, app. | `config`, `gates`. |
| `agent_core.validators` | Shared patch/file/code/schema validators used by patching and gates. | patching, gates. | `schemas`. |
| `agent_core.workspace` | Resolves workspace root, job directories, and stage paths. | app, chat, config, graph, REPL, storage. | filesystem only. |
| `agent_core.tui` | Textual terminal frontend entry point. | `radagent-tui` command, `python -m agent_core.tui`. | `app`. |
| `agent_core.visualization` | Static graph visualization helpers and CLI graph rendering support. | `scripts/view_graph.py`. | none. |
| `agent_core.workflow` | Builds copilot-visible workflow context, memory summaries, and evidence summaries. | app service, copilot, TUI. | `app.schemas`, `workspace`. |
| `knowledge_base.geant4` | Geant4 RAG data prep, indexing, MCP helper, query rewrite, and generator utilities. | codegen example lookup, manual maintenance entry points. | `knowledge_base.llm_client`. |
| `knowledge_base.tcad` | TCAD RAG data prep, indexing, MCP helper, query rewrite, generator utilities, and optional WeChat scraper. | manual maintenance entry points. | `knowledge_base.llm_client`. |
| `knowledge_base.llm_client` | Shared OpenAI-compatible helper for knowledge-base generation/query rewrite scripts. | Geant4 and TCAD KB scripts. | `agent_core.config`. |
| `scripts` | Operational helpers for running pipeline, viewing graphs, validating examples, inspecting logs, and regenerating tracked fixtures. | command line only. | public `agent_core` APIs. |

Top-level runtime modules:

| Module | Role | Used by |
| --- | --- | --- |
| `agent_core.main` | One-shot CLI entry point and status inspection helper around the main LangGraph pipeline. | `python -m agent_core.main`, `scripts/run_pipeline.py` pattern. |
| `agent_core.repl` | Rich/prompt-toolkit interactive shell for phase-by-phase pipeline control and job inspection. | `repl.sh`, local operators. |
| `agent_core.naming` | Model-assisted job title slug generation with deterministic fallback. | main graph job initialization. |

The Geant4 codegen layer is module-oriented. Coarse agents generate
`simulation_core`, `beam_physics`, and `runtime_app` file groups. Layer gates
check that each group produced usable files, a read-only context coordinator
summarizes upstream interfaces for later agents, and the global integration
agent is the only cross-module writer before output is persisted.

Dead-code policy:

- Runtime Python files under `agent_core`, `knowledge_base`, and `scripts` are
  checked by `tests/unit/test_architecture_invariants.py` for detached modules:
  a non-entry module must have an incoming local import edge.
- Package `__init__.py` files stay as lightweight public APIs and must not hide
  business logic.
- CLI/TUI/RAG maintenance scripts are valid entry points when they provide a
  `__main__` guard or console-script target.
- Runtime jobs, logs, caches, and knowledge-base generated data are not source
  modules and are ignored under `simulation_workspace/` or `knowledge_base/**/data/`.

The current codebase has no known orphan runtime module after this cleanup. The
graph and import invariants above are the regression guard for future changes.

## Validation

Validation is layered:

- schema checks for task specs, Model IR, patch payloads, and gate results;
- modeling gates for completeness, no unapproved simplification, geometry
  interfaces, overlap policy, evidence traceability, module boundaries, and
  magic-number policy;
- layer consistency gates for generated Geant4 module outputs;
- global integration repair from concrete compile/runtime observations;
- runtime execution auditing and LLM physics fidelity review;
- build, smoke-test, output-contract, benchmark, and physics-sanity gates.

Generated output is considered useful only when it is accompanied by structured
gate results and reviewable artifacts.

## Review Artifacts

Review artifacts are collected under `review_artifacts/` and job workspaces.
The repository includes a current sample under:

```text
review_artifacts/g4_complex_model/latest/
```

This directory is intended for code review and regression inspection. Runtime
job outputs are produced under `simulation_workspace/jobs/<job_id>/`. The
tracked sample is marked `validation_scope=fixture_model_review`: it preserves
current Model IR, gate, manifest, and human-confirmation formats, but skips
real runtime gates because it does not execute Geant4.

## Knowledge Bases

Local knowledge-base material lives under:

```text
knowledge_base/geant4/
knowledge_base/tcad/
```

These directories contain preprocessing, indexing, query rewriting, generator,
and MCP/RAG helper code. Build or refresh indexes only when the source material
or retrieval behavior changes.

## Development

Runtime install:

```bash
python -m pip install -e .
```

Development install:

```bash
python -m pip install -e ".[dev]"
```

TUI install:

```bash
python -m pip install -e ".[tui]"
```

TCAD WeChat article collection is an optional maintenance tool:

```bash
python -m pip install -e ".[wechat-scraper]"
```

For local development across all optional surfaces:

```bash
python -m pip install -e ".[dev,tui,wechat-scraper]"
```

Common checks:

```bash
python -m pytest -q tests/unit/test_storage_repository.py tests/unit/test_repl.py
python -m pytest -q tests/unit/
python -m ruff check agent_core tests scripts
python -m ruff check --select F,I knowledge_base
python -m compileall -q agent_core tests scripts knowledge_base
```

Some integration and real full-graph tests require external tools such as
Geant4, TCAD Sentaurus, ngspice, or a configured model API. Those tests are
marked in `pyproject.toml` and should not be treated as ordinary local smoke
tests.

## Environment Notes

Typical configuration comes from `.env` and `agent_core/config/environment.py`.
Important values include:

- `RADAGENT_WORKSPACE_ROOT`
- model API credentials used by `agent_core.models`
- RAG/web-search availability settings
- external tool paths for Geant4/TCAD/SPICE integration tests

Model access is configured through one OpenAI-compatible surface. Set the base
URL, API key, and tier model names in `.env`; MiMo Token Plan and other
OpenAI-compatible endpoints use the same fields:

```bash
RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
RADAGENT_API_KEY=<api-key>
RADAGENT_MODEL_LITE=mimo-v2.5
RADAGENT_MODEL_PRO=mimo-v2.5-pro
RADAGENT_MODEL_MAX=mimo-v2.5-pro
```

Frontend code should call `RadAgentAppService.get_model_config()` and
`RadAgentAppService.update_model_config(...)` instead of editing model globals
directly.

The project is designed so the main graph and service layer can run in strict
mode with persisted state, while expensive external validation is guarded by
mode and environment availability.

## Current Scope

Production focus:

- Geant4 detector/model planning;
- module-based Geant4 C++ generation;
- validation, runtime auditing, and global integration repair;
- persisted local project/job management;
- CLI, REPL, and service-layer consumption.

Reserved or experimental:

- full TCAD and SPICE pipeline orchestration;
- multi-user server deployment;
- remote artifact storage;
- GUI/frontend packaging beyond the service-layer API.

## License

MIT
