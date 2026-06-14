import type { ArtifactSummary, JobStatus, RadAgentEvent } from './api'
import type { TimelineRow } from './workbenchState'

export type WorkbenchHero = {
  eyebrow: string
  title: string
  subtitle: string
  statusText: string
  modeText: string
}

export type PhaseTrackItem = {
  id: string
  label: string
  labelEn: string
  state: 'done' | 'active' | 'pending'
}

export type PresentedTimelineRow = {
  label: string
  title: string
  body: string
  phase: string
  statusLabel: string
  expandable: boolean
}

export type StatusPanelSummary = {
  metrics: Array<{ label: string; value: string }>
  phases: Array<{
    id: string
    label: string
    state: 'done' | 'active' | 'pending'
    marker: string
  }>
}

export type AgentCockpitFile = {
  path: string
  name: string
  stage: string
  kindLabel: string
  sizeLabel: string
  selected: boolean
}

export type AgentCockpitFileGroup = {
  id: string
  label: string
  labelEn: string
  files: AgentCockpitFile[]
}

export type AgentCockpitActivity = {
  title: string
  statusLabel: string
  phaseLabel: string
}

export type AgentCockpit = {
  agent: {
    stateLabel: string
    phaseLabel: string
    currentAction: string
    workspace: string
    changedFiles: string
  }
  fileGroups: AgentCockpitFileGroup[]
  recentActivity: AgentCockpitActivity[]
}

const pipelinePhases = [
  'prepare_workspace',
  'context',
  'task_planning',
  'g4_modeling',
  'human_confirmation',
  'g4_codegen',
  'patch',
  'gate',
  'artifact',
  'report',
] as const

const phaseLabels: Record<string, { label: string; labelEn: string }> = {
  prepare_workspace: { label: '准备工作区', labelEn: 'Workspace' },
  context: { label: '上下文收集', labelEn: 'Context' },
  task_planning: { label: '任务规划', labelEn: 'Planning' },
  g4_modeling: { label: 'Geant4 建模', labelEn: 'Model IR' },
  human_confirmation: { label: '人工确认', labelEn: 'Review' },
  g4_codegen: { label: '工程生成', labelEn: 'Codegen' },
  patch: { label: '修订补丁', labelEn: 'Patch' },
  gate: { label: '验证门禁', labelEn: 'Gates' },
  artifact: { label: '产物归档', labelEn: 'Artifacts' },
  report: { label: '报告交付', labelEn: 'Report' },
  validation: { label: '验证门禁', labelEn: 'Validation' },
}

const statusLabels: Record<TimelineRow['status'], string> = {
  info: '记录',
  running: '运行中',
  success: '通过',
  warning: '需审查',
  error: '失败',
}

const runtimeStatusLabels: Record<string, string> = {
  idle: '待命',
  running: '运行中',
  paused: '暂停审查',
  completed: '已完成',
  failed: '失败',
  blocked: '已阻塞',
}

const confirmationStatusLabels: Record<string, string> = {
  pending: '等待审查',
  approved: '已批准',
  rejected: '已拒绝',
  asked_more: '等待补充',
  blocked: '已阻塞',
  complete: '已完成',
  completed: '已完成',
}

function phaseLabel(phase?: string): string {
  if (!phase) {
    return '准备工作区'
  }
  return phaseLabels[phase]?.label || phase.replaceAll('_', ' ')
}

function heroPhaseLabel(phase?: string): string {
  if (phase === 'g4_codegen') {
    return 'Geant4 工程生成'
  }
  return phaseLabel(phase)
}

function runModeLabel(mode?: string): string {
  if (!mode || mode === 'local') {
    return '本地运行'
  }
  if (mode === 'remote') {
    return '远程运行'
  }
  return mode
}

function runtimeStatusLabel(status?: string): string {
  if (!status) {
    return '待命'
  }
  return runtimeStatusLabels[status] || status.replaceAll('_', ' ')
}

function humanizeIdentifier(value?: string): string {
  const text = String(value || '').trim()
  if (!text) {
    return ''
  }
  const lastSegment = text.split('/').filter(Boolean).at(-1) || text
  return lastSegment
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function completedCount(status: JobStatus): number {
  const completed = new Set(status.completed_phases)
  return pipelinePhases.filter((phase) => completed.has(phase)).length
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

const artifactKindLabels: Record<string, string> = {
  report: '报告',
  source: '源码',
  code: '源码',
  json: 'JSON',
  gate: '门禁',
  log: '日志',
  text: '文本',
  binary: '二进制',
}

function artifactKindLabel(kind?: string, path = ''): string {
  const normalized = String(kind || '').trim().toLowerCase()
  if (artifactKindLabels[normalized]) {
    return artifactKindLabels[normalized]
  }
  const suffix = basename(path).split('.').at(-1)?.toLowerCase()
  if (['cc', 'hh', 'hpp', 'cpp', 'h', 'cmake', 'mac'].includes(suffix || '')) {
    return '源码'
  }
  if (suffix === 'json') {
    return 'JSON'
  }
  if (suffix === 'md') {
    return '报告'
  }
  return normalized || '产物'
}

function stageId(artifact: ArtifactSummary): string {
  const path = artifact.path || ''
  const stage = String(artifact.stage || '').trim()
  if (stage) {
    return stage
  }
  const match = path.match(/\/(\d{2}_[^/]+)/)
  return match?.[1] || 'artifact'
}

function stageSortValue(stage: string): number {
  const match = stage.match(/^(\d+)/)
  if (match) {
    return Number(match[1])
  }
  return 99
}

function eventArtifacts(event: RadAgentEvent): Array<{ path?: unknown }> {
  const raw = event.payload?.artifacts
  return Array.isArray(raw) ? (raw as Array<{ path?: unknown }>) : []
}

function latestEvent(events: RadAgentEvent[]): RadAgentEvent | undefined {
  return [...events].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).at(0)
}

function changedFileLabel(events: RadAgentEvent[]): string {
  for (const event of [...events].reverse()) {
    const count = Number(event.payload?.changed_file_count ?? event.payload?.generated_file_count)
    if (Number.isFinite(count) && count > 0) {
      return `${count} 个文件`
    }
  }
  const artifactPaths = new Set<string>()
  for (const event of events) {
    for (const artifact of eventArtifacts(event)) {
      const path = String(artifact.path || '').trim()
      if (path) {
        artifactPaths.add(path)
      }
    }
  }
  return artifactPaths.size > 0 ? `${artifactPaths.size} 个文件` : '暂无文件变更'
}

function extractPromptField(prompt: string, label: string): string {
  const match = prompt.match(new RegExp(`${label}：([^。]+)`))
  return match?.[1]?.trim() || ''
}

function workbenchTitle(status: JobStatus): string {
  const query = status.user_query?.trim()
  if (!query) {
    return status.job_id
  }
  if (query.includes('空天辐照防护仿真任务') && query.includes('任务模板：')) {
    const template = extractPromptField(query, '任务模板')
    const source = extractPromptField(query, '粒子源')
    const parts = [template, source].filter(Boolean)
    if (parts.length > 0) {
      return parts.join(' · ')
    }
  }
  if (query.length > 42) {
    return `${query.slice(0, 40)}...`
  }
  return query
}

export function createWorkbenchHero(status: JobStatus | null): WorkbenchHero {
  if (!status || !status.job_id) {
    return {
      eyebrow: 'RadAgent',
      title: '等待仿真任务',
      subtitle: '输入辐照防护目标，Agent 会规划模型、构建工程、运行门禁并归档结果。',
      statusText: '待命 · 准备工作区',
      modeText: '本地环境 · strict',
    }
  }

  const currentPhase = heroPhaseLabel(status.current_phase)
  const done = completedCount(status)
  const total = pipelinePhases.length
  const project = humanizeIdentifier(String(status.state.project_slug || status.workspace_root || status.job_id))

  return {
    eyebrow: project,
    title: workbenchTitle(status),
    subtitle: `当前推进到 ${currentPhase}，已完成 ${done}/${total} 个阶段。`,
    statusText: `${runtimeStatusLabel(status.status)} · ${currentPhase}`,
    modeText: `${runModeLabel(status.run_mode)} · ${status.execution_mode || 'strict'}`,
  }
}

export function createPhaseTrack(status: JobStatus | null): PhaseTrackItem[] {
  const completed = new Set(status?.completed_phases || [])
  const activePhase = status?.current_phase || 'prepare_workspace'

  return pipelinePhases.map((phase) => {
    const labels = phaseLabels[phase]
    const state: PhaseTrackItem['state'] = completed.has(phase)
      ? 'done'
      : phase === activePhase
        ? 'active'
        : 'pending'
    return {
      id: phase,
      label: labels.label,
      labelEn: labels.labelEn,
      state,
    }
  })
}

function timelineKindLabel(kind: TimelineRow['kind']): string {
  if (kind === 'event') {
    return 'Agent 证据'
  }
  if (kind === 'command') {
    return '用户操作'
  }
  return '系统记录'
}

export function presentTimelineRow(row: TimelineRow): PresentedTimelineRow {
  return {
    label: timelineKindLabel(row.kind),
    title: row.title.replaceAll('_', ' '),
    body: row.body,
    phase: phaseLabel(row.meta),
    statusLabel: statusLabels[row.status],
    expandable: Boolean(row.details),
  }
}

export function createStatusPanelSummary(status: JobStatus | null): StatusPanelSummary {
  if (!status) {
    return {
      metrics: [
        { label: '活动作业', value: '暂无活动作业' },
        { label: '状态', value: '未加载' },
      ],
      phases: createPhaseTrack(null).map((phase, index) => ({
        id: phase.id,
        label: phase.label,
        state: phase.state,
        marker: String(index + 1),
      })),
    }
  }

  return {
    metrics: [
      { label: '活动作业', value: status.job_id || '暂无活动作业' },
      { label: '状态', value: runtimeStatusLabel(status.status) },
    ],
    phases: createPhaseTrack(status).map((phase, index) => ({
      id: phase.id,
      label: phase.label,
      state: phase.state,
      marker: phase.state === 'active' ? '当前' : String(index + 1),
    })),
  }
}

export function presentConfirmationStatus(status: unknown): string {
  const normalized = String(status ?? '').trim()
  if (!normalized) {
    return '未加载确认项'
  }
  return confirmationStatusLabels[normalized] || normalized.replaceAll('_', ' ')
}

export function createAgentCockpit({
  status,
  events,
  artifacts,
  selectedPath = '',
}: {
  status: JobStatus | null
  events: RadAgentEvent[]
  artifacts: ArtifactSummary[]
  selectedPath?: string
}): AgentCockpit {
  const currentEvent = latestEvent(events)
  const activePhase = status?.current_phase || currentEvent?.phase || 'prepare_workspace'
  const grouped = new Map<string, AgentCockpitFile[]>()

  for (const artifact of artifacts) {
    const path = artifact.path
    if (!path) {
      continue
    }
    const id = stageId(artifact)
    const files = grouped.get(id) || []
    files.push({
      path,
      name: basename(path),
      stage: id,
      kindLabel: artifactKindLabel(artifact.kind, path),
      sizeLabel: bytes(artifact.size_bytes),
      selected: Boolean(selectedPath && selectedPath === path),
    })
    grouped.set(id, files)
  }

  const fileGroups = [...grouped.entries()]
    .sort(([left], [right]) => stageSortValue(left) - stageSortValue(right) || left.localeCompare(right))
    .map(([id, files]) => {
      const labels = phaseLabels[id] || phaseLabels[id.replace(/^\d+_/, '')] || {
        label: humanizeIdentifier(id) || '产物',
        labelEn: 'Files',
      }
      return {
        id,
        label: labels.label,
        labelEn: labels.labelEn,
        files: files.sort((left, right) => left.name.localeCompare(right.name)),
      }
    })

  const recentActivity = [...events]
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .slice(0, 4)
    .map((event) => ({
      title: event.event_type.replaceAll('_', ' '),
      statusLabel: statusLabels[event.status],
      phaseLabel: phaseLabel(event.phase),
    }))

  return {
    agent: {
      stateLabel: runtimeStatusLabel(status?.status),
      phaseLabel: heroPhaseLabel(activePhase),
      currentAction: currentEvent?.summary || '等待新的 Agent 操作',
      workspace: status?.job_workspace || status?.workspace_root || '尚未创建工作区',
      changedFiles: changedFileLabel(events),
    },
    fileGroups,
    recentActivity,
  }
}
