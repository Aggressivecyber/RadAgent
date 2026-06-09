# RadAgent

RadAgent is an agentic radiation-simulation coding system for turning natural
language requirements into reviewable Geant4 projects. It combines a LangGraph
pipeline, retrieval context, model planning, human confirmation, module-level
C++ generation, validation gates, artifact collection, and persistent workspace
metadata.

The current implementation is focused on Geant4 detector/model generation.
TCAD and SPICE assets exist in the repository as knowledge-base and benchmark
material, but they are not the primary production pipeline yet.

## What It Does

RadAgent can:

- classify user intent and route simulation requests through a structured pipeline;
- retrieve Geant4 context from local RAG sources and optional web context;
- build a Geant4 Model IR with geometry, materials, sources, physics, sensitive
  detectors, scoring, and output contracts;
- pause for human confirmation when generated assumptions need approval;
- generate a Geant4 C++ project through independent module agents;
- validate generated code with module gates, cross-file integration checks,
  build/smoke/data-contract gates, and report generation;
- persist jobs, projects, resume snapshots, events, artifacts, and chat context
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
/chat <message>       ask a contextual chat question
```

### Application Service Layer

`agent_core.app.service.RadAgentAppService` is a UI-neutral facade for desktop,
web, or API frontends. It owns session state, emits structured events, and
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
      03_modeling/
      04_human_confirmation/
      05_model_ir/
      06_codegen/
      07_patch/
      08_gate_validation/
      09_artifacts/
      10_report/
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
- chat sessions/messages and tool-call records.

Large outputs remain as files. The database is the control plane, not a blob
store.

## Architecture

Key packages:

```text
agent_core/
  app/                 UI-neutral service layer and Pydantic response schemas
  chat/                conversational assistant with RAG/web/job context
  context/             RAG and web-context retrieval nodes
  g4_modeling/         Model IR schemas, modeling nodes, validators, codegen helpers
  g4_codegen/          module agents, module gates, repair loop, integration checks
  gates/               validation gate runners and schemas
  graph/               LangGraph main graph, routes, subgraph builders, main state
  human_confirmation/  confirmation request/response handling
  intent/              intent schemas, fallback rules, router, response routing
  models/              model gateway, tiers, usage, tool-call logging
  observability/       job-scoped events and failure bundles
  patching/            patch contract review and application
  reports/             final report nodes and schemas
  response/            non-pipeline response handling
  storage/             SQLite workspace metadata repository
  tools/               shell, patch, web search, Geant4 runner wrappers
  workspace/           job directory and stage path management
```

The Geant4 codegen layer is module-oriented. Independent agents generate and
validate modules such as geometry, placement, material, physics, source,
sensitive detector, scoring, action initialization, output manager, and
`main`/CMake. Integration gates then check cross-file contracts before outputs
are persisted.

## Validation

Validation is layered:

- schema checks for task specs, Model IR, patch payloads, and gate results;
- modeling gates for completeness, no unapproved simplification, geometry
  interfaces, overlap policy, evidence traceability, module boundaries, and
  magic-number policy;
- module-specific hard gates and LLM review gates for generated Geant4 code;
- static semantic scans and cross-file hard/LLM integration gates;
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
job outputs are produced under `simulation_workspace/jobs/<job_id>/`.

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

Install:

```bash
python -m pip install -e ".[dev]"
```

Common checks:

```bash
python -m pytest -q tests/unit/test_storage_repository.py tests/unit/test_repl.py
python -m pytest -q tests/unit/
python -m ruff check agent_core tests
python -m compileall -q agent_core
```

Some integration and real-module tests require external tools such as Geant4,
TCAD Sentaurus, ngspice, or configured model providers. Those tests are marked
in `pyproject.toml` and should not be treated as ordinary local smoke tests.

## Environment Notes

Typical configuration comes from `.env` and `agent_core/config/environment.py`.
Important values include:

- `RADAGENT_WORKSPACE_ROOT`
- model provider/API credentials used by `agent_core.models`
- RAG/web-search availability settings
- external tool paths for Geant4/TCAD/SPICE integration tests

The project is designed so the main graph and service layer can run in strict
mode with persisted state, while expensive external validation is guarded by
mode and environment availability.

## Current Scope

Production focus:

- Geant4 detector/model planning;
- module-based Geant4 C++ generation;
- validation and repair loops;
- persisted local project/job management;
- CLI, REPL, and service-layer consumption.

Reserved or experimental:

- full TCAD and SPICE pipeline orchestration;
- multi-user server deployment;
- remote artifact storage;
- GUI/frontend packaging beyond the service-layer API.

## License

MIT
