export type CollectionRow = {
  title: string
  status: string
  detail: string
  meta: string
  record: Record<string, unknown>
}

export type CollectionPanel = {
  title: string
  summary: string
  rows: CollectionRow[]
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function text(value: unknown, fallback = ''): string {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

const statusLabels: Record<string, string> = {
  completed: '已完成',
  running: '运行中',
  failed: '失败',
  pending: '等待中',
  blocked: '已阻塞',
  pass: '通过',
  fail: '失败',
  warning: '警告',
  ready: '就绪',
  generated: '已生成',
  applied: '已应用',
  default: '默认',
  project: '项目',
  artifact: '产物',
  report: '报告',
}

const phaseLabels: Record<string, string> = {
  workspace: '准备工作区',
  context: '上下文整理',
  planning: '任务规划',
  g4_modeling: 'Geant4 建模',
  human_confirmation: '人工确认',
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

function basename(path: string): string {
  return path.split('/').filter(Boolean).at(-1) || path
}

function bytes(value: unknown): string {
  const size = Number(value || 0)
  if (!Number.isFinite(size) || size <= 0) {
    return ''
  }
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024)} KB`
  }
  return `${Math.round(size / (1024 * 1024))} MB`
}

function plural(count: number, singular: string): string {
  return `${count} 个${singular}`
}

function compact(parts: string[]): string {
  return parts.filter(Boolean).join(' · ')
}

function rowFor(view: string, item: unknown, index: number): CollectionRow {
  const record = asRecord(item)

  if (view === 'jobs') {
    return {
      title: text(record.user_query || record.job_id, `Job ${index + 1}`),
      status: label(record.status, '未知'),
      detail: compact([
        label(record.current_phase || record.phase),
        text(record.project_name || record.project_slug),
      ]),
      meta: text(record.job_id),
      record,
    }
  }

  if (view === 'artifacts') {
    const path = text(record.path, `Artifact ${index + 1}`)
    return {
      title: basename(path),
      status: label(record.kind || record.stage, '产物'),
      detail: compact([label(record.stage), bytes(record.size_bytes)]),
      meta: path,
      record,
    }
  }

  if (view === 'gates') {
    const gateId = text(record.gate_id ?? record.id, String(index + 1))
    return {
      title: `门禁 ${gateId}`,
      status: label(record.status, '未知'),
      detail: text(record.message || record.summary || record.reason),
      meta: label(record.credibility_level || record.level || record.phase),
      record,
    }
  }

  if (view === 'revisions') {
    return {
      title: text(record.revision_id, `Revision ${index + 1}`),
      status: label(record.status, '未知'),
      detail: text(record.user_request || record.summary),
      meta: label(record.patch_status || record.candidate_project_dir),
      record,
    }
  }

  if (view === 'projects') {
    return {
      title: text(record.name || record.slug, `Project ${index + 1}`),
      status: label(record.slug, '项目'),
      detail: text(record.description),
      meta: text(record.root_path || record.last_opened_at),
      record,
    }
  }

  return {
    title: text(
      record.job_id ?? record.path ?? record.slug ?? record.revision_id ?? record.gate_id,
      `Record ${index + 1}`,
    ),
    status: label(record.status ?? record.kind ?? record.name ?? record.stage),
    detail: '',
    meta: '',
    record,
  }
}

export function createCollectionPanel(view: string, data: unknown): CollectionPanel | null {
  if (!Array.isArray(data)) {
    return null
  }

  const labels: Record<string, string> = {
    jobs: '作业列表',
    artifacts: '产物列表',
    gates: '验证门禁',
    projects: '项目列表',
    revisions: '修订记录',
  }
  const nouns: Record<string, string> = {
    jobs: '作业',
    artifacts: '产物',
    gates: '门禁',
    projects: '项目',
    revisions: '修订',
  }
  const title = labels[view] || '记录'
  const noun = nouns[view] || '记录'

  return {
    title,
    summary: plural(data.length, noun),
    rows: data.map((item, index) => rowFor(view, item, index)),
  }
}
