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
  return `${count} ${singular}${count === 1 ? '' : 's'}`
}

function compact(parts: string[]): string {
  return parts.filter(Boolean).join(' · ')
}

function rowFor(view: string, item: unknown, index: number): CollectionRow {
  const record = asRecord(item)

  if (view === 'jobs') {
    return {
      title: text(record.user_query || record.job_id, `Job ${index + 1}`),
      status: text(record.status, 'unknown'),
      detail: compact([
        text(record.current_phase || record.phase),
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
      status: text(record.kind || record.stage, 'artifact'),
      detail: compact([text(record.stage), bytes(record.size_bytes)]),
      meta: path,
      record,
    }
  }

  if (view === 'gates') {
    const gateId = text(record.gate_id ?? record.id, String(index + 1))
    return {
      title: `Gate ${gateId}`,
      status: text(record.status, 'unknown'),
      detail: text(record.message || record.summary || record.reason),
      meta: text(record.credibility_level || record.level || record.phase),
      record,
    }
  }

  if (view === 'revisions') {
    return {
      title: text(record.revision_id, `Revision ${index + 1}`),
      status: text(record.status, 'unknown'),
      detail: text(record.user_request || record.summary),
      meta: text(record.patch_status || record.candidate_project_dir),
      record,
    }
  }

  if (view === 'projects') {
    return {
      title: text(record.name || record.slug, `Project ${index + 1}`),
      status: text(record.slug, 'project'),
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
    status: text(record.status ?? record.kind ?? record.name ?? record.stage),
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
    jobs: 'Jobs',
    artifacts: 'Artifacts',
    gates: 'Gates',
    projects: 'Projects',
    revisions: 'Revisions',
  }
  const nouns: Record<string, string> = {
    jobs: 'job',
    artifacts: 'artifact',
    gates: 'gate',
    projects: 'project',
    revisions: 'revision',
  }
  const title = labels[view] || 'Records'
  const noun = nouns[view] || 'record'

  return {
    title,
    summary: plural(data.length, noun),
    rows: data.map((item, index) => rowFor(view, item, index)),
  }
}
