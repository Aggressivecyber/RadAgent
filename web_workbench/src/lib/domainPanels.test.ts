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

    expect(panel?.title).toBe('Runtime tools')
    expect(panel?.metrics).toEqual([
      { label: 'Project', value: 'default' },
      { label: 'Tools', value: '2' },
      { label: 'Available', value: '0' },
    ])
    expect(panel?.rows[0]).toMatchObject({
      title: 'Geant4',
      status: 'configured',
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

    expect(panel?.title).toBe('Credibility')
    expect(panel?.metrics).toEqual([
      { label: 'Status', value: 'pass' },
      { label: 'Level', value: 'high' },
      { label: 'Confidence', value: '0.91' },
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
      { label: 'Job', value: 'job-1' },
      { label: 'Phase', value: 'g4_modeling' },
      { label: 'Memory', value: '2' },
    ])
    expect(panel?.rows.map((row) => row.title)).toEqual(['geometry', 'report'])
  })
})
