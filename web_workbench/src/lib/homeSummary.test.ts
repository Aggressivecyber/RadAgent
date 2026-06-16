import { describe, expect, it } from 'vitest'
import { normalizeHomeSummary } from './homeSummary'

describe('normalizeHomeSummary', () => {
  it('uses showcase examples instead of exposing user project cards on Home', () => {
    const summary = normalizeHomeSummary({
      metrics: {
        projects: 2,
        jobs: 4,
        completed_jobs: 3,
        active_jobs: 1,
        artifacts: 9,
      },
      workflow_capabilities: [
        {
          name: 'Intent capture',
          description: 'Turn a request into a structured simulation objective.',
          command: '/run',
        },
      ],
      projects: [
        {
          job_id: 'job-1',
          title: 'HPGe detector response workflow',
          project_name: 'Detector Workflows',
          status: 'completed',
          phase: 'report',
          updated_at: '2026-06-13 09:12:00',
          artifact_count: 2,
          artifact_kinds: ['report', 'source'],
        },
      ],
      showcase_examples: [
        {
          id: 'example-hpge-coincidence',
          title: 'HPGe 反符合谱仪',
          subtitle: 'Anti-coincidence HPGe spectrometer',
          prompt: 'Build a Geant4 workflow for an HPGe anti-coincidence gamma spectrometer.',
          difficulty: 'advanced',
          tags: ['HPGe', 'anti-coincidence', 'spectrum'],
          validation_focus: ['geometry', 'scoring'],
        },
      ],
    })

    expect(summary.metrics.completed_jobs).toBe(3)
    expect(summary.metricTiles[0]).toEqual({ label: '项目', labelEn: 'Projects', value: '2' })
    expect(summary.workflowCapabilities[0].name).toBe('Intent capture')
    expect(summary.toolUseItems.map((item) => item.title)).toEqual([
      '任务转仿真链路',
      'Geant4 可信模型',
      '材料屏蔽检查',
      '本地工程生成',
      '运行得到结果',
      '审查与修订',
    ])
    expect(summary.capabilityShowcases).toHaveLength(2)
    expect(summary.capabilityShowcases[0]).toMatchObject({
      title: '防护建模',
      label: 'Shielding model',
      items: [
        { title: '任务拆解', demoIndex: '01' },
        { title: '模型证据', demoIndex: '02' },
        { title: '参数确认', demoIndex: '06' },
      ],
    })
    expect(summary.capabilityShowcases[1].items.map((item) => item.demoIndex)).toEqual([
      '03',
      '04',
      '05',
    ])
    expect(summary.advantageItems.map((item) => item.title)).toEqual([
      '空天辐照防护',
      'Geant4 可信建模',
      '空间辐射源接入',
      '本地构建运行',
      '多层验证门禁',
      '产物可复查',
    ])
    expect(summary.advantageItems.map((item) => item.body).join(' ')).toContain('AP8/AE8')
    expect(summary.advantageItems.map((item) => item.body).join(' ')).toContain('本地')
    expect(summary.showcaseCards[0]).toMatchObject({
      id: 'example-hpge-coincidence',
      title: 'HPGe 反符合谱仪',
      subtitle: 'Anti-coincidence HPGe spectrometer',
      prompt: expect.stringContaining('Geant4'),
      difficulty: 'advanced',
      tags: ['HPGe', 'anti-coincidence', 'spectrum'],
      validationFocus: ['几何闭合检查', '反符合计分逻辑', '报告可追溯'],
      deliverables: ['Geant4 工程', '能谱直方图', '门禁报告'],
    })
  })

  it('keeps the home screen populated when there are no persisted jobs yet', () => {
    const summary = normalizeHomeSummary({
      metrics: {
        projects: 0,
        jobs: 0,
        completed_jobs: 0,
        active_jobs: 0,
        artifacts: 0,
      },
      workflow_capabilities: [],
      projects: [],
      showcase_examples: [],
    })

    expect(summary.workflowCapabilities).toHaveLength(6)
    expect(summary.toolUseItems).toHaveLength(6)
    expect(summary.capabilityShowcases.flatMap((group) => group.items)).toHaveLength(6)
    expect(summary.advantageItems).toHaveLength(6)
    expect(summary.toolUseItems[2].body).toContain('屏蔽材料')
    expect(summary.showcaseCards).toHaveLength(4)
    expect(summary.showcaseCards[0].title).toBe('HPGe 反符合谱仪')
    expect(summary.showcaseCards[0].prompt).toContain('coincidence')
    expect(summary.showcaseCards.every((card) => card.validationFocus.length >= 2)).toBe(true)
    expect(summary.showcaseCards.every((card) => card.deliverables.length >= 3)).toBe(true)
    expect(summary.metricTiles.map((tile) => tile.value)).toEqual(['0', '0', '0', '0'])
  })
})
