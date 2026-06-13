import { describe, expect, it } from 'vitest'
import { createOverviewPanel } from './overviewPanel'
import type { CommandCatalogEntry, JobStatus, RadAgentEvent } from './api'

const commands: CommandCatalogEntry[] = [
  {
    name: 'run',
    description: 'Start workflow',
    tip: 'Start a real RadAgent workflow from a simulation request.',
    module: 'workflow/start_job',
    connection: 'service',
    visible: true,
  },
  {
    name: 'confirm',
    description: 'Open confirmation review',
    tip: 'Open the active confirmation review before approving or rejecting.',
    module: 'human_confirmation',
    connection: 'service',
    visible: true,
  },
  {
    name: 'build',
    description: 'Build generated code',
    tip: 'Compile generated Geant4 code for the active job.',
    module: 'codegen/build',
    connection: 'service',
    visible: true,
  },
]

describe('overview panel presentation', () => {
  it('summarizes active workflow status and promotes confirmation when needed', () => {
    const status: JobStatus = {
      job_id: 'job-1',
      user_query: 'Build a silicon slab detector',
      status: 'paused',
      current_phase: 'validation',
      current_phase_idx: 4,
      completed_phases: ['prepare_workspace', 'context', 'g4_modeling'],
      execution_mode: 'strict',
      run_mode: 'strict',
      workspace_root: '/workspace',
      job_workspace: '/workspace/job-1',
      needs_confirmation: true,
      key_statuses: {},
      state: { project_slug: 'detectors' },
    }
    const events: RadAgentEvent[] = [
      {
        event_type: 'gate_blocked',
        status: 'warning',
        summary: 'Needs human confirmation',
        phase: 'validation',
        job_id: 'job-1',
        run_id: 'run-1',
        payload: {},
        created_at: '2026-06-14T08:00:00Z',
      },
    ]

    const panel = createOverviewPanel({ status, events, commands })

    expect(panel.metrics).toEqual([
      { label: '状态 State', value: 'paused' },
      { label: '阶段 Phase', value: 'validation' },
      { label: '已完成 Completed', value: '3 phases' },
      { label: '模式 Mode', value: 'strict' },
    ])
    expect(panel.alerts[0]).toMatchObject({
      status: 'warning',
      title: '需要确认',
    })
    expect(panel.actions[0]).toMatchObject({
      label: '处理确认',
      labelEn: 'Review confirmation',
      command: '/confirm',
      tone: 'primary',
      mode: 'execute',
    })
    expect(panel.recentEvents[0]).toMatchObject({
      title: 'gate blocked',
      status: 'warning',
      detail: 'Needs human confirmation',
    })
  })

  it('offers a run action when no job is active', () => {
    const panel = createOverviewPanel({ status: null, events: [], commands })

    expect(panel.title).toBe('暂无活动作业')
    expect(panel.metrics[0]).toEqual({ label: '状态 State', value: 'idle' })
    expect(panel.actions[0]).toMatchObject({
      label: '开始工作流',
      labelEn: 'Start workflow',
      command: '/run',
      tone: 'primary',
      mode: 'compose',
    })
  })
})
