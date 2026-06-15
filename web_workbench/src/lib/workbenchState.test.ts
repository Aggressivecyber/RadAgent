import { describe, expect, it } from 'vitest'
import {
  createInitialWorkbenchState,
  reduceInitialJobSelection,
  reduceCommandResponse,
  reduceDetailSelection,
  reduceEvents,
} from './workbenchState'

describe('workbench state reducer', () => {
  it('starts on the overview inspector', () => {
    const state = createInitialWorkbenchState()

    expect(state.activeInspector).toBe('overview')
    expect(state.timeline[0]).toMatchObject({
      title: '工作台已就绪',
      body: '命令、事件、审查面板状态已连接。',
    })
  })

  it('adds command responses to the timeline and switches inspector view', () => {
    const state = createInitialWorkbenchState()

    const next = reduceCommandResponse(state, {
      ok: true,
      command: 'status',
      args: '',
      view: 'status',
      data: { job_id: 'job-1', status: 'paused', current_phase: 'context' },
    })

    expect(next.activeInspector).toBe('status')
    expect(next.inspectorData.status).toEqual({
      job_id: 'job-1',
      status: 'paused',
      current_phase: 'context',
    })
    expect(next.timeline.at(-1)).toMatchObject({
      kind: 'command',
      title: '查看状态',
      status: 'success',
      meta: 'status',
      details: { job_id: 'job-1', status: 'paused', current_phase: 'context' },
    })
  })

  it('marks only chat commands as Copilot history rows', () => {
    const state = createInitialWorkbenchState()

    const next = reduceCommandResponse(state, {
      ok: true,
      command: 'chat',
      args: '当前状态',
      view: 'timeline',
      data: { message: '当前正在 g4_codegen 阶段。' },
    })

    expect(next.timeline.at(-1)).toMatchObject({
      kind: 'command',
      title: '对话',
      meta: 'chat',
      body: '当前正在 g4_codegen 阶段。',
    })
  })

  it('keeps command errors visible without changing the active inspector', () => {
    const state = { ...createInitialWorkbenchState(), activeInspector: 'jobs' }

    const next = reduceCommandResponse(state, {
      ok: false,
      command: 'unknown',
      view: 'composer',
      error: 'Unknown command',
    })

    expect(next.activeInspector).toBe('jobs')
    expect(next.timeline.at(-1)).toMatchObject({
      kind: 'command',
      title: 'unknown',
      status: 'error',
      body: 'Unknown command',
    })
  })

  it('merges service events without duplicating existing rows', () => {
    const state = createInitialWorkbenchState()

    const first = reduceEvents(state, [
      {
        event_type: 'job_started',
        status: 'running',
        summary: 'job-1',
        phase: 'prepare_workspace',
        job_id: 'job-1',
        run_id: 'run-1',
        payload: { workspace: '/tmp/radagent', phase_idx: 0 },
        created_at: '2026-06-13T00:00:00Z',
      },
    ])
    const second = reduceEvents(first, [
      {
        event_type: 'job_started',
        status: 'running',
        summary: 'job-1',
        phase: 'prepare_workspace',
        job_id: 'job-1',
        run_id: 'run-1',
        payload: { workspace: '/tmp/radagent', phase_idx: 0 },
        created_at: '2026-06-13T00:00:00Z',
      },
    ])

    expect(first.timeline).toHaveLength(2)
    expect(second.timeline).toHaveLength(2)
    expect(first.timeline.at(-1)).toMatchObject({
      kind: 'event',
      details: {
        workspace: '/tmp/radagent',
        phase_idx: 0,
      },
    })
  })

  it('stores selected detail previews by inspector view', () => {
    const state = createInitialWorkbenchState()

    const next = reduceDetailSelection(state, 'artifact', {
      path: '/tmp/report.md',
      exists: true,
      kind: 'text',
      text: 'artifact body',
    })

    expect(next.activeInspector).toBe('artifact')
    expect(next.inspectorData.artifact).toEqual({
      path: '/tmp/report.md',
      exists: true,
      kind: 'text',
      text: 'artifact body',
    })
    expect(next.timeline.at(-1)).toMatchObject({
      kind: 'system',
      title: 'Selected artifact',
      status: 'info',
    })
  })

  it('opens an externally selected home project as a job detail', () => {
    const state = createInitialWorkbenchState()

    const next = reduceInitialJobSelection(state, {
      job_id: 'job-123',
      user_query: 'HPGe detector response workflow',
      status: 'completed',
    })

    expect(next.activeInspector).toBe('job')
    expect(next.inspectorData.job).toMatchObject({
      job_id: 'job-123',
      user_query: 'HPGe detector response workflow',
    })
    expect(next.timeline.at(-1)).toMatchObject({
      kind: 'system',
      title: 'Opened project job',
      status: 'info',
      meta: 'job',
    })
  })
})
