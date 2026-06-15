export type OperationMetric = {
  label: string
  value: string
}

export type OperationArtifact = {
  path: string
  kind: string
  stage: string
}

export type OperationPanel = {
  title: string
  summary: string
  metrics: OperationMetric[]
  preview: string
  artifacts: OperationArtifact[]
}

const operationViews = new Set([
  'build',
  'simulation',
  'report',
  'demo',
  'mode',
  'history',
  'exit',
])

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

function passFail(value: unknown): string {
  return value === true ? '通过' : '失败'
}

function returnCodeStatus(value: unknown): string {
  const row = asRecord(value)
  if (!('returncode' in row)) {
    return '未运行'
  }
  return Number(row.returncode) === 0 ? '通过' : '失败'
}

function targetLabel(value: unknown, fallback: string): string {
  const raw = text(value, fallback)
  const labels: Record<string, string> = {
    report: '报告交付',
    artifacts: '产物列表',
    artifact: '产物',
  }
  return labels[raw] || raw
}

function artifactRows(value: unknown): OperationArtifact[] {
  return asArray(value).map((item) => {
    const row = asRecord(item)
    return {
      path: text(row.path, 'unknown artifact'),
      kind: text(row.kind, 'artifact'),
      stage: text(row.stage),
    }
  })
}

export function isOperationPanelView(view: string): boolean {
  return operationViews.has(view)
}

export function createOperationPanel(view: string, data: unknown): OperationPanel | null {
  const row = asRecord(data)

  if (view === 'build') {
    const executable = text(row.executable_path, '不可用')
    return {
      title: '构建结果',
      summary: text(row.errors, row.success === true ? '构建已完成。' : '构建失败。'),
      metrics: [
        { label: '结果', value: passFail(row.success) },
        { label: '配置', value: returnCodeStatus(row.configure) },
        { label: '构建', value: returnCodeStatus(row.build) },
        { label: '可执行文件', value: executable },
      ],
      preview: text(row.errors),
      artifacts: [],
    }
  }

  if (view === 'simulation') {
    const events = text(row.events)
    const visualEvents = text(row.visual_events, '100')
    return {
      title: '模拟结果',
      summary: text(row.errors, row.success === true ? '模拟已完成。' : '模拟失败。'),
      metrics: [
        { label: '结果', value: passFail(row.success) },
        { label: `可视化 ${visualEvents}`, value: passFail(row.visual_success) },
        { label: '生产批次', value: events ? `${events} 个事件` : passFail(row.production_success) },
        { label: '输出目录', value: text(row.output_dir, '不可用') },
      ],
      preview: text(row.errors || row.log),
      artifacts: [],
    }
  }

  if (view === 'report' || view === 'artifacts') {
    const artifacts = artifactRows(row.artifacts)
    return {
      title: view === 'report' ? '报告产物' : '产物选择',
      summary: artifacts.length ? `${artifacts.length} 个产物可用。` : '暂无可用产物。',
      metrics: [
        { label: '目标', value: targetLabel(row.target, view) },
        { label: '产物', value: String(artifacts.length) },
      ],
      preview: '',
      artifacts,
    }
  }

  if (view === 'demo') {
    return {
      title: '示例模板',
      summary: text(row.message, '生产工作流建议使用明确的运行需求。'),
      metrics: [{ label: '示例', value: text(row.demo, '未知') }],
      preview: text(row.command),
      artifacts: [],
    }
  }

  if (view === 'mode') {
    return {
      title: '输入模式',
      summary: '网页工作台会保留结构化输入控件。',
      metrics: [{ label: '模式', value: text(row.mode, '询问') }],
      preview: '',
      artifacts: [],
    }
  }

  if (view === 'history' || view === 'exit') {
    return {
      title: view === 'history' ? '历史记录' : '退出工作台',
      summary: text(row.message),
      metrics: [],
      preview: '',
      artifacts: [],
    }
  }

  return null
}
