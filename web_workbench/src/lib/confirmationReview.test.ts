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

  it('marks an approved confirmation review as non-actionable', () => {
    const view = createConfirmationReviewView({
      status: 'approved',
      preview: 'Approved confirmation report markdown.',
    })

    expect(view.status).toBe('approved')
    expect(view.actionable).toBe(false)
  })
})
