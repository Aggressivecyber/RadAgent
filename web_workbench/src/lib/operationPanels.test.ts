import { describe, expect, it } from 'vitest'
import { createOperationPanel, isOperationPanelView } from './operationPanels'

describe('operation panel presentation', () => {
  it('turns build output into concise metrics and error preview', () => {
    const panel = createOperationPanel('build', {
      success: false,
      configure: { returncode: 0 },
      build: { returncode: 2 },
      executable_path: '',
      errors: 'No generated code directory in current state.',
    })

    expect(panel?.title).toBe('Build result')
    expect(panel?.metrics).toEqual([
      { label: 'Result', value: 'failed' },
      { label: 'Configure', value: 'ok' },
      { label: 'Build', value: 'failed' },
      { label: 'Executable', value: 'not available' },
    ])
    expect(panel?.preview).toBe('No generated code directory in current state.')
  })

  it('summarizes simulation output without raw JSON fallback', () => {
    const panel = createOperationPanel('simulation', {
      success: true,
      output_dir: '/tmp/job/output',
      log: 'BeamOn completed 250 events',
      errors: '',
    })

    expect(panel?.title).toBe('Simulation result')
    expect(panel?.metrics).toEqual([
      { label: 'Result', value: 'passed' },
      { label: 'Output', value: '/tmp/job/output' },
    ])
    expect(panel?.preview).toBe('BeamOn completed 250 events')
  })

  it('extracts report and open command artifacts into selectable rows', () => {
    const panel = createOperationPanel('report', {
      target: 'report',
      artifacts: [
        { path: '/tmp/final_report.md', kind: 'report', stage: 'report' },
        { path: '/tmp/g4_summary.json', kind: 'json', stage: 'output' },
      ],
    })

    expect(panel?.title).toBe('Report artifacts')
    expect(panel?.metrics).toEqual([
      { label: 'Target', value: 'report' },
      { label: 'Artifacts', value: '2' },
    ])
    expect(panel?.artifacts.map((artifact) => artifact.path)).toEqual([
      '/tmp/final_report.md',
      '/tmp/g4_summary.json',
    ])
  })

  it('models visual workbench and review actions as operation panels', () => {
    const workbench = createOperationPanel('workbench', {
      success: true,
      events: 100,
      launched: true,
      executable: '/tmp/example',
      working_dir: '/tmp/job',
      errors: '',
    })
    const review = createOperationPanel('visual-review', {
      status: 'rejected',
      notes: 'Geometry needs a clearer shield boundary.',
    })

    expect(isOperationPanelView('workbench')).toBe(true)
    expect(isOperationPanelView('status')).toBe(false)
    expect(workbench?.metrics).toEqual([
      { label: 'Result', value: 'passed' },
      { label: 'Events', value: '100' },
      { label: 'Launched', value: 'yes' },
    ])
    expect(workbench?.preview).toContain('/tmp/example')
    expect(review?.title).toBe('Visual review')
    expect(review?.preview).toBe('Geometry needs a clearer shield boundary.')
  })
})
