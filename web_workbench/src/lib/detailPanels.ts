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

export type DetailPanel = {
  title: string
  status: string
  subtitle: string
  metrics: DetailMetric[]
  sections: DetailSection[]
  preview: string
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

function plural(count: number, singular: string): string {
  return `${count} ${singular}${count === 1 ? '' : 's'}`
}

function fields(rows: DetailField[]): DetailField[] {
  return rows.filter((row) => row.value)
}

function titleFromTask(value: unknown): string {
  const task = asRecord(value)
  return text(task.en || task.zh)
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
      status: text(row.status, 'unknown'),
      subtitle: text(row.job_id),
      metrics: [
        { label: 'Phase', value: text(row.current_phase || row.phase, 'idle') },
        { label: 'Project', value: text(row.project_name || row.project_slug, 'default') },
        { label: 'Completed', value: plural(completed, 'phase') },
      ],
      sections: [
        {
          title: 'Workflow',
          rows: fields([
            { label: 'Job ID', value: text(row.job_id) },
            { label: 'Run mode', value: text(row.run_mode || row.execution_mode) },
            { label: 'Workspace', value: text(row.workspace_root || row.project_dir) },
            { label: 'Created', value: text(row.created_at) },
            { label: 'Updated', value: text(row.updated_at || row.completed_at) },
          ]),
        },
      ],
      preview: text(row.user_query || row.objective || row.summary),
    }
  }

  if (view === 'gate') {
    const gateId = text(row.gate_id ?? row.id, 'selected')
    return {
      title: `Gate ${gateId}`,
      status: text(row.status, 'unknown'),
      subtitle: text(row.phase || row.credibility_level || row.level),
      metrics: [
        { label: 'Level', value: text(row.credibility_level || row.level, 'unknown') },
        { label: 'Phase', value: text(row.phase, 'unknown') },
      ],
      sections: [
        {
          title: 'Decision',
          rows: fields([
            { label: 'Gate ID', value: gateId },
            { label: 'Reason', value: text(row.reason) },
            { label: 'Evidence', value: text(row.evidence) },
          ]),
        },
      ],
      preview: text(row.message || row.summary || row.reason),
    }
  }

  if (view === 'revision') {
    const request = text(row.user_request || row.summary)
    return {
      title: text(row.revision_id, 'Revision'),
      status: text(row.status || row.patch_status, 'unknown'),
      subtitle: request,
      metrics: [
        { label: 'Patch', value: text(row.patch_status, 'unknown') },
        { label: 'Job', value: text(row.job_id, 'active') },
      ],
      sections: [
        {
          title: 'Revision',
          rows: fields([
            { label: 'Revision ID', value: text(row.revision_id) },
            { label: 'Request', value: request },
            { label: 'Candidate', value: text(row.candidate_project_dir) },
            { label: 'Created', value: text(row.created_at) },
          ]),
        },
      ],
      preview: request,
    }
  }

  if (view === 'project') {
    const root = text(row.root_path || row.workspace_root)
    return {
      title: text(row.name || row.slug, 'Project'),
      status: text(row.slug, 'project'),
      subtitle: root,
      metrics: [
        { label: 'Slug', value: text(row.slug, 'project') },
        { label: 'Jobs', value: text(row.job_count || row.jobs, '0') },
      ],
      sections: [
        {
          title: 'Workspace',
          rows: fields([
            { label: 'Root', value: root },
            { label: 'Description', value: text(row.description) },
            { label: 'Last opened', value: text(row.last_opened_at) },
          ]),
        },
      ],
      preview: text(row.description),
    }
  }

  return null
}
