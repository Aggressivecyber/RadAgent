import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { buildSimulationPresetPrompt, createSimulationPresetSummary } from '../lib/simulationPresets'
import PresetTaskPreview from './PresetTaskPreview'

describe('PresetTaskPreview', () => {
  it('renders the same full prompt that will be sent to the agent', () => {
    const selection = {
      template: 'device-tid',
      source: 'trapped-radiation',
      material: 'al-poly',
    }
    const prompt = buildSimulationPresetPrompt(selection, '重点评估 2 mm Al 外壳下游硅探测器剂量')
    const summary = createSimulationPresetSummary(selection, '重点评估 2 mm Al 外壳下游硅探测器剂量')
    const markup = renderToStaticMarkup(<PresetTaskPreview summary={summary} fullPrompt={prompt} />)

    expect(markup).toContain('Agent 将执行')
    expect(markup).toContain('完整任务描述')
    expect(markup).toContain('空天辐照防护仿真任务')
    expect(markup).toContain('基于 Geant4')
    expect(markup).toContain('重点评估 2 mm Al 外壳下游硅探测器剂量')
    expect(markup).toContain('几何闭合')
    expect(markup).toContain('验证报告')
  })
})
