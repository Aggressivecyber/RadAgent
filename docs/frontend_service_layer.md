# RadAgent Frontend Service Layer

This branch introduces a UI-neutral application layer for terminal, web, or
API frontends.

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

It has no Rich, prompt-toolkit, Textual, or web framework dependency.

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

service.get_model_config()
service.update_model_config({
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "<api-key>",
    "lite_model": "mimo-v2.5",
    "pro_model": "mimo-v2.5-pro",
    "max_model": "mimo-v2.5-pro",
})

await service.build_generated_code()
await service.run_simulation(events=1000)
```

`get_model_config()` is frontend-safe and never returns the API key value; it
only reports the configured env var name and whether a key is present.
`update_model_config()` writes the project `.env`, updates the current process,
and refreshes the model gateway. MiMo Token Plan and other OpenAI-compatible
endpoints use the same fields: model name, base URL, and API key.

## Event Stream

TUI or web code can subscribe to structured events:

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
- `copilot_started`
- `copilot_finished`
- `build_started`
- `build_finished`
- `simulation_started`
- `simulation_finished`
- `model_config_updated`

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

Recommended terminal/web frontend regions:

- fixed header: project, job, phase, mode, and confirmation state
- primary region: chat and job timeline from events
- bottom region: command/input composer
- inspector overlay/drawer: jobs, artifacts, gates, model IR, logs, and status
- modal/overlay: human confirmation review

Avoid calling `agent_core.repl.RadAgentREPL` from new frontends. Use
`RadAgentAppService` and render its models/events.
