export type DetailMetric = {
  label: string
  value: string
}

export type DetailField = {
  label: string
  value: string
}

export type DetailSection = {
  title: string
  rows: DetailField[]
}

export type DetailAction = {
  label: string
  labelEn: string
  command: string
  intent: 'primary' | 'neutral'
}

export type DetailPanel = {
  title: string
  status: string
  subtitle: string
  metrics: DetailMetric[]
  sections: DetailSection[]
  preview: string
  actions: DetailAction[]
}

const detailViews = new Set(['job', 'gate', 'revision', 'project'])

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

function fields(rows: DetailField[]): DetailField[] {
  return rows.filter((row) => row.value)
}

function titleFromTask(value: unknown): string {
  const task = asRecord(value)
  return text(task.en || task.zh)
}

const phaseLabels: Record<string, string> = {
  prepare_workspace: '准备工作区',
  context: '上下文收集',
  task_planning: '任务规划',
  requirements_review: '参数核对',
  g4_modeling: 'Geant4 建模',
  human_confirmation: '人工确认',
  g4_codegen: '工程生成',
  patch: '修订补丁',
  gate: '验证门禁',
  validation: '验证门禁',
  artifact: '产物归档',
  report: '报告交付',
}

const statusLabels: Record<string, string> = {
  paused: '暂停审查',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  pass: '通过',
  passed: '通过',
  ready: '就绪',
  generated: '已生成',
  project: '项目',
  default: '默认',
  unknown: '未知',
}

const levelLabels: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  unknown: '未知',
}

function phaseLabel(value: unknown, fallback = '准备工作区'): string {
  const raw = text(value, fallback)
  return phaseLabels[raw] || raw
}

function statusLabel(value: unknown, fallback = '未知'): string {
  const raw = text(value, fallback)
  return statusLabels[raw] || raw
}

function levelLabel(value: unknown): string {
  const raw = text(value, 'unknown')
  return levelLabels[raw] || raw
}

function phaseCount(count: number): string {
  return `${count} 个阶段`
}

export function isDetailPanelView(view: string): boolean {
  return detailViews.has(view)
}

export function createDetailPanel(view: string, data: unknown): DetailPanel | null {
  const row = asRecord(data)

  if (view === 'job') {
    const completed = asArray(row.completed_phases).length
    const title = text(row.user_query || row.objective || row.summary || titleFromTask(row.task_summary), text(row.job_id, 'Job'))
    return {
      title,
      status: statusLabel(row.status),
      subtitle: text(row.job_id),
      metrics: [
        { label: '阶段', value: phaseLabel(row.current_phase || row.phase) },
        { label: '项目', value: text(row.project_name || row.project_slug, '默认') },
        { label: '已完成', value: phaseCount(completed) },
      ],
      sections: [
        {
          title: '工作流',
          rows: fields([
            { label: '作业 ID', value: text(row.job_id) },
            { label: '运行模式', value: text(row.run_mode || row.execution_mode) },
            { label: '工作区', value: text(row.workspace_root || row.project_dir) },
            { label: '创建时间', value: text(row.created_at) },
            { label: '更新时间', value: text(row.updated_at || row.completed_at) },
          ]),
        },
      ],
      preview: text(row.user_query || row.objective || row.summary),
      actions: text(row.job_id)
        ? [
            {
              label: '切换到工作区',
              labelEn: 'Switch workspace',
              command: `/resume ${text(row.job_id)}`,
              intent: 'neutral',
            },
            {
              label: '继续运行',
              labelEn: 'Continue run',
              command: `/retry ${text(row.job_id)}`,
              intent: 'primary',
            },
          ]
        : [],
    }
  }

  if (view === 'gate') {
    const gateId = text(row.gate_id ?? row.id, 'selected')
    return {
      title: `门禁 ${gateId}`,
      status: statusLabel(row.status),
      subtitle: phaseLabel(row.phase || row.credibility_level || row.level, '未知'),
      metrics: [
        { label: '级别', value: levelLabel(row.credibility_level || row.level) },
        { label: '阶段', value: phaseLabel(row.phase, '未知') },
      ],
      sections: [
        {
          title: '审查决定',
          rows: fields([
            { label: '门禁 ID', value: gateId },
            { label: '原因', value: text(row.reason) },
            { label: '证据', value: text(row.evidence) },
          ]),
        },
      ],
      preview: text(row.message || row.summary || row.reason),
      actions: [],
    }
  }

  if (view === 'revision') {
    const request = text(row.user_request || row.summary)
    return {
      title: text(row.revision_id, 'Revision'),
      status: statusLabel(row.status || row.patch_status),
      subtitle: request,
      metrics: [
        { label: '补丁', value: statusLabel(row.patch_status) },
        { label: '作业', value: text(row.job_id, '当前') },
      ],
      sections: [
        {
          title: '修订',
          rows: fields([
            { label: '修订 ID', value: text(row.revision_id) },
            { label: '请求', value: request },
            { label: '候选目录', value: text(row.candidate_project_dir) },
            { label: '创建时间', value: text(row.created_at) },
          ]),
        },
      ],
      preview: request,
      actions: [],
    }
  }

  if (view === 'project') {
    const root = text(row.root_path || row.workspace_root)
    return {
      title: text(row.name || row.slug, 'Project'),
      status: statusLabel(row.slug, '项目'),
      subtitle: root,
      metrics: [
        { label: '标识', value: text(row.slug, '项目') },
        { label: '作业数', value: text(row.job_count || row.jobs, '0') },
      ],
      sections: [
        {
          title: '工作区',
          rows: fields([
            { label: '根目录', value: root },
            { label: '描述', value: text(row.description) },
            { label: '最近打开', value: text(row.last_opened_at) },
          ]),
        },
      ],
      preview: text(row.description),
      actions: [],
    }
  }

  return null
}
