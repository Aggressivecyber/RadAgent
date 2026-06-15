import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import InspectorPanel from './InspectorPanel'
import type { JobStatus } from '../lib/api'

const status: JobStatus = {
  job_id: 'job_42',
  user_query: 'Build a neutron shielding benchmark.',
  status: 'failed',
  current_phase: 'human_confirmation',
  current_phase_idx: 4,
  completed_phases: ['prepare_workspace', 'context', 'task_planning', 'g4_modeling'],
  execution_mode: 'strict',
  run_mode: 'strict',
  workspace_root: '/tmp/radagent',
  job_workspace: '/tmp/radagent/job_42',
  needs_confirmation: false,
  key_statuses: { g4_modeling_status: 'failed' },
  state: { g4_modeling_status: 'failed' },
}

describe('InspectorPanel', () => {
  it('renders workflow diagnosis as a readable non-approval panel', () => {
    const markup = renderToStaticMarkup(
      <InspectorPanel
        active="diagnosis"
        data={{
          ui_state: 'modeling_failed',
          severity: 'error',
          phase: 'g4_modeling',
          user_message: '建模阶段失败，人工确认不能批准。',
          blocking_reason: 'No oxide layer is required for this shielding stack.',
          next_step_hint: '查看建模校验报告并重新运行建模。',
          confirmation_actionable: false,
          allowed_actions: ['view_modeling_report', 'retry_modeling'],
          hard_rules: {
            confirmation_actionable: false,
            reason: 'g4_modeling_status is not passed',
          },
          artifacts: ['/tmp/radagent/job_42/03_model_ir/validation_report.json'],
          model_enhanced: true,
        }}
        commands={[]}
        status={status}
        events={[]}
        onSelectCommand={() => {}}
        onSelectRecord={() => {}}
        onSaveModelConfig={async () => {}}
        onTestModelHealth={async () => ({ tested_at: '', tiers: {} })}
        onExecuteCommand={async () => {}}
      />,
    )

    expect(markup).toContain('诊断')
    expect(markup).toContain('Workflow diagnosis')
    expect(markup).toContain('建模阶段失败，人工确认不能批准。')
    expect(markup).toContain('No oxide layer is required for this shielding stack.')
    expect(markup).toContain('查看建模校验报告并重新运行建模。')
    expect(markup).toContain('不可审批')
    expect(markup).toContain('view_modeling_report')
    expect(markup).toContain('retry_modeling')
    expect(markup).toContain('g4_modeling_status is not passed')
    expect(markup).not.toContain('json-preview')
  })
})
