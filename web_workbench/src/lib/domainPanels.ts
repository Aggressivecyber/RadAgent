export type DomainMetric = {
  label: string
  value: string
}

export type DomainRow = {
  title: string
  status: string
  detail: string
  meta: string
}

export type DomainPanel = {
  title: string
  summary: string
  metrics: DomainMetric[]
  rows: DomainRow[]
}

const domainViews = new Set(['tools', 'credibility', 'memory'])

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown, fallback = ''): string {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

const statusLabels: Record<string, string> = {
  available: '可用',
  configured: '已配置',
  missing: '未配置',
  pass: '通过',
  fail: '失败',
  warning: '警告',
  unknown: '未知',
  default: '默认',
  gate: '门禁',
  artifact: '产物',
}

const phaseLabels: Record<string, string> = {
  idle: '待命',
  workspace: '准备工作区',
  context: '上下文整理',
  planning: '任务规划',
  requirements_review: '参数核对',
  requirements: '参数核对',
  g4_modeling: 'Geant4 建模',
  human_confirmation: '参数核对',
  coding: '工程编码',
  patch: '修订补丁',
  gates: '验证门禁',
  artifacts: '产物归档',
  report: '报告',
}

const levelLabels: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

function label(value: unknown, fallback = ''): string {
  const normalized = text(value, fallback)
  return statusLabels[normalized] || phaseLabels[normalized] || levelLabels[normalized] || normalized
}

function formatStatus(value: Record<string, unknown>): string {
  if (value.available === true) {
    return '可用'
  }
  if (value.configured === true) {
    return '已配置'
  }
  return '未配置'
}

export function isDomainPanelView(view: string): boolean {
  return domainViews.has(view)
}

export function createDomainPanel(view: string, data: unknown): DomainPanel | null {
  const row = asRecord(data)

  if (view === 'tools') {
    const tools = Object.values(asRecord(row.tools)).map(asRecord)
    const available = tools.filter((tool) => tool.available === true).length
    return {
      title: '本地运行环境',
      summary: text(row.workspace_root),
      metrics: [
        { label: '项目', value: label(row.project_slug, '默认') },
        { label: '工具', value: String(tools.length) },
        { label: '可用', value: String(available) },
      ],
      rows: tools.map((tool) => ({
        title: text(tool.label || tool.key, '工具'),
        status: formatStatus(tool),
        detail: text(tool.detail),
        meta: text(tool.path),
      })),
    }
  }

  if (view === 'credibility') {
    const warnings = asArray(row.warnings)
    return {
      title: '可信度审查',
      summary: text(row.message, '暂无可信度审查报告。'),
      metrics: [
        { label: '状态', value: label(row.status, '未知') },
        { label: '级别', value: label(row.credibility_level, '未知') },
        { label: '置信度', value: text(row.confidence, '') },
      ],
      rows: warnings.map((warning) => ({
        title: text(warning),
        status: '警告',
        detail: '',
        meta: '',
      })),
    }
  }

  if (view === 'memory') {
    const memory = asArray(row.memory).map(asRecord)
    return {
      title: '工作记忆',
      summary: memory.length ? '当前作业的近期工作记忆。' : '当前作业暂无工作记忆。',
      metrics: [
        { label: '作业', value: text(row.job_id, '无作业') },
        { label: '阶段', value: label(row.phase, '待命') },
        { label: '记忆', value: String(memory.length) },
      ],
      rows: memory.map((item) => ({
        title: text(item.key, '记忆'),
        status: label(item.source, '记忆'),
        detail: text(item.summary),
        meta: '',
      })),
    }
  }

  return null
}
