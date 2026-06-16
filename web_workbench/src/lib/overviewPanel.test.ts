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
      key_statuses: {
        confirmation_status: 'pending',
      },
      state: {
        project_slug: 'detectors',
        confirmation_status: 'pending',
        human_confirmation_required: true,
      },
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
      { label: '状态', value: '暂停审查' },
      { label: '阶段', value: '验证门禁' },
      { label: '已完成', value: '3 个阶段' },
      { label: '模式', value: '严格模式' },
    ])
    expect(panel.alerts[0]).toMatchObject({
      status: 'warning',
      title: '需要人工确认',
    })
    expect(panel.actions[0]).toMatchObject({
      label: '查看确认项',
      labelEn: 'Review',
      command: '/confirm job-1',
      tone: 'primary',
      mode: 'execute',
    })
    expect(panel.recentEvents[0]).toMatchObject({
      title: 'gate blocked',
      status: 'warning',
      detail: 'Needs human confirmation',
      meta: '验证门禁',
    })
  })

  it('promotes visual review separately from ordinary confirmation', () => {
    const status: JobStatus = {
      job_id: 'job-visual',
      user_query: 'Build HPGe visual review workflow',
      status: 'paused',
      current_phase: 'gate',
      current_phase_idx: 7,
      completed_phases: [
        'prepare_workspace',
        'context',
        'task_planning',
        'g4_modeling',
        'human_confirmation',
        'g4_codegen',
        'patch',
      ],
      execution_mode: 'strict',
      run_mode: 'strict',
      workspace_root: '/workspace',
      job_workspace: '/workspace/job-visual',
      needs_confirmation: true,
      key_statuses: {
        confirmation_status: 'approved',
        validation_status: 'blocked',
      },
      state: {
        confirmation_status: 'approved',
        human_confirmation_required: false,
        failed_gates: [{ gate_id: 21, name: 'G4 Visual Review', status: 'blocked' }],
      },
    }

    const panel = createOverviewPanel({ status, events: [], commands })

    expect(panel.alerts).toEqual([])
    expect(panel.actions.map((action) => action.command)).not.toContain('/workbench 100')
    expect(panel.actions.map((action) => action.command)).not.toContain('/visual-approve')
    expect(panel.actions.map((action) => action.command)).not.toContain('/confirm')
  })

  it('offers a run action when no job is active', () => {
    const panel = createOverviewPanel({ status: null, events: [], commands })

    expect(panel.title).toBe('暂无活动作业')
    expect(panel.subtitle).toBe('从首页选择示例，或在工作台输入一个新的辐照防护仿真任务。')
    expect(panel.metrics[0]).toEqual({ label: '状态', value: '待命' })
    expect(panel.actions[0]).toMatchObject({
      label: '开始工作流',
      labelEn: 'Start',
      command: '/run',
      tone: 'primary',
      mode: 'compose',
    })
  })

  it('does not expose generic continue while repair continuation approval is pending', () => {
    const status: JobStatus = {
      job_id: 'job-repair',
      user_query: 'Build Bragg benchmark',
      status: 'paused',
      current_phase: 'g4_codegen',
      current_phase_idx: 5,
      completed_phases: ['prepare_workspace', 'context', 'task_planning', 'g4_modeling', 'human_confirmation'],
      execution_mode: 'strict',
      run_mode: 'strict',
      workspace_root: '/workspace',
      job_workspace: '/workspace/job-repair',
      needs_confirmation: true,
      key_statuses: {
        g4_codegen_status: 'needs_user_input',
        repair_continuation_status: 'pending',
      },
      state: {
        repair_continuation_status: 'pending',
        repair_continuation_request: {
          status: 'pending',
          increment_turns: 12,
          requested_total_turns: 60,
        },
      },
    }

    const panel = createOverviewPanel({ status, events: [], commands })

    expect(panel.alerts[0]).toMatchObject({
      title: '需要批准继续修复',
    })
    expect(panel.actions[0]).toMatchObject({
      label: '批准追加 12 轮',
      labelEn: 'Approve repair',
      command: '/confirm approve',
      tone: 'primary',
    })
    expect(panel.actions.map((action) => action.command)).not.toContain('/step')
    expect(panel.actions.map((action) => action.label)).not.toContain('继续下一步')
  })

  it('does not use continue step as the default action for ordinary active jobs', () => {
    const status: JobStatus = {
      job_id: 'job-running',
      user_query: 'Build detector',
      status: 'running',
      current_phase: 'g4_codegen',
      current_phase_idx: 5,
      completed_phases: ['prepare_workspace', 'context'],
      execution_mode: 'strict',
      run_mode: 'strict',
      workspace_root: '/workspace',
      job_workspace: '/workspace/job-running',
      needs_confirmation: false,
      key_statuses: {},
      state: {},
    }

    const panel = createOverviewPanel({ status, events: [], commands })

    expect(panel.actions.map((action) => action.command)).toEqual(['/build', '/simulate', '/artifacts'])
    expect(panel.actions.map((action) => action.label)).not.toContain('继续下一步')
  })
})
