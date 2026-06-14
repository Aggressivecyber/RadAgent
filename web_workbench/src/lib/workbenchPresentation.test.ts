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
  current_phase_idx: 5,
  completed_phases: ['prepare_workspace', 'context', 'task_planning', 'g4_modeling'],
  execution_mode: 'strict',
  run_mode: 'local',
  workspace_root: '/tmp/radagent',
  job_workspace: '/tmp/radagent/job-42',
  needs_confirmation: false,
  key_statuses: {},
  state: { project_slug: 'proton-depth-dose' },
}

describe('workbench presentation', () => {
  it('summarizes the active Geant4 workflow as a Chinese-first hero', () => {
    expect(createWorkbenchHero(activeStatus)).toEqual({
      eyebrow: 'Proton Depth Dose',
      title: '150 MeV proton depth-dose benchmark',
      subtitle: '当前推进到 Geant4 工程生成，已完成 4/10 个阶段。',
      statusText: '运行中 · Geant4 工程生成',
      modeText: '本地运行 · strict',
    })
  })

  it('falls back to a ready state when no job is active', () => {
    expect(createWorkbenchHero(null)).toMatchObject({
      eyebrow: 'RadAgent',
      title: '等待仿真任务',
      statusText: '待命 · 准备工作区',
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
      'g4_modeling',
      'human_confirmation',
      'g4_codegen',
      'patch',
      'gate',
      'artifact',
      'report',
    ])
    expect(track.find((phase) => phase.id === 'g4_modeling')).toMatchObject({
      label: 'Geant4 建模',
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

  it('does not show human approval again after model confirmation is approved', () => {
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

    expect(callout).toMatchObject({
      kind: 'visual-review',
      eyebrow: '需要可视化复核',
      primaryLabel: '打开工作台',
      primaryCommand: '/workbench 100',
      secondaryLabel: '记录通过',
      secondaryCommand: '/visual-approve',
    })
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
      primaryCommand: '/confirm',
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
      statusLabel: '通过',
      phaseLabel: '工程生成',
    })
  })
})
