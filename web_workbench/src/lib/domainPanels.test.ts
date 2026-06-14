import { describe, expect, it } from 'vitest'
import { createDomainPanel, isDomainPanelView } from './domainPanels'

describe('domain inspector presentation', () => {
  it('summarizes runtime tools from startup status', () => {
    const panel = createDomainPanel('tools', {
      project_slug: 'default',
      workspace_root: '/workspace',
      tools: {
        geant4: {
          label: 'Geant4',
          configured: true,
          available: false,
          path: '/opt/geant4/bin/geant4-config',
          detail: 'cmake=ok',
        },
        ngspice: {
          label: 'ngspice',
          configured: false,
          available: false,
          path: '',
          detail: 'set NGSPICE_BIN',
        },
      },
    })

    expect(panel?.title).toBe('本地运行环境')
    expect(panel?.metrics).toEqual([
      { label: '项目', value: '默认' },
      { label: '工具', value: '2' },
      { label: '可用', value: '0' },
    ])
    expect(panel?.rows[0]).toMatchObject({
      title: 'Geant4',
      status: '已配置',
      detail: 'cmake=ok',
      meta: '/opt/geant4/bin/geant4-config',
    })
  })

  it('summarizes credibility gates without exposing raw JSON first', () => {
    const panel = createDomainPanel('credibility', {
      status: 'pass',
      credibility_level: 'high',
      confidence: 0.91,
      message: 'Evidence is consistent.',
      warnings: ['mesh coarse near source'],
    })

    expect(panel?.title).toBe('可信度审查')
    expect(panel?.metrics).toEqual([
      { label: '状态', value: '通过' },
      { label: '级别', value: '高' },
      { label: '置信度', value: '0.91' },
    ])
    expect(panel?.summary).toBe('Evidence is consistent.')
    expect(panel?.rows[0].title).toBe('mesh coarse near source')
  })

  it('presents workflow memory items as rows', () => {
    const panel = createDomainPanel('memory', {
      job_id: 'job-1',
      phase: 'g4_modeling',
      memory: [
        { source: 'gate', key: 'geometry', summary: 'Detector radius fixed at 5 cm.' },
        { source: 'artifact', key: 'report', summary: 'Report generated.' },
      ],
    })

    expect(isDomainPanelView('memory')).toBe(true)
    expect(isDomainPanelView('status')).toBe(false)
    expect(panel?.metrics).toEqual([
      { label: '作业', value: 'job-1' },
      { label: '阶段', value: 'Geant4 建模' },
      { label: '记忆', value: '2' },
    ])
    expect(panel?.rows.map((row) => row.title)).toEqual(['geometry', 'report'])
  })
})
