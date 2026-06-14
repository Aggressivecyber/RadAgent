export type SimulationPresetKind = 'template' | 'source' | 'material'

export type SimulationPresetOption = {
  id: string
  label: string
  labelEn: string
  description: string
  prompt: string
}

export type SimulationPresetGroup = {
  kind: SimulationPresetKind
  label: string
  labelEn: string
  options: SimulationPresetOption[]
}

export type SimulationPresetSelection = {
  template: string
  source: string
  material: string
}

export type SimulationPresetSummary = {
  title: string
  detail: string
  rows: Array<{ label: string; value: string }>
  gates: string[]
  deliverables: string[]
}

export const simulationPresetGroups: SimulationPresetGroup[] = [
  {
    kind: 'template',
    label: '任务模板',
    labelEn: 'Scenario',
    options: [
      {
        id: 'device-tid',
        label: '器件总剂量',
        labelEn: 'Device TID',
        description: '评估器件、探测器或芯片屏蔽后的能量沉积和剂量。',
        prompt: '建立器件总剂量 TID 仿真，包含硅敏感体、屏蔽结构、能量沉积计分和剂量换算。',
      },
      {
        id: 'shielding-stack',
        label: '屏蔽层优化',
        labelEn: 'Shielding stack',
        description: '比较多层材料屏蔽后的泄漏通量、剂量和二次粒子影响。',
        prompt: '建立多层屏蔽优化仿真，比较不同材料厚度下的泄漏通量、剂量和二次粒子响应。',
      },
      {
        id: 'detector-spectrum',
        label: '探测器能谱',
        labelEn: 'Detector spectrum',
        description: '生成探测器能谱、反符合逻辑和报告可追溯证据。',
        prompt: '建立探测器能谱仿真，输出能量沉积谱、计分逻辑、反符合条件和可追溯报告。',
      },
    ],
  },
  {
    kind: 'source',
    label: '粒子源',
    labelEn: 'Source',
    options: [
      {
        id: 'trapped-radiation',
        label: 'AP8/AE8 轨道粒子',
        labelEn: 'Trapped orbit',
        description: '适合轨道电子、质子环境到 Geant4 源项的封装。',
        prompt: '使用 AP8/AE8 轨道辐射环境作为源项，区分电子和质子能谱并记录轨道环境假设。',
      },
      {
        id: 'solar-proton',
        label: '太阳质子事件',
        labelEn: 'Solar proton',
        description: '适合高能质子穿透屏蔽和 Bragg 峰剂量验证。',
        prompt: '使用太阳质子事件 SPE 源项，设置质子能谱、入射方向和深度剂量计分。',
      },
      {
        id: 'gamma-line',
        label: '伽马线源',
        labelEn: 'Gamma lines',
        description: '适合谱仪响应、能量沉积谱和反符合门禁。',
        prompt: '使用 662 keV 与 1332 keV 伽马线源，输出探测器能量沉积谱和峰区响应。',
      },
    ],
  },
  {
    kind: 'material',
    label: '屏蔽材料',
    labelEn: 'Shielding',
    options: [
      {
        id: 'al-poly',
        label: '铝 + 聚乙烯',
        labelEn: 'Al + PE',
        description: '航天器外壳和轻质富氢屏蔽的常见组合。',
        prompt: '采用铝外壳与聚乙烯富氢屏蔽组合，检查厚度、密度、几何重叠和材料定义。',
      },
      {
        id: 'si-al',
        label: '硅 + 铝壳',
        labelEn: 'Si + Al',
        description: '适合器件敏感体、封装和外壳剂量评估。',
        prompt: '采用硅敏感体、器件封装和铝壳结构，输出敏感体能量沉积与剂量结果。',
      },
      {
        id: 'bpe-lead',
        label: '含硼聚乙烯 + 铅',
        labelEn: 'BPE + Pb',
        description: '适合中子屏蔽、二次伽马代理和材料堆栈比较。',
        prompt: '采用含硼聚乙烯和铅组合，评估中子泄漏、二次伽马代理和下游探测器剂量。',
      },
    ],
  },
]

export const defaultSimulationPresetSelection: SimulationPresetSelection = {
  template: 'device-tid',
  source: 'trapped-radiation',
  material: 'al-poly',
}

function optionFor(kind: SimulationPresetKind, id: string): SimulationPresetOption {
  const group = simulationPresetGroups.find((item) => item.kind === kind)
  const fallback = group?.options[0]
  const selected = group?.options.find((option) => option.id === id)
  if (!selected && !fallback) {
    throw new Error(`Missing simulation preset group: ${kind}`)
  }
  return selected || fallback!
}

export function buildSimulationPresetPrompt(selection: SimulationPresetSelection, userRequest: string): string {
  const template = optionFor('template', selection.template)
  const source = optionFor('source', selection.source)
  const material = optionFor('material', selection.material)
  const detail = userRequest.trim()

  return [
    '空天辐照防护仿真任务：基于 Geant4 建立可构建、可运行、可审查的工作流。',
    `任务模板：${template.label}。${template.prompt}`,
    `粒子源：${source.label}。${source.prompt}`,
    `屏蔽材料：${material.label}。${material.prompt}`,
    '请生成几何、材料、源项、物理列表、计分、构建脚本、运行宏、验证门禁和最终结果报告。',
    detail ? `补充要求：${detail}` : '补充要求：优先保证几何闭合、材料参数、计分 bin 和报告可追溯。',
  ].join(' ')
}

export function createSimulationPresetSummary(
  selection: SimulationPresetSelection,
  userRequest: string,
): SimulationPresetSummary {
  const template = optionFor('template', selection.template)
  const source = optionFor('source', selection.source)
  const material = optionFor('material', selection.material)
  const detail = userRequest.trim() || '优先保证几何闭合、材料参数、计分 bin 和报告可追溯。'

  return {
    title: `${template.label} · ${source.label} · ${material.label}`,
    detail,
    rows: [
      { label: '任务', value: template.label },
      { label: '源项', value: source.label },
      { label: '材料', value: material.label },
    ],
    gates: ['几何闭合', '材料厚度', '计分契约'],
    deliverables: ['Geant4 工程', '运行宏', '验证报告'],
  }
}
