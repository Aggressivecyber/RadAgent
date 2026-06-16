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
  it('renders a color-coded parameter checklist in the confirmation panel', () => {
    const markup = renderToStaticMarkup(
      <InspectorPanel
        active="confirmation"
        data={{
          status: 'pending',
          confirmation_request: {
            summary_for_user: '模型已用默认值补全，请人工确认后继续。',
            ambiguous_fields: [
              {
                field_path: 'components.detector.material',
                proposed_value: 'G4_Si',
                reason: '用户只说了半导体探测器，材料由 AI 补全。',
              },
            ],
          },
          proposed_model_completion: {
            proposed_parameters: [
              {
                field_path: 'sources.primary.energy',
                proposed_value: '14 MeV',
                source_type: 'user',
                confidence: 0.98,
              },
              {
                field_path: 'components.detector.material',
                proposed_value: 'G4_Si',
                source_type: 'ai_inferred',
                confidence: 0.52,
                requires_confirmation: true,
              },
            ],
          },
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

    expect(markup).toContain('参数核对')
    expect(markup).toContain('confirmation-parameter-row confirmed')
    expect(markup).toContain('confirmation-parameter-row needs-review')
    expect(markup).toContain('sources.primary.energy')
    expect(markup).toContain('明确')
    expect(markup).toContain('components.detector.material')
    expect(markup).toContain('AI 补全 / 需确认')
    expect(markup).toContain('修改意见或补充参数')
  })

  it('renders selected job confirmation request details instead of the empty preview state', () => {
    const markup = renderToStaticMarkup(
      <InspectorPanel
        active="confirmation"
        data={{
          status: 'pending',
          summary_for_user: '请确认水层厚度。',
          confirmation_request: {
            questions: [
              {
                field_path: 'components.water.dimensions',
                proposed_value: { dz: 300000.0 },
                impact: '影响 Bragg peak 位置。',
              },
            ],
          },
          proposed_model_completion: {
            missing_information: ['Step limiter settings need definition.'],
            proposed_components: [
              {
                component_id: 'water',
                component_type: 'layer',
                material_id: 'G4_WATER',
                parameters: [
                  {
                    field_path: 'components.water.dimensions',
                    proposed_value: { dz: 300000.0 },
                    source_type: 'assumption',
                    confidence: 0.4,
                    requires_confirmation: true,
                  },
                ],
              },
            ],
          },
          preview: 'human confirmation report',
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

    expect(markup).toContain('请确认水层厚度。')
    expect(markup).toContain('参数核对')
    expect(markup).toContain('components.water.dimensions')
    expect(markup).toContain('AI 补全 / 需确认')
    expect(markup).toContain('Step limiter settings need definition.')
    expect(markup).toContain('human confirmation report')
    expect(markup).not.toContain('暂无确认预览。')
  })

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
