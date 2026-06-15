import { describe, expect, it } from 'vitest'
import { createConfirmationReviewView } from './confirmationReview'

describe('confirmation review presentation', () => {
  it('extracts ambiguous fields, critical confirmations and questions', () => {
    const view = createConfirmationReviewView({
      status: 'pending',
      confirmation_request: {
        summary_for_user: '关键确认项会影响 Geant4 代码生成。',
        missing_information: ['Beam spot size was not specified.'],
        critical_confirmations: [
          {
            field_path: 'components.water_tank.geometry',
            category: 'dimension',
            proposed_value: { x: 10, y: 10, z: 10 },
            impact: '影响 Geant4 几何尺寸。',
          },
        ],
        questions: [
          {
            field_path: 'sources.primary.energy',
            question: '请确认 primary source 的 energy',
            proposed_value: '150 MeV',
            impact: '影响粒子类型、能量、方向和轨迹预览。',
          },
        ],
      },
    })

    expect(view.summary).toBe('关键确认项会影响 Geant4 代码生成。')
    expect(view.missingInformation).toEqual(['Beam spot size was not specified.'])
    expect(view.criticalConfirmations[0]).toMatchObject({
      title: 'components.water_tank.geometry',
      detail: '影响 Geant4 几何尺寸。',
      meta: 'dimension',
    })
    expect(view.questions[0]).toMatchObject({
      title: '请确认 primary source 的 energy',
      detail: '影响粒子类型、能量、方向和轨迹预览。',
      meta: '150 MeV',
    })
  })

  it('falls back to an explicit confirmation summary when only preview text is available', () => {
    const view = createConfirmationReviewView({
      status: 'pending',
      preview: 'Human confirmation report markdown.',
    })

    expect(view.summary).toContain('请确认本轮 Geant4 模型假设')
    expect(view.preview).toBe('Human confirmation report markdown.')
  })

  it('derives a visible confirmation item from preview when structured lists are empty', () => {
    const view = createConfirmationReviewView({
      status: 'pending',
      summary: '',
      confirmation_request: {
        questions: [],
        critical_confirmations: [],
      },
      proposed_model_completion: {
        proposed_components: [],
        proposed_sources: [],
        proposed_scoring: [],
      },
      preview: '# Human Confirmation Report\n\n## Task Summary\n\n确认 14 MeV neutron 屏蔽模型。',
    })

    expect(view.proposedItems).toEqual([
      {
        title: '人工确认报告',
        detail: '# Human Confirmation Report\n\n## Task Summary\n\n确认 14 MeV neutron 屏蔽模型。',
        meta: 'report',
      },
    ])
  })

  it('marks an approved confirmation review as non-actionable', () => {
    const view = createConfirmationReviewView({
      status: 'approved',
      preview: 'Approved confirmation report markdown.',
    })

    expect(view.status).toBe('approved')
    expect(view.actionable).toBe(false)
  })

  it('marks modeling failure reviews as non-actionable and keeps the failure summary', () => {
    const view = createConfirmationReviewView({
      type: 'modeling_failure',
      status: 'failed',
      actionable: false,
      summary: 'NoSimplification: Complex model requested but no oxide component found.',
      preview: 'Validation report: validation_report.json',
    })

    expect(view.status).toBe('failed')
    expect(view.actionable).toBe(false)
    expect(view.summary).toContain('NoSimplification')
    expect(view.preview).toContain('validation_report.json')
  })

  it('surfaces proposed model details even when the request has no questions', () => {
    const view = createConfirmationReviewView({
      status: 'pending',
      confirmation_request: {
        summary_for_user: '模型已用默认值补全，请人工确认后继续。',
        questions: [],
      },
      proposed_model_completion: {
        proposed_components: [
          {
            component_id: 'mosfet_gate_oxide',
            component_type: 'oxide',
            material_id: 'SiO2',
            geometry: { thickness_nm: 10 },
            requires_confirmation: true,
          },
        ],
        proposed_sources: [
          {
            field_path: 'sources.primary.particle_type',
            proposed_value: 'gamma',
            source_type: 'default',
            confidence: 0.6,
          },
        ],
        proposed_scoring: [
          {
            field_path: 'scoring.tid_dose.scoring_type',
            proposed_value: 'dose',
            source_type: 'default',
            confidence: 0.6,
          },
        ],
        assumptions: ['Assumed Co-60 gamma irradiation because the user only said TID.'],
      },
    })

    expect(view.proposedItems).toHaveLength(3)
    expect(view.proposedItems[0]).toMatchObject({
      title: 'mosfet_gate_oxide',
      meta: 'oxide · SiO2',
    })
    expect(view.proposedItems[1].title).toBe('sources.primary.particle_type')
    expect(view.proposedItems[2].title).toBe('scoring.tid_dose.scoring_type')
    expect(view.assumptions).toEqual([
      'Assumed Co-60 gamma irradiation because the user only said TID.',
    ])
  })
})
