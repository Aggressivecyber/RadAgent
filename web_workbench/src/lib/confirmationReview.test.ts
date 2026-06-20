import { describe, expect, it } from 'vitest'
import { buildQuestionCardSupplement, createConfirmationReviewView } from './confirmationReview'

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
      recommendedValue: '150 MeV',
      fieldPath: 'sources.primary.energy',
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
        title: '参数核对报告',
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
        summary_for_user: '模型已用默认值补全，请参数核对后继续。',
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

  it('builds a source-aware parameter checklist for human review', () => {
    const view = createConfirmationReviewView({
      status: 'pending',
      confirmation_request: {
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
    })

    expect(view.parameterChecklist).toEqual([
      {
        title: 'sources.primary.energy',
        value: '14 MeV',
        detail: '',
        meta: 'user · 98%',
        tone: 'confirmed',
        statusLabel: '明确',
      },
      {
        title: 'components.detector.material',
        value: 'G4_Si',
        detail: '用户只说了半导体探测器，材料由 AI 补全。',
        meta: 'ai_inferred · 52%',
        tone: 'needs-review',
        statusLabel: 'AI 补全 / 需确认',
      },
    ])
  })

  it('presents max-model requirements review as a parameter confirmation card', () => {
    const view = createConfirmationReviewView({
      type: 'requirements_review',
      status: 'pending',
      summary_for_user: '请确认质子束、水箱尺寸和 scoring。',
      requirements_review: {
        missing_information: ['Water phantom dimensions are not specified.'],
        physics_risks: ['Physics cuts are unspecified.'],
        proposed_parameters: [
          {
            field_path: 'source.particle',
            proposed_value: 'proton',
            source_type: 'user',
            confidence: 0.99,
          },
          {
            field_path: 'target.size',
            proposed_value: '30 cm x 30 cm x 30 cm',
            source_type: 'max_model_proposed_default',
            confidence: 0.62,
            requires_confirmation: true,
          },
        ],
        ambiguous_parameters: [
          {
            field_path: 'target.size',
            reason: 'User asked for depth-dose but did not give phantom size.',
          },
        ],
      },
    })

    expect(view.summary).toBe('请确认质子束、水箱尺寸和 scoring。')
    expect(view.missingInformation).toEqual(['Water phantom dimensions are not specified.'])
    expect(view.assumptions).toEqual(['Physics cuts are unspecified.'])
    expect(view.parameterChecklist).toEqual([
      {
        title: 'source.particle',
        value: 'proton',
        detail: '',
        meta: 'user · 99%',
        tone: 'confirmed',
        statusLabel: '明确',
      },
      {
        title: 'target.size',
        value: '30 cm x 30 cm x 30 cm',
        detail: 'User asked for depth-dose but did not give phantom size.',
        meta: 'max_model_proposed_default · 62%',
        tone: 'needs-review',
        statusLabel: 'AI 补全 / 需确认',
      },
    ])
  })

  it('normalizes requirements review questions into recommendation cards', () => {
    const view = createConfirmationReviewView({
      type: 'requirements_review',
      status: 'pending',
      confirmation_request: {
        questions: [
          {
            field_path: 'source.energy',
            question: '束流能量是否使用 160 MeV？',
            recommended_value: '160 MeV',
            reason: '用户补充说能量改成 160 MeV。',
          },
          {
            field_path: 'scoring.sensitive_volume',
            question: '是否在敏感体内记录 dose/edep/step length？',
            proposed_value: '记录通用 sensitive volume 内的 dose、edep、step length、track id。',
            reason: '这是管线能在代码中实现的通用计分逻辑。',
          },
        ],
      },
    })

    expect(view.questionCards).toEqual([
      {
        fieldPath: 'source.energy',
        question: '束流能量是否使用 160 MeV？',
        recommendedValue: '160 MeV',
        reason: '用户补充说能量改成 160 MeV。',
      },
      {
        fieldPath: 'scoring.sensitive_volume',
        question: '是否在敏感体内记录 dose/edep/step length？',
        recommendedValue: '记录通用 sensitive volume 内的 dose、edep、step length、track id。',
        reason: '这是管线能在代码中实现的通用计分逻辑。',
      },
    ])
  })

  it('dedupes requirements questions mirrored through request and review payloads', () => {
    const question = {
      field_path: 'shielding.layer_thicknesses',
      question: '各屏蔽层的厚度分别是多少？',
      recommended_value: '聚乙烯 5 cm，含硼聚乙烯 5 cm，铅 2 cm，硅探测器 3 mm',
      reason: '缺少厚度时无法构建可靠几何。',
    }
    const view = createConfirmationReviewView({
      type: 'requirements_review',
      status: 'pending',
      questions: [question],
      confirmation_request: {
        questions: [question],
      },
      requirements_review: {
        questions: [question],
      },
    })

    expect(view.questionCards).toHaveLength(1)
    expect(view.questionCards[0]).toMatchObject({
      fieldPath: 'shielding.layer_thicknesses',
      question: '各屏蔽层的厚度分别是多少？',
    })
  })

  it('builds a compact supplement from per-question card answers', () => {
    const supplement = buildQuestionCardSupplement(
      [
        {
          fieldPath: 'source.energy',
          question: '束流能量是否使用 160 MeV？',
          recommendedValue: '160 MeV',
          reason: '',
        },
        {
          fieldPath: 'scoring.bin_width',
          question: '剂量深度 bin 是否使用 1 mm？',
          recommendedValue: '1 mm',
          reason: '',
        },
      ],
      {
        'source.energy': { mode: 'recommended', value: '160 MeV' },
        'scoring.bin_width': { mode: 'modified', value: '0.5 mm' },
      },
      '事件数使用 10000。',
    )

    expect(supplement).toBe(
      'source.energy: 确认推荐 160 MeV\n' +
        'scoring.bin_width: 修改为 0.5 mm\n' +
        '补充说明: 事件数使用 10000。',
    )
  })

  it('can append machine-readable confirmed parameter answers for the backend prompt', () => {
    const supplement = buildQuestionCardSupplement(
      [
        {
          fieldPath: 'environment.medium',
          question: '是否坚持当前真空环境，还是改为冷却水介质？',
          recommendedValue: '保持真空环境',
          reason: '用户已指定真空环境，冷却水只是模型改进建议。',
        },
        {
          fieldPath: 'geometry.robot_model',
          question: '机器人几何是否采用分层壳体？',
          recommendedValue: '保持 10cm x 10cm x 20cm 铁质机器人简化模型',
          reason: '用户原始需求只要求铁质机器人。',
        },
      ],
      {
        'environment.medium': { mode: 'recommended', value: '保持真空环境' },
        'geometry.robot_model': {
          mode: 'modified',
          value: '采用分层壳体机器人模型，但保留外形 10cm x 10cm x 20cm',
        },
      },
      '先按本轮选择继续。',
      { includeMachinePayload: true },
    )

    expect(supplement).toContain('environment.medium: 确认推荐 保持真空环境')
    expect(supplement).toContain('geometry.robot_model: 修改为 采用分层壳体机器人模型')

    const marker = 'RADAGENT_CONFIRMATION_JSON:'
    const payload = JSON.parse(supplement.slice(supplement.indexOf(marker) + marker.length))
    expect(payload).toMatchObject({
      schema_version: 'requirements_review_answers_v1',
      user_note: '先按本轮选择继续。',
      confirmed_parameters: [
        {
          field_path: 'environment.medium',
          decision: 'accept_recommended',
          selected_value: '保持真空环境',
          recommended_value: '保持真空环境',
        },
        {
          field_path: 'geometry.robot_model',
          decision: 'modify',
          selected_value: '采用分层壳体机器人模型，但保留外形 10cm x 10cm x 20cm',
          recommended_value: '保持 10cm x 10cm x 20cm 铁质机器人简化模型',
        },
      ],
    })
  })
})
