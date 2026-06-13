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

function formatStatus(value: Record<string, unknown>): string {
  if (value.available === true) {
    return 'available'
  }
  if (value.configured === true) {
    return 'configured'
  }
  return 'missing'
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
      title: 'Runtime tools',
      summary: text(row.workspace_root),
      metrics: [
        { label: 'Project', value: text(row.project_slug, 'default') },
        { label: 'Tools', value: String(tools.length) },
        { label: 'Available', value: String(available) },
      ],
      rows: tools.map((tool) => ({
        title: text(tool.label || tool.key, 'Tool'),
        status: formatStatus(tool),
        detail: text(tool.detail),
        meta: text(tool.path),
      })),
    }
  }

  if (view === 'credibility') {
    const warnings = asArray(row.warnings)
    return {
      title: 'Credibility',
      summary: text(row.message, 'No credibility report is available.'),
      metrics: [
        { label: 'Status', value: text(row.status, 'unknown') },
        { label: 'Level', value: text(row.credibility_level, 'unknown') },
        { label: 'Confidence', value: text(row.confidence, '') },
      ],
      rows: warnings.map((warning) => ({
        title: text(warning),
        status: 'warning',
        detail: '',
        meta: '',
      })),
    }
  }

  if (view === 'memory') {
    const memory = asArray(row.memory).map(asRecord)
    return {
      title: 'Workflow memory',
      summary: memory.length ? 'Recent workflow memory for the active job.' : 'No workflow memory for the active job.',
      metrics: [
        { label: 'Job', value: text(row.job_id, 'no-job') },
        { label: 'Phase', value: text(row.phase, 'idle') },
        { label: 'Memory', value: String(memory.length) },
      ],
      rows: memory.map((item) => ({
        title: text(item.key, 'memory'),
        status: text(item.source, 'memory'),
        detail: text(item.summary),
        meta: '',
      })),
    }
  }

  return null
}
