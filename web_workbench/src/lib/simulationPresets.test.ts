import { describe, expect, it } from 'vitest'
import {
  buildSimulationPresetPrompt,
  createSimulationPresetSummary,
  defaultSimulationPresetSelection,
  simulationPresetGroups,
} from './simulationPresets'

describe('simulation presets', () => {
  it('defines aerospace radiation choices for task, source and shielding material', () => {
    expect(simulationPresetGroups.map((group) => group.label)).toEqual(['任务模板', '粒子源', '屏蔽材料'])
    expect(simulationPresetGroups[0].options.map((option) => option.label)).toContain('器件总剂量')
    expect(simulationPresetGroups[1].options.map((option) => option.label)).toContain('AP8/AE8 轨道粒子')
    expect(simulationPresetGroups[2].options.map((option) => option.label)).toContain('铝 + 聚乙烯')
  })

  it('builds a Geant4 prompt from selected controls and free-form user request', () => {
    const prompt = buildSimulationPresetPrompt(
      {
        template: 'device-tid',
        source: 'trapped-radiation',
        material: 'al-poly',
      },
      '重点评估 2 mm Al 外壳下游硅探测器剂量',
    )

    expect(prompt).toContain('空天辐照防护仿真任务')
    expect(prompt).toContain('器件总剂量')
    expect(prompt).toContain('AP8/AE8 轨道粒子')
    expect(prompt).toContain('铝 + 聚乙烯')
    expect(prompt).toContain('Geant4')
    expect(prompt).toContain('重点评估 2 mm Al 外壳下游硅探测器剂量')
  })

  it('falls back to a complete default selection when ids are missing', () => {
    const prompt = buildSimulationPresetPrompt(
      {
        ...defaultSimulationPresetSelection,
        source: 'missing',
      },
      '',
    )

    expect(prompt).toContain('器件总剂量')
    expect(prompt).toContain('AP8/AE8 轨道粒子')
    expect(prompt).toContain('铝 + 聚乙烯')
    expect(prompt).not.toContain('undefined')
  })

  it('creates a reviewable summary for the workbench before launch', () => {
    const summary = createSimulationPresetSummary(
      {
        template: 'shielding-stack',
        source: 'solar-proton',
        material: 'bpe-lead',
      },
      '比较 5 cm 与 10 cm 屏蔽层',
    )

    expect(summary.title).toBe('屏蔽层优化 · 太阳质子事件 · 含硼聚乙烯 + 铅')
    expect(summary.rows).toEqual([
      { label: '任务', value: '屏蔽层优化' },
      { label: '源项', value: '太阳质子事件' },
      { label: '材料', value: '含硼聚乙烯 + 铅' },
    ])
    expect(summary.gates).toEqual(['几何闭合', '材料厚度', '计分契约'])
    expect(summary.deliverables).toEqual(['Geant4 工程', '运行宏', '验证报告'])
    expect(summary.detail).toContain('比较 5 cm 与 10 cm 屏蔽层')
  })
})
