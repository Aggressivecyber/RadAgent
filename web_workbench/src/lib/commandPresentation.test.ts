import { describe, expect, it } from 'vitest'
import { commandGroupPresentation, commandPresentation } from './commandPresentation'

describe('command presentation', () => {
  it('turns internal commands into Chinese-first web actions without exposing slash text', () => {
    const action = commandPresentation({
      name: 'run',
      description: 'Start workflow',
      tip: 'Start a real RadAgent workflow from a simulation request.',
      module: 'workflow/start_job',
      connection: 'service',
      visible: true,
    })

    expect(action.primary).toBe('开始工作流')
    expect(action.secondary).toBe('Run workflow')
    expect(action.tip).toContain('仿真')
    expect(action.internalCommand).toBe('/run')
    expect(action.displayCommand).toBeUndefined()
  })

  it('keeps useful fallback labels and tips for commands outside the curated map', () => {
    const action = commandPresentation({
      name: 'custom-tool',
      description: 'Open a custom service panel',
      visible: true,
    })

    expect(action.primary).toBe('Open a custom service panel')
    expect(action.secondary).toBe('custom tool')
    expect(action.tip).toBe('Open a custom service panel')
    expect(action.internalCommand).toBe('/custom-tool')
  })

  it('presents workflow diagnosis as an explanatory review action', () => {
    const action = commandPresentation({
      name: 'diagnose',
      description: 'Explain current workflow block',
      tip: 'Use a lite model to explain the current block while hard workflow rules remain authoritative.',
      module: 'workflow/diagnosis',
      connection: 'service',
      visible: true,
    })

    expect(action.primary).toBe('诊断阻塞')
    expect(action.secondary).toBe('Diagnose')
    expect(action.tip).toContain('失败或等待')
    expect(action.internalCommand).toBe('/diagnose')
  })

  it('presents retry as a current-stage action', () => {
    const action = commandPresentation({
      name: 'retry',
      description: 'Retry current stage',
      module: 'job_control',
      connection: 'service',
      visible: true,
    })

    expect(action.primary).toBe('重试阶段')
    expect(action.secondary).toBe('Retry stage')
    expect(action.tip).toContain('当前作业')
    expect(action.internalCommand).toBe('/retry')
  })

  it('localizes command groups for the web command picker', () => {
    expect(commandGroupPresentation('Workflow')).toEqual({
      primary: '工作流',
      secondary: 'Workflow',
    })
    expect(commandGroupPresentation('System')).toEqual({
      primary: '系统',
      secondary: 'System',
    })
  })
})
