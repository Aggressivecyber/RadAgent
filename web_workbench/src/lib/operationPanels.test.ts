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

    expect(panel?.title).toBe('构建结果')
    expect(panel?.metrics).toEqual([
      { label: '结果', value: '失败' },
      { label: '配置', value: '通过' },
      { label: '构建', value: '失败' },
      { label: '可执行文件', value: '不可用' },
    ])
    expect(panel?.preview).toBe('No generated code directory in current state.')
  })

  it('summarizes simulation output without raw JSON fallback', () => {
    const panel = createOperationPanel('simulation', {
      success: true,
      events: 250,
      visual_events: 100,
      visual_success: true,
      production_success: true,
      output_dir: '/tmp/job/output',
      log: 'BeamOn completed 250 events',
      errors: '',
    })

    expect(panel?.title).toBe('模拟结果')
    expect(panel?.metrics).toEqual([
      { label: '结果', value: '通过' },
      { label: '可视化 100', value: '通过' },
      { label: '生产批次', value: '250 个事件' },
      { label: '输出目录', value: '/tmp/job/output' },
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

    expect(panel?.title).toBe('报告产物')
    expect(panel?.metrics).toEqual([
      { label: '目标', value: '报告交付' },
      { label: '产物', value: '2' },
    ])
    expect(panel?.artifacts.map((artifact) => artifact.path)).toEqual([
      '/tmp/final_report.md',
      '/tmp/g4_summary.json',
    ])
  })

  it('does not model retired native visual workbench actions as operation panels', () => {
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

    expect(isOperationPanelView('workbench')).toBe(false)
    expect(isOperationPanelView('visual-review')).toBe(false)
    expect(isOperationPanelView('status')).toBe(false)
    expect(workbench).toBeNull()
    expect(review).toBeNull()
  })
})
