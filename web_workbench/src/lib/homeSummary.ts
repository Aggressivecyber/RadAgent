import type { HomeSummary, ShowcaseExample, WorkflowCapability } from './api'

export type MetricTile = {
  label: string
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
}

export type NormalizedHomeSummary = {
  metrics: HomeSummary['metrics']
  metricTiles: MetricTile[]
  workflowCapabilities: WorkflowCapability[]
  showcaseCards: ShowcaseCard[]
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
    description: '在继续前展示验证门禁和人工确认。',
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

function normalizeShowcaseExample(example: ShowcaseExample): ShowcaseCard {
  return {
    id: example.id,
    title: example.title,
    subtitle: example.subtitle,
    prompt: example.prompt,
    difficulty: example.difficulty,
    tags: example.tags,
    validationFocus: example.validation_focus,
  }
}

export function normalizeHomeSummary(summary: HomeSummary): NormalizedHomeSummary {
  const metricTiles: MetricTile[] = [
    { label: '项目 Projects', value: String(summary.metrics.projects) },
    { label: '完成 Completed', value: String(summary.metrics.completed_jobs) },
    { label: '产物 Artifacts', value: String(summary.metrics.artifacts) },
    { label: '活动 Active', value: String(summary.metrics.active_jobs) },
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
  }
}
