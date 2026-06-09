# RadAgent Frontend Service Layer

This branch introduces a UI-neutral application layer for terminal, Qt, web,
or API frontends.

## Entry Point

```python
from agent_core.app import RadAgentAppService

service = RadAgentAppService(execution_mode="strict")
```

The service owns one interactive session:

- current job state
- completed pipeline phases
- chat agent lifecycle
- project/job/artifact storage access
- structured frontend events

It has no Rich, prompt-toolkit, Qt, or web framework dependency.

## Core Methods

```python
await service.classify_intent(text)
await service.chat(message)

await service.start_job(query, run_mode="strict", auto_continue=True)
await service.step()
await service.run_phase("context")
await service.run_until_blocked()
await service.submit_confirmation(response)

service.get_status()
service.resume_job(job_id)
service.list_jobs()
service.list_projects()
service.create_project(name)
service.set_current_project(slug_or_id)

service.list_artifacts(job_id)
service.read_artifact(path)
service.get_model_ir(job_id)
service.get_gate_results(job_id)

await service.build_generated_code()
await service.run_simulation(events=1000)
```

## Event Stream

Qt or TUI code can subscribe to structured events:

```python
async for event in service.subscribe_events():
    ...
```

Important event types:

- `job_started`
- `phase_started`
- `phase_finished`
- `phase_failed`
- `human_confirmation_required`
- `human_confirmation_submitted`
- `chat_started`
- `chat_finished`
- `build_started`
- `build_finished`
- `simulation_started`
- `simulation_finished`

Each event includes:

- `event_type`
- `status`
- `summary`
- `phase`
- `job_id`
- `run_id`
- `payload`
- `created_at`

## Frontend Mapping

Recommended Qt panels:

- left: projects/jobs
- center: chat and job timeline from events
- right: current status, phases, gates, artifacts
- bottom: command/input bar
- modal: human confirmation review

Avoid calling `agent_core.repl.RadAgentREPL` from Qt. Use
`RadAgentAppService` and render its models/events.
