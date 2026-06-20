import type { HomeSummary, ShowcaseExample, WorkflowCapability } from './api'

export type MetricTile = {
  label: string
  labelEn: string
  value: string
}

export type ShowcaseCard = {
  id: string
  title: string
  subtitle: string
  prompt: string
  difficulty: string
  tags: string[]
  validationFocus: string[]
  deliverables: string[]
}

export type ToolUseItem = {
  index: string
  title: string
  titleEn: string
  body: string
  keyword: string
}

export type CapabilityShowcaseItem = {
  title: string
  titleEn: string
  body: string
  demoIndex: string
}

export type CapabilityShowcaseGroup = {
  title: string
  label: string
  body: string
  items: CapabilityShowcaseItem[]
}

export type AdvantageItem = {
  index: string
  title: string
  titleEn: string
  body: string
  proof: string
  demoIndex: string
}

export type NormalizedHomeSummary = {
  metrics: HomeSummary['metrics']
  metricTiles: MetricTile[]
  workflowCapabilities: WorkflowCapability[]
  showcaseCards: ShowcaseCard[]
  toolUseItems: ToolUseItem[]
  capabilityShowcases: CapabilityShowcaseGroup[]
  advantageItems: AdvantageItem[]
}

const fallbackWorkflowCapabilities: WorkflowCapability[] = [
  {
    name: '需求捕获 / Intent capture',
    description: '把一句仿真需求转成结构化目标。',
    command: '启动工作流',
  },
  {
    name: '物理模型 / Physics model IR',
    description: '持续记录几何、源项、计分和假设。',
    command: '模型记忆',
  },
  {
    name: '门禁审核 / Gate review',
    description: '在继续前展示验证门禁和建模前参数核对。',
    command: '审核门禁',
  },
  {
    name: '代码生成 / Code generation',
    description: '由模型生成 Geant4 源码、宏和工程文件。',
    command: '构建工程',
  },
  {
    name: '构建模拟 / Build and simulation',
    description: '编译生成代码并运行可控仿真批次。',
    command: '运行模拟',
  },
  {
    name: '产物修订 / Artifacts and revisions',
    description: '检查报告、源码、修订和最终交付物。',
    command: '查看产物',
  },
]

const fallbackShowcaseExamples: ShowcaseExample[] = [
  {
    id: 'example-hpge-coincidence',
    title: 'HPGe 反符合谱仪',
    subtitle: 'Anti-coincidence HPGe spectrometer',
    prompt:
      'Build a Geant4 workflow for an HPGe anti-coincidence gamma spectrometer: coaxial HPGe crystal, dead layer, BGO veto shield, 662 keV and 1332 keV gamma sources, energy-deposit scoring in crystal and veto, coincidence rejection logic, spectrum histogram, and a final report that explains geometry assumptions and gate criteria.',
    difficulty: 'advanced',
    tags: ['HPGe', 'anti-coincidence', 'spectrum'],
    validation_focus: ['geometry', 'coincidence scoring', 'report traceability'],
  },
  {
    id: 'example-proton-depth-dose',
    title: '质子束深度剂量',
    subtitle: 'Layered proton depth-dose benchmark',
    prompt:
      'Build a Geant4 proton depth-dose benchmark for a 150 MeV pencil beam through water, aluminum, and silicon layers. Produce range and Bragg peak scoring, per-layer energy deposition, step limiter settings, physics list rationale, CSV output, and validation gates for material thickness and scoring bin size.',
    difficulty: 'advanced',
    tags: ['proton', 'Bragg peak', 'dose'],
    validation_focus: ['materials', 'scoring bins', 'physics list'],
  },
  {
    id: 'example-neutron-shielding',
    title: '中子屏蔽响应',
    subtitle: 'Neutron shielding and activation proxy',
    prompt:
      'Build a Geant4 shielding study for 14 MeV neutrons through polyethylene, borated polyethylene, lead, and a downstream silicon detector. Score neutron leakage, secondary gamma production proxy, detector dose, material stack sensitivity, and produce a report with assumptions and limitations.',
    difficulty: 'expert',
    tags: ['neutron', 'shielding', 'secondary gamma'],
    validation_focus: ['hadronic physics', 'material stack', 'leakage scoring'],
  },
  {
    id: 'example-muon-tomography',
    title: '宇宙线缪子断层',
    subtitle: 'Cosmic muon scattering tomography',
    prompt:
      'Build a Geant4 cosmic muon scattering tomography workflow with two tracker planes above and below a dense object. Generate a realistic angular muon source, score hit positions, scattering angles, and reconstruction-ready CSV outputs, with gates for tracker spacing and material placement.',
    difficulty: 'expert',
    tags: ['muon', 'tomography', 'tracking'],
    validation_focus: ['source angular model', 'tracker geometry', 'CSV outputs'],
  },
]

const showcaseFocusById: Record<string, string[]> = {
  'example-hpge-coincidence': ['几何闭合检查', '反符合计分逻辑', '报告可追溯'],
  'example-proton-depth-dose': ['材料厚度核验', '剂量计分 bin', '物理列表选择'],
  'example-neutron-shielding': ['强子物理过程', '多层屏蔽堆栈', '泄漏通量计分'],
  'example-muon-tomography': ['角分布源项', '追踪器几何', 'CSV 重建数据'],
}

const showcaseDeliverablesById: Record<string, string[]> = {
  'example-hpge-coincidence': ['Geant4 工程', '能谱直方图', '门禁报告'],
  'example-proton-depth-dose': ['深度剂量 CSV', 'Bragg 峰定位', '材料验证记录'],
  'example-neutron-shielding': ['泄漏通量表', '屏蔽敏感性结果', '假设限制报告'],
  'example-muon-tomography': ['命中点 CSV', '散射角输出', '重建前数据包'],
}

const focusLabelMap: Record<string, string> = {
  geometry: '几何闭合检查',
  scoring: '计分逻辑检查',
  materials: '材料参数核验',
  'scoring bins': '计分 bin 检查',
  'physics list': '物理列表选择',
  'coincidence scoring': '反符合计分逻辑',
  'report traceability': '报告可追溯',
  'hadronic physics': '强子物理过程',
  'material stack': '多层材料堆栈',
  'leakage scoring': '泄漏通量计分',
  'source angular model': '角分布源项',
  'tracker geometry': '追踪器几何',
  'CSV outputs': 'CSV 输出契约',
}

const toolUseItems: ToolUseItem[] = [
  {
    index: '01',
    title: '任务转仿真链路',
    titleEn: 'Mission to workflow',
    body: '把空天辐照防护目标拆成粒子谱、轨道环境、屏蔽材料、探测器、剂量计分和验证门禁。',
    keyword: 'Mission',
  },
  {
    index: '02',
    title: 'Geant4 可信模型',
    titleEn: 'Geant4 Model IR',
    body: '持续维护 Geant4 模型 IR，记录几何、材料、源项、物理列表、假设、证据和未决参数。',
    keyword: 'Traceability',
  },
  {
    index: '03',
    title: '材料屏蔽检查',
    titleEn: 'Materials & geometry',
    body: '识别铝、硅、聚乙烯、含硼聚乙烯、铅等常见屏蔽材料，检测重叠、占位和不可追踪参数。',
    keyword: 'Validation',
  },
  {
    index: '04',
    title: '本地工程生成',
    titleEn: 'Codegen & build',
    body: '生成 Geant4 C++ 工程、宏文件和运行脚本，接入本地 Geant4 环境完成构建与修订。',
    keyword: 'Build',
  },
  {
    index: '05',
    title: '运行得到结果',
    titleEn: 'Simulation artifacts',
    body: '在本地运行事件批次，输出剂量、泄漏、能谱、CSV、日志、门禁结果和最终报告。',
    keyword: 'Artifacts',
  },
  {
    index: '06',
    title: '审查与修订',
    titleEn: 'Human gates',
    body: '对物理列表、材料参数、几何假设和关键选择发起确认，保留接受、拒绝和修订记录。',
    keyword: 'Review',
  },
]

const advantageItems: AdvantageItem[] = [
  {
    index: '01',
    title: '空天辐照防护',
    titleEn: 'Aerospace radiation shielding',
    body: '不是泛用代码生成器，而是面向航天器、电子器件和屏蔽结构的辐照防护仿真链路。',
    proof: '任务规划围绕粒子谱、屏蔽层、探测器和剂量计分展开。',
    demoIndex: '01',
  },
  {
    index: '02',
    title: 'Geant4 可信建模',
    titleEn: 'Geant4 traceable modeling',
    body: '基于 Geant4 物理算法和 Model IR 管理几何、材料、源项、物理列表和计分，减少传统手写模型遗漏。',
    proof: '模型 IR、schema gate、物理列表证据和未决问题会被持续记录，用证据链支撑高准确度结果。',
    demoIndex: '02',
  },
  {
    index: '03',
    title: '空间辐射源接入',
    titleEn: 'Space environment sources',
    body: '仓库内置 AP8/AE8 空间辐射环境封装，可把轨道辐射源转成 Geant4 可用输入。',
    proof: 'agent_core.space_radiation 负责 AP8/AE8 trapped-radiation source packaging。',
    demoIndex: '03',
  },
  {
    index: '04',
    title: '本地构建运行',
    titleEn: 'Local build and run',
    body: '接入本地 Geant4 环境后，系统可以生成工程、构建、运行模拟并直接得到输出结果。',
    proof: 'app service 和工具层暴露 build、simulation、artifacts、results 操作。',
    demoIndex: '04',
  },
  {
    index: '05',
    title: '多层验证门禁',
    titleEn: 'Validation gates',
    body: '相比传统脚本，RadAgent 会做 schema、几何、材料、构建、smoke、数据契约和物理审查门禁。',
    proof: 'README 明确包含 runtime auditing、physics review、build/smoke/data-contract gates。',
    demoIndex: '05',
  },
  {
    index: '06',
    title: '产物可复查',
    titleEn: 'Reviewable artifacts',
    body: '每次任务都沉淀源码、宏文件、日志、CSV、报告、门禁结果和 SQLite 工作区记录，便于复现实验。',
    proof: 'simulation_workspace 保存阶段目录、artifact indexes、events、snapshots 和 reports。',
    demoIndex: '06',
  },
]

const capabilityShowcases: CapabilityShowcaseGroup[] = [
  {
    title: '防护建模',
    label: 'Shielding model',
    body: '从任务目标开始，建立空天辐照防护的几何、材料、源项和计分结构，让模型从第一步就可追踪。',
    items: [
      {
        title: '任务拆解',
        titleEn: 'Mission routing',
        body: '把防护目标拆成粒子谱、能量、屏蔽层、器件结构、计分和门禁。',
        demoIndex: '01',
      },
      {
        title: '模型证据',
        titleEn: 'Model evidence',
        body: '用 Geant4 Model IR 记录几何、材料、源项、物理列表、假设和证据。',
        demoIndex: '02',
      },
      {
        title: '参数确认',
        titleEn: 'Human gates',
        body: '对物理列表、材料参数、屏蔽厚度和关键假设发起确认。',
        demoIndex: '06',
      },
    ],
  },
  {
    title: '仿真交付',
    label: 'Simulation delivery',
    body: '模型稳定后，Agent 推进材料几何检查、Geant4 工程生成、本地运行和结果归档。',
    items: [
      {
        title: '材料屏蔽',
        titleEn: 'Materials & geometry',
        body: '识别常见屏蔽材料，检测几何重叠、占位和不可追踪参数。',
        demoIndex: '03',
      },
      {
        title: '本地构建',
        titleEn: 'Codegen & build',
        body: '生成 Geant4 工程、宏文件和运行脚本，接入本地环境构建。',
        demoIndex: '04',
      },
      {
        title: '结果归档',
        titleEn: 'Artifacts',
        body: '运行事件批次，归档剂量、泄漏、谱图、CSV、日志和报告。',
        demoIndex: '05',
      },
    ],
  },
]

function normalizeValidationFocus(example: ShowcaseExample): string[] {
  const knownFocus = showcaseFocusById[example.id]
  if (knownFocus) {
    return knownFocus
  }

  const translated = example.validation_focus
    .map((focus) => focusLabelMap[focus] ?? focus)
    .filter((focus) => focus.trim().length > 0)

  return translated.length > 0 ? translated : ['模型一致性检查', '结果可复查']
}

function normalizeDeliverables(example: ShowcaseExample): string[] {
  return showcaseDeliverablesById[example.id] ?? ['Geant4 工程', '运行日志', '验证报告']
}

function normalizeShowcaseExample(example: ShowcaseExample): ShowcaseCard {
  return {
    id: example.id,
    title: example.title,
    subtitle: example.subtitle,
    prompt: example.prompt,
    difficulty: example.difficulty,
    tags: example.tags,
    validationFocus: normalizeValidationFocus(example),
    deliverables: normalizeDeliverables(example),
  }
}

export function normalizeHomeSummary(summary: HomeSummary): NormalizedHomeSummary {
  const metricTiles: MetricTile[] = [
    { label: '项目', labelEn: 'Projects', value: String(summary.metrics.projects) },
    { label: '完成', labelEn: 'Completed', value: String(summary.metrics.completed_jobs) },
    { label: '产物', labelEn: 'Artifacts', value: String(summary.metrics.artifacts) },
    { label: '活动', labelEn: 'Active', value: String(summary.metrics.active_jobs) },
  ]

  return {
    metrics: summary.metrics,
    metricTiles,
    workflowCapabilities:
      summary.workflow_capabilities.length > 0
        ? summary.workflow_capabilities
        : fallbackWorkflowCapabilities,
    showcaseCards: (summary.showcase_examples.length > 0
      ? summary.showcase_examples
      : fallbackShowcaseExamples
    ).map(normalizeShowcaseExample),
    toolUseItems,
    capabilityShowcases,
    advantageItems,
  }
}
