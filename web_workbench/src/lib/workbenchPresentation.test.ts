import { describe, expect, it } from 'vitest'
import type { JobStatus } from './api'
import type { TimelineRow } from './workbenchState'
import {
  createAgentCockpit,
  createPhaseTrack,
  createReviewCallout,
  createWorkbenchHero,
  createStatusPanelSummary,
  presentConfirmationStatus,
  presentTimelineRow,
} from './workbenchPresentation'

const activeStatus: JobStatus = {
  job_id: 'job-42',
  user_query: '150 MeV proton depth-dose benchmark',
  status: 'running',
  current_phase: 'g4_codegen',
  current_phase_idx: 6,
  completed_phases: ['prepare_workspace', 'context', 'task_planning', 'requirements_review'],
  execution_mode: 'strict',
  run_mode: 'local',
  workspace_root: '/tmp/radagent',
  job_workspace: '/tmp/radagent/job-42',
  needs_confirmation: false,
  key_statuses: { runtime_active: true },
  state: { project_slug: 'proton-depth-dose', runtime_active: true },
}

describe('workbench presentation', () => {
  it('summarizes the active Geant4 workflow as a Chinese-first hero', () => {
    expect(createWorkbenchHero(activeStatus)).toEqual({
      eyebrow: 'Proton Depth Dose',
      title: '150 MeV proton depth-dose benchmark',
      subtitle: '当前推进到 Geant4 工程生成，已完成 4/11 个阶段。',
      statusText: '运行中 · Geant4 工程生成',
      statusTone: 'running',
    })
  })

  it('shows resumable jobs as waiting when no runtime worker is active', () => {
    expect(
      createWorkbenchHero({
        ...activeStatus,
        key_statuses: { runtime_active: false },
        state: { ...activeStatus.state, runtime_active: false },
      }),
    ).toMatchObject({
      statusText: '待继续 · Geant4 工程生成',
      statusTone: 'paused',
    })
  })

  it('marks inactive running codegen jobs as waiting to continue in the cockpit', () => {
    const cockpit = createAgentCockpit({
      status: {
        ...activeStatus,
        key_statuses: { g4_codegen_status: 'running', runtime_active: false },
        state: { ...activeStatus.state, g4_codegen_status: 'running', runtime_active: false },
      },
      events: [],
      artifacts: [],
    })

    expect(cockpit.agent).toMatchObject({
      stateLabel: '待继续',
      phaseLabel: 'Geant4 工程生成',
    })
    expect(cockpit.runtimeActive).toBe(false)
    expect(cockpit.agent.statusChips).toEqual(
      expect.arrayContaining([{ label: 'Codegen', value: '待继续', tone: 'warning' }]),
    )
  })

  it('falls back to a ready state when no job is active', () => {
    expect(createWorkbenchHero(null)).toMatchObject({
      eyebrow: 'RadAgent',
      title: '等待仿真任务',
      statusText: '待命 · 准备工作区',
      statusTone: 'idle',
    })
  })

  it('formats raw project slugs and workspace paths for the hero eyebrow', () => {
    expect(
      createWorkbenchHero({
        ...activeStatus,
        state: { project_slug: 'simulation_workspace' },
      }).eyebrow,
    ).toBe('Simulation Workspace')
    expect(
      createWorkbenchHero({
        ...activeStatus,
        state: {},
        workspace_root: '/tmp/radagent/simulation_workspace',
      }).eyebrow,
    ).toBe('Simulation Workspace')
  })

  it('does not use a full generated prompt as the workbench H1', () => {
    const hero = createWorkbenchHero({
      ...activeStatus,
      user_query:
        '空天辐照防护仿真任务：基于 Geant4 建立可构建、可运行、可审查的工作流。 任务模板：器件总剂量。建立器件总剂量 TID 仿真，包含硅敏感体、屏蔽结构、能量沉积计分和剂量换算。 粒子源：AP8/AE8 轨道粒子。',
    })

    expect(hero.title).toBe('器件总剂量 · AP8/AE8 轨道粒子')
    expect(hero.title.length).toBeLessThan(32)
  })

  it('builds a full phase track from the canonical RadAgent pipeline', () => {
    const track = createPhaseTrack(activeStatus)

    expect(track.map((phase) => phase.id)).toEqual([
      'prepare_workspace',
      'context',
      'task_planning',
      'requirements_review',
      'g4_modeling',
      'human_confirmation',
      'g4_codegen',
      'patch',
      'gate',
      'artifact',
      'report',
    ])
    expect(track.find((phase) => phase.id === 'requirements_review')).toMatchObject({
      label: '参数核对',
      state: 'done',
    })
    expect(track.find((phase) => phase.id === 'g4_codegen')).toMatchObject({
      label: '工程生成',
      state: 'active',
    })
  })

  it('presents timeline rows as auditable agent evidence', () => {
    const row: TimelineRow = {
      id: 'event:1',
      kind: 'event',
      title: 'job_started',
      body: 'Workspace prepared',
      status: 'running',
      meta: 'prepare_workspace',
      details: { workspace: '/tmp/radagent/job-42' },
    }

    expect(presentTimelineRow(row)).toMatchObject({
      label: 'Agent 证据',
      title: 'job started',
      phase: '准备工作区',
      statusLabel: '运行中',
      expandable: true,
    })
  })

  it('localizes status panel metrics and canonical phase rows', () => {
    const summary = createStatusPanelSummary(activeStatus)

    expect(summary.metrics).toEqual([
      { label: '活动作业', value: 'job-42' },
      { label: '状态', value: '运行中' },
    ])
    expect(summary.phases.map((phase) => phase.label)).toEqual([
      '准备工作区',
      '上下文收集',
      '任务规划',
      '参数核对',
      'Geant4 建模',
      '人工确认',
      '工程生成',
      '修订补丁',
      '验证门禁',
      '产物归档',
      '报告交付',
    ])
    expect(summary.phases.find((phase) => phase.id === 'g4_codegen')).toMatchObject({
      state: 'active',
      marker: '当前',
    })
  })

  it('presents confirmation status without raw fallback labels', () => {
    expect(presentConfirmationStatus('pending')).toBe('等待审查')
    expect(presentConfirmationStatus('approved')).toBe('已批准')
    expect(presentConfirmationStatus(undefined)).toBe('未加载确认项')
  })

  it('ignores retired visual review gate 21 after model confirmation is approved', () => {
    const callout = createReviewCallout({
      ...activeStatus,
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
      needs_confirmation: true,
      key_statuses: {
        confirmation_status: 'approved',
        validation_status: 'blocked',
      },
      state: {
        confirmation_status: 'approved',
        human_confirmation_required: false,
        failed_gates: [
          {
            gate_id: 21,
            name: 'G4 Visual Review',
            status: 'blocked',
          },
        ],
      },
    })

    expect(callout).toBeNull()
  })

  it('does not show a human approval callout for failed modeling', () => {
    const callout = createReviewCallout({
      ...activeStatus,
      status: 'failed',
      current_phase: 'human_confirmation',
      current_phase_idx: 4,
      needs_confirmation: false,
      key_statuses: {
        g4_modeling_status: 'failed',
        termination_reason: 'g4_modeling status is failed',
      },
      state: {
        g4_modeling_status: 'failed',
        human_confirmation_required: true,
        termination_reason: 'g4_modeling status is failed',
      },
    })

    expect(callout).toBeNull()
  })

  it('prompts for model confirmation only while ordinary confirmation is pending', () => {
    const callout = createReviewCallout({
      ...activeStatus,
      status: 'paused',
      current_phase: 'human_confirmation',
      current_phase_idx: 4,
      needs_confirmation: true,
      key_statuses: {
        confirmation_status: 'pending',
      },
      state: {
        confirmation_status: 'pending',
        human_confirmation_required: true,
      },
    })

    expect(callout).toMatchObject({
      kind: 'human-confirmation',
      eyebrow: '需要人工确认',
      primaryLabel: '查看确认项',
      primaryCommand: '/confirm job-42',
    })
  })

  it('does not keep the current node on human confirmation after approval advances the phase', () => {
    const cockpit = createAgentCockpit({
      status: {
        ...activeStatus,
        current_phase: 'g4_codegen',
        current_phase_idx: 5,
        completed_phases: [
          'prepare_workspace',
          'context',
          'task_planning',
          'g4_modeling',
          'human_confirmation',
        ],
        needs_confirmation: false,
        key_statuses: {
          confirmation_status: 'approved',
        },
        state: {
          ...activeStatus.state,
          current_node: 'human_confirmation_subgraph',
          confirmation_status: 'approved',
          human_confirmation_required: false,
        },
      },
      events: [],
      artifacts: [],
    })

    expect(cockpit.agent.statusChips).toEqual(
      expect.arrayContaining([
        { label: '当前节点', value: 'G4 Codegen', tone: 'neutral' },
      ]),
    )
  })

  it('surfaces repair continuation as a distinct approval instead of generic confirmation', () => {
    const callout = createReviewCallout({
      ...activeStatus,
      status: 'paused',
      current_phase: 'g4_codegen',
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
    })

    expect(callout).toMatchObject({
      kind: 'repair-continuation',
      eyebrow: '需要批准继续修复',
      primaryLabel: '批准追加 12 轮',
      primaryCommand: '/confirm approve',
      secondaryLabel: '查看确认项',
      secondaryCommand: '/confirm job-42',
    })
  })

  it('builds a VS Code style agent cockpit model with RadAgent artifact groups', () => {
    const cockpit = createAgentCockpit({
      status: activeStatus,
      events: [
        {
          event_type: 'model_call_start',
          status: 'running',
          summary: 'Generating detector construction module',
          phase: 'g4_codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: {
            artifacts: [
              { path: '/tmp/radagent/job-42/05_codegen/proposed_patch.json' },
            ],
          },
          created_at: '2026-06-14T08:00:00Z',
        },
        {
          event_type: 'g4_codegen_persist',
          status: 'success',
          summary: 'G4 codegen persisted changed files',
          phase: 'g4_codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: { changed_file_count: 3 },
          created_at: '2026-06-14T08:01:00Z',
        },
      ],
      artifacts: [
        {
          path: '/tmp/radagent/job-42/05_codegen/proposed_patch.json',
          kind: 'json',
          stage: 'g4_codegen',
          size_bytes: 4096,
        },
        {
          path: '/tmp/radagent/job-42/06_patch/geant4_project/src/DetectorConstruction.cc',
          kind: 'source',
          stage: 'patch',
          size_bytes: 8192,
        },
        {
          path: '/tmp/radagent/job-42/08_artifact/final_report.md',
          kind: 'report',
          stage: 'report',
          size_bytes: 2048,
        },
      ],
      selectedPath: '/tmp/radagent/job-42/06_patch/geant4_project/src/DetectorConstruction.cc',
    })

    expect(cockpit.agent).toMatchObject({
      stateLabel: '运行中',
      phaseLabel: 'Geant4 工程生成',
      currentAction: 'G4 codegen persisted changed files',
      workspace: '/tmp/radagent/job-42',
      changedFiles: '3 个文件',
    })
    expect(cockpit.agent.statusChips).toEqual(
      expect.arrayContaining([
        { label: '当前节点', value: 'G4 Codegen', tone: 'neutral' },
        { label: 'Codegen', value: '运行中', tone: 'running' },
        { label: '构建模块', value: 'G4 Codegen Persist', tone: 'running' },
      ]),
    )
    expect(cockpit.fileGroups.map((group) => group.label)).toEqual([
      '工程生成',
      '修订补丁',
      '报告交付',
    ])
    expect(cockpit.fileGroups[1].files[0]).toMatchObject({
      name: 'DetectorConstruction.cc',
      kindLabel: '源码',
      selected: true,
      sizeLabel: '8 KB',
    })
    expect(cockpit.recentActivity[0]).toMatchObject({
      title: 'g4 codegen persist',
      detail: 'G4 codegen persisted changed files',
      statusLabel: '通过',
      phaseLabel: '工程生成',
    })
  })

  it('keeps latest agent activity at the top when timestamps tie', () => {
    const cockpit = createAgentCockpit({
      status: activeStatus,
      events: [
        {
          event_type: 'model_call_start',
          status: 'running',
          summary: 'Starting module prompt',
          phase: 'g4_codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: { module_name: 'detector_construction' },
          created_at: '2026-06-14T08:00:00Z',
        },
        {
          event_type: 'module_layer_finished',
          status: 'success',
          summary: 'Detector module files generated',
          phase: 'g4_codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: { module_name: 'detector_construction' },
          created_at: '2026-06-14T08:00:00Z',
        },
      ],
      artifacts: [],
    })

    expect(cockpit.recentActivity.map((row) => row.title)).toEqual([
      'module layer finished',
      'model call start',
    ])
    expect(cockpit.agent.currentAction).toBe('Detector module files generated')
  })

  it('surfaces codegen wait and repair state as readable status chips', () => {
    const cockpit = createAgentCockpit({
      status: {
        ...activeStatus,
        key_statuses: {
          g4_codegen_status: 'needs_user_input',
          repair_continuation_status: 'pending',
        },
        state: {
          ...activeStatus.state,
          current_node: 'g4_codegen_subgraph',
          g4_codegen_status: 'needs_user_input',
          repair_continuation_status: 'pending',
          repair_continuation_request: {
            status: 'pending',
            current_turns: 48,
            requested_total_turns: 60,
          },
          global_integration_agent_report: {
            agentic: {
              n_turns: 48,
              stop_reason: 'max_turns',
            },
          },
        },
      },
      events: [
        {
          event_type: 'runtime_execution_audit',
          status: 'warning',
          summary: 'Runtime execution audit paused for repair continuation approval.',
          phase: 'g4_codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: { module_name: 'runtime_execution_auditor' },
          created_at: '2026-06-14T08:03:00Z',
        },
      ],
      artifacts: [],
    })

    expect(cockpit.agent.statusChips).toEqual(
      expect.arrayContaining([
        { label: '当前节点', value: 'G4 Codegen Subgraph', tone: 'neutral' },
        { label: 'Codegen', value: '等待人工确认', tone: 'warning' },
        { label: '构建模块', value: 'Runtime Execution Auditor', tone: 'running' },
        { label: '修复轮数', value: '48/60', tone: 'warning' },
        { label: '等待事项', value: '批准继续修复', tone: 'warning' },
      ]),
    )
  })

  it('keeps Copilot events out of the workflow phase summary', () => {
    const cockpit = createAgentCockpit({
      status: activeStatus,
      events: [
        {
          event_type: 'g4_codegen_persist',
          status: 'success',
          summary: 'G4 codegen persisted changed files',
          phase: 'g4_codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: { changed_file_count: 2 },
          created_at: '2026-06-14T08:01:00Z',
        },
        {
          event_type: 'copilot_finished',
          status: 'success',
          summary: 'Copilot answered status question',
          phase: '',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: {},
          created_at: '2026-06-14T08:02:00Z',
        },
      ],
      artifacts: [],
    })

    expect(cockpit.agent).toMatchObject({
      stateLabel: '运行中',
      phaseLabel: 'Geant4 工程生成',
      currentAction: 'G4 codegen persisted changed files',
    })
    expect(cockpit.recentActivity.map((row) => row.title)).toEqual(['g4 codegen persist'])
  })

  it('derives current and recent LLM debug calls from model_call events', () => {
    const cockpit = createAgentCockpit({
      status: activeStatus,
      events: [
        {
          event_type: 'model_call_start',
          status: 'running',
          summary: 'Build detector prompt',
          phase: 'codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: {
            metrics: { system_prompt_chars: 4504, user_prompt_chars: 26289 },
            artifacts: [{ path: 'logs/model_calls/call-a_detector_codegen.json' }],
            details: {
              tier: 'pro',
              model_name: 'mimo-v2.5-pro',
              metadata: { model_call_id: 'call-a', module_name: 'detector_construction' },
            },
          },
          created_at: '2026-06-14T08:00:00Z',
        },
        {
          event_type: 'model_call',
          status: 'passed' as any,
          summary: 'Build detector result',
          phase: 'codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: {
            duration_ms: 104435.897,
            metrics: { content_length: 9815, parsed_json: true },
            artifacts: [{ path: 'logs/model_calls/call-a_detector_codegen.json' }],
            details: {
              tier: 'pro',
              model_name: 'mimo-v2.5-pro',
              metadata: { model_call_id: 'call-a', module_name: 'detector_construction' },
            },
          },
          created_at: '2026-06-14T08:01:44Z',
        },
        {
          event_type: 'model_call_start',
          status: 'running',
          summary: 'Context summary prompt',
          phase: 'context_summary',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: {
            metrics: { system_prompt_chars: 100, user_prompt_chars: 200 },
            artifacts: [{ path: 'logs/model_calls/call-b_context_summary.json' }],
            details: {
              tier: 'lite',
              provider: 'openai_compatible',
              model_name: 'mimo-v2.5',
              metadata: {
                model_call_id: 'call-b',
                module_name: 'coordinate_core_modules_context',
              },
            },
          },
          created_at: '2026-06-14T08:02:00Z',
        },
      ],
      artifacts: [],
    })

    expect(cockpit.llmDebugCalls).toHaveLength(2)
    expect(cockpit.llmDebugCalls[0]).toMatchObject({
      id: 'call-b',
      phase: 'context_summary',
      moduleName: 'coordinate_core_modules_context',
      modelName: 'mimo-v2.5',
      statusLabel: '运行中',
      durationLabel: '进行中',
      promptSummary: 'Context summary prompt',
      promptCharsLabel: '300 字符',
      outputSummary: '等待模型输出',
      artifactPath: 'logs/model_calls/call-b_context_summary.json',
    })
    expect(cockpit.llmDebugCalls[1]).toMatchObject({
      id: 'call-a',
      phase: 'codegen',
      moduleName: 'detector_construction',
      modelName: 'mimo-v2.5-pro',
      statusLabel: '通过',
      durationLabel: '104.4 秒',
      promptSummary: 'Build detector prompt',
      promptCharsLabel: '30,793 字符',
      outputSummary: 'Build detector result',
      outputCharsLabel: '9,815 字符',
      artifactPath: 'logs/model_calls/call-a_detector_codegen.json',
    })
  })

  it('does not present start-only model calls as live when runtime is inactive', () => {
    const cockpit = createAgentCockpit({
      status: {
        ...activeStatus,
        key_statuses: { runtime_active: false },
        state: { ...activeStatus.state, runtime_active: false },
      },
      events: [
        {
          event_type: 'model_call_start',
          status: 'running',
          summary: 'Interrupted codegen prompt',
          phase: 'codegen',
          job_id: 'job-42',
          run_id: 'run-1',
          payload: {
            artifacts: [{ path: 'logs/model_calls/call-stale_codegen.json' }],
            details: {
              model_name: 'mimo-v2.5-pro',
              metadata: { model_call_id: 'call-stale', module_name: 'simulation_core' },
            },
          },
          created_at: '2026-06-14T08:03:00Z',
        },
      ],
      artifacts: [],
    })

    expect(cockpit.llmDebugCalls[0]).toMatchObject({
      id: 'call-stale',
      statusLabel: '记录',
      durationLabel: '未记录',
      outputSummary: '等待继续后刷新',
    })
  })
})
