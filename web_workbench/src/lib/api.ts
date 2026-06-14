export type CommandCatalogEntry = {
  name: string
  description: string
  tip: string
  module: string
  connection: 'service' | 'derived' | 'panel' | 'alias' | 'client'
  visible: boolean
}

export type JobStatus = {
  job_id: string
  user_query: string
  status: string
  current_phase: string
  current_phase_idx: number
  completed_phases: string[]
  execution_mode: string
  run_mode: string
  workspace_root: string
  job_workspace: string
  needs_confirmation: boolean
  key_statuses: Record<string, unknown>
  state: Record<string, unknown>
}

export type RadAgentEvent = {
  event_type: string
  status: 'info' | 'running' | 'success' | 'warning' | 'error'
  summary: string
  phase: string
  job_id: string
  run_id: string
  payload: Record<string, unknown>
  created_at: string
}

export type WebCommandResponse = {
  ok: boolean
  command?: string
  args?: string
  view: string
  data?: unknown
  error?: string
}

export type ArtifactContent = {
  path: string
  exists: boolean
  kind: 'text' | 'json' | 'binary' | 'missing'
  text: string
  json_data: unknown | null
  size_bytes: number
  truncated: boolean
  errors: string[]
}

export type ArtifactSummary = {
  job_id?: string
  path: string
  stage?: string
  kind?: string
  mime_type?: string
  size_bytes?: number
  sha256?: string
}

export type ModelUpdatePayload = {
  base_url?: string
  api_key?: string
  api_key_env?: string
  lite_model?: string
  pro_model?: string
  max_model?: string
  lite_timeout_s?: number
  pro_timeout_s?: number
  max_timeout_s?: number
  lite_max_tokens?: number
  pro_max_tokens?: number
  max_max_tokens?: number
  lite_context_window_tokens?: number
  pro_context_window_tokens?: number
  max_context_window_tokens?: number
  agentic_repair_max_turns?: number
  agentic_repair_history_chars?: number
}

export type ModelHealthTierResult = {
  tier: string
  status: 'ok' | 'error' | 'skipped'
  model_name: string
  base_url: string
  api_key_env: string
  latency_ms: number
  response_preview: string
  error: string
}

export type ModelHealthReport = {
  tested_at: string
  tiers: Record<string, ModelHealthTierResult>
}

export type WorkflowCapability = {
  name: string
  description: string
  command: string
}

export type HomeProjectCard = {
  job_id: string
  title: string
  project_name: string
  status: string
  phase: string
  updated_at: string
  artifact_count: number
  artifact_kinds: string[]
}

export type ShowcaseExample = {
  id: string
  title: string
  subtitle: string
  prompt: string
  difficulty: string
  tags: string[]
  validation_focus: string[]
}

export type HomeSummary = {
  metrics: {
    projects: number
    jobs: number
    completed_jobs: number
    active_jobs: number
    artifacts: number
  }
  workflow_capabilities: WorkflowCapability[]
  projects: HomeProjectCard[]
  showcase_examples: ShowcaseExample[]
}

export type VisualizationApiPayload = Record<string, unknown>

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  let payload: unknown = null
  if (text.trim()) {
    try {
      payload = JSON.parse(text)
    } catch {
      const suffix = response.ok ? '' : `（${response.status} ${response.statusText || 'API error'}）`
      throw new Error(`工作台服务返回了不可解析的数据${suffix}`)
    }
  } else if (!response.ok) {
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      throw new Error('本地 RadAgent 服务未连接，请确认后端服务已启动。')
    }
    throw new Error(`工作台服务返回空响应（${response.status} ${response.statusText || 'API error'}）`)
  } else {
    throw new Error('工作台服务返回了不可解析的数据')
  }
  if (!response.ok) {
    const message =
      typeof payload === 'object' && payload && 'error' in payload
        ? String((payload as { error: unknown }).error)
        : response.statusText
    throw new Error(message)
  }
  return payload as T
}

export async function fetchCommandCatalog(): Promise<CommandCatalogEntry[]> {
  const payload = await readJson<{ commands: CommandCatalogEntry[] }>(await fetch('/api/commands'))
  return payload.commands
}

export async function fetchHomeSummary(): Promise<HomeSummary> {
  const payload = await readJson<{ home: HomeSummary }>(await fetch('/api/home'))
  return payload.home
}

export async function fetchStatus(): Promise<JobStatus> {
  const payload = await readJson<{ status: JobStatus }>(await fetch('/api/status'))
  return payload.status
}

export async function fetchEvents(limit = 80): Promise<RadAgentEvent[]> {
  const payload = await readJson<{ events: RadAgentEvent[] }>(
    await fetch(`/api/events?limit=${encodeURIComponent(String(limit))}`),
  )
  return payload.events
}

export async function fetchVisualization(jobId = ''): Promise<VisualizationApiPayload> {
  const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''
  const payload = await readJson<{ visualization: VisualizationApiPayload }>(
    await fetch(`/api/visualization${query}`),
  )
  return payload.visualization
}

export async function fetchArtifacts(jobId = ''): Promise<ArtifactSummary[]> {
  const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''
  const payload = await readJson<{ artifacts: ArtifactSummary[] }>(
    await fetch(`/api/artifacts${query}`),
  )
  return payload.artifacts
}

export async function sendCommand(text: string): Promise<WebCommandResponse> {
  return readJson<WebCommandResponse>(
    await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  )
}

export async function fetchJobDetail(jobId: string): Promise<Record<string, unknown>> {
  const payload = await readJson<{ job: Record<string, unknown> }>(
    await fetch('/api/job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId }),
    }),
  )
  return payload.job
}

export async function fetchArtifactContent(path: string, maxChars = 200_000): Promise<ArtifactContent> {
  const payload = await readJson<{ artifact: ArtifactContent }>(
    await fetch('/api/artifact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, max_chars: maxChars }),
    }),
  )
  return payload.artifact
}

export async function updateModelConfig(update: ModelUpdatePayload): Promise<Record<string, unknown>> {
  const payload = await readJson<{ model: Record<string, unknown> }>(
    await fetch('/api/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    }),
  )
  return payload.model
}

export async function testModelHealth(): Promise<ModelHealthReport> {
  const payload = await readJson<{ health: ModelHealthReport }>(
    await fetch('/api/model/health', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }),
  )
  return payload.health
}
