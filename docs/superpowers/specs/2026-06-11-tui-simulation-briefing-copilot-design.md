# TUI Simulation Briefing Copilot Design

## Goal

Upgrade the RadAgent TUI copilot so every natural-language simulation request enters a mandatory briefing loop before the pipeline starts. The briefing copilot uses the MAX model to ask comprehensive questions, provide recommendations, produce a structured simulation plan, and request human approval before any `start_job` call.

## Requirements

- Natural-language simulation requests must not directly start a job.
- Simulation requests must enter a `briefing` state even when the request appears complete.
- The first briefing turn and later briefing refinement turns must use `ModelTier.MAX`.
- Briefing output must be structured JSON, not free-form chat only.
- Briefing output must cover downstream needs: objective, simulation scope, geometry, materials, source, physics, scoring, run plan, codegen constraints, missing critical fields, assumptions, risks, and final query.
- A job can start only after a human approves the structured start request.
- If the human rejects or edits the proposal, the session returns to briefing with the feedback included.
- If the MAX briefing call fails, the TUI must not silently downgrade to a weaker model and start the job.
- Once approved, the briefing summary and final query must be persisted into job state so later copilot turns can see the plan through workflow context.
- Slash commands such as `/run` can remain as expert shortcuts, but plain natural-language simulation requests must use briefing.

## Architecture

Add a pure-Python TUI controller between Textual and `RadAgentAppService`.

- `agent_core.tui.controller` owns input routing, briefing state, pending human approval, and operation selection.
- `agent_core.chat.briefing` owns the MAX-model briefing call and schema validation.
- `RadAgentAppService` exposes briefing methods and accepts approved briefing context when starting a job.
- Textual `app.py` delegates composer input to the controller, renders returned rows/panels, and runs controller operations in workers.

`RadAgentAppService` remains the only boundary for real workflow execution. The briefing copilot may propose a `start_job` action, but the controller executes it only after explicit human approval.

## Data Flow

1. User enters plain text.
2. Controller calls `service.classify_intent(text)`.
3. If intent is `chat`, controller returns an async `service.chat(text)` operation.
4. If intent is `simulation_work`, controller starts a briefing session and calls `service.brief_simulation(...)`.
5. The MAX briefing result is shown as a pending proposal.
6. User says `确定`, `批准`, or equivalent.
7. Controller calls `service.start_job(final_query, briefing_context=...)`.
8. Service writes briefing context into state before the first phase persists state.
9. Later `service.chat()` calls include briefing memory through `get_workflow_context()`.

## Briefing Output

The planner returns:

- `status`: `needs_input` or `ready_for_approval`
- `understanding`: concise summary of the user's intent
- `questions`: prioritized questions for the user
- `recommendations`: concrete expert recommendations
- `draft_plan`: structured simulation plan
- `missing_critical_fields`: required details that are absent
- `assumptions`: explicit assumptions
- `risks`: risks and expected impact
- `final_query`: full downstream query for `start_job`
- `approval_request`: human-readable approval summary and `requires_human_approval`

`ready_for_approval` can occur on the first turn for complete requests. Human approval is still required.

## Testing

- Model registry maps `SIMULATION_BRIEFING` to MAX with thinking enabled.
- Briefing planner calls gateway with `tier=ModelTier.MAX` and `response_format="json"`.
- Controller enters briefing for natural-language simulation intent.
- Controller does not start jobs until the user approves.
- Rejection or modification feedback continues briefing instead of starting.
- Approval starts a job with `final_query`.
- Workflow context includes approved briefing summary after job start.
