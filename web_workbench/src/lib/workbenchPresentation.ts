import type { ArtifactSummary, JobStatus, RadAgentEvent } from './api'
import type { TimelineRow } from './workbenchState'

export type WorkbenchHero = {
  eyebrow: string
  title: string
  subtitle: string
  statusText: string
  statusTone: 'idle' | 'running' | 'paused' | 'error'
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
  detail: string
  statusLabel: string
  phaseLabel: string
}

export type AgentCockpitStatusChip = {
  label: string
  value: string
  tone: 'neutral' | 'running' | 'warning' | 'error' | 'success'
}

export type LlmDebugCall = {
  id: string
  phase: string
  phaseLabel: string
  moduleName: string
  moduleLabel: string
  modelName: string
  status: 'running' | 'success' | 'error' | 'info'
  statusLabel: string
  durationLabel: string
  promptSummary: string
  promptCharsLabel: string
  outputSummary: string
  outputCharsLabel: string
  artifactPath: string
  createdAt: string
}

export type AgentCockpit = {
  agent: {
    stateLabel: string
    phaseLabel: string
    currentAction: string
    workspace: string
    changedFiles: string
    statusChips: AgentCockpitStatusChip[]
  }
  fileGroups: AgentCockpitFileGroup[]
  recentActivity: AgentCockpitActivity[]
  llmDebugCalls: LlmDebugCall[]
  runtimeActive: boolean
}

export type ReviewCallout = {
  kind: 'human-confirmation' | 'repair-continuation'
  eyebrow: string
  title: string
  detail: string
  primaryLabel: string
  primaryCommand: string
  secondaryLabel?: string
  secondaryCommand?: string
}

const pipelinePhases = [
  'prepare_workspace',
  'context',
  'task_planning',
  'requirements_review',
  'g4_modeling',
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
  requirements_review: { label: '参数核对', labelEn: 'Requirements' },
  g4_modeling: { label: 'Geant4 建模', labelEn: 'Model IR' },
  human_confirmation: { label: '参数核对', labelEn: 'Requirements' },
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

const llmStatusLabels: Record<LlmDebugCall['status'], string> = {
  info: '记录',
  running: '运行中',
  success: '通过',
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

const codegenStatusLabels: Record<string, { value: string; tone: AgentCockpitStatusChip['tone'] }> = {
  passed: { value: '已通过', tone: 'success' },
  failed: { value: '失败', tone: 'error' },
  needs_user_input: { value: '等待修复批准', tone: 'warning' },
  running: { value: '运行中', tone: 'running' },
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

function runtimeStatusLabel(status?: string): string {
  if (!status) {
    return '待命'
  }
  return runtimeStatusLabels[status] || status.replaceAll('_', ' ')
}

function runtimeActive(status: JobStatus | null): boolean {
  return status?.key_statuses?.runtime_active === true || status?.state?.runtime_active === true
}

function presentedRuntimeStatus(status: JobStatus | null): string {
  if (status?.status === 'running' && !runtimeActive(status)) {
    return '待继续'
  }
  return runtimeStatusLabel(status?.status)
}

function runtimeStatusTone(status?: string): WorkbenchHero['statusTone'] {
  if (status === 'running' || status === 'completed') {
    return 'running'
  }
  if (status === 'paused' || status === 'blocked') {
    return 'paused'
  }
  if (status === 'failed' || status === 'error') {
    return 'error'
  }
  return 'idle'
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

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function statusValue(status: JobStatus, key: string): string {
  return String(status.key_statuses?.[key] ?? status.state?.[key] ?? '').trim()
}

function repairContinuationRequest(status: JobStatus): Record<string, unknown> {
  const request = status.state?.repair_continuation_request
  return record(request)
}

export function createReviewCallout(status: JobStatus | null): ReviewCallout | null {
  if (!status || !status.job_id) {
    return null
  }
  const reviewCommand = `/confirm ${status.job_id}`

  const repairStatus = statusValue(status, 'repair_continuation_status')
  const repairRequest = repairContinuationRequest(status)
  if (repairStatus === 'pending' && repairRequest.status === 'pending') {
    const increment = Number(repairRequest.increment_turns || 12)
    return {
      kind: 'repair-continuation',
      eyebrow: '需要批准继续修复',
      title: `修复 Agent 已耗尽当前轮数，是否追加 ${increment} 轮继续修复？`,
      detail: '这不是普通下一步。批准后会继续当前 Geant4 工程修复；拒绝则保留当前失败/暂停状态。',
      primaryLabel: `批准追加 ${increment} 轮`,
      primaryCommand: '/confirm approve',
      secondaryLabel: '查看确认项',
      secondaryCommand: reviewCommand,
    }
  }

  if (statusValue(status, 'g4_modeling_status') === 'failed') {
    return null
  }

  const confirmationStatus = statusValue(status, 'confirmation_status')
  const requirementsReviewStatus = statusValue(status, 'requirements_review_status')
  const requirementsReviewPending = ['pending', 'needs_user_input'].includes(requirementsReviewStatus)
  const humanConfirmationRequired = Boolean(status.state?.human_confirmation_required)
  const humanConfirmationPending =
    requirementsReviewPending ||
    confirmationStatus === 'pending' ||
    status.current_phase === 'human_confirmation' ||
    humanConfirmationRequired

  if (humanConfirmationPending && confirmationStatus !== 'approved') {
    if (
      requirementsReviewPending ||
      status.current_phase === 'requirements_review' ||
      status.current_phase === 'human_confirmation' ||
      humanConfirmationRequired
    ) {
      return {
        kind: 'human-confirmation',
        eyebrow: '需要参数核对',
        title: '建模前需要你确认关键 Geant4 参数。',
        detail: '逐项查看模型建议的推荐答案。确认推荐或填写修改后，模型会再次评估，直到参数足够明确再进入建模。',
        primaryLabel: '打开参数核对',
        primaryCommand: reviewCommand,
      }
    }
  }

  return null
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

function eventField(event: RadAgentEvent, key: string): unknown {
  const payloadValue = event.payload?.[key]
  if (payloadValue !== undefined) {
    return payloadValue
  }
  return (event as unknown as Record<string, unknown>)[key]
}

function eventArtifacts(event: RadAgentEvent): Array<{ path?: unknown }> {
  const raw = eventField(event, 'artifacts')
  return Array.isArray(raw) ? (raw as Array<{ path?: unknown }>) : []
}

function eventMetrics(event: RadAgentEvent): Record<string, unknown> {
  return record(eventField(event, 'metrics'))
}

function eventDetails(event: RadAgentEvent): Record<string, unknown> {
  return record(eventField(event, 'details'))
}

function eventDurationMs(event: RadAgentEvent): number {
  const value = Number(eventField(event, 'duration_ms'))
  return Number.isFinite(value) && value >= 0 ? value : 0
}

function eventErrors(event: RadAgentEvent): string[] {
  const raw = eventField(event, 'errors')
  return Array.isArray(raw) ? raw.map((item) => String(item || '').trim()).filter(Boolean) : []
}

function eventTimestamp(event: RadAgentEvent): string {
  return (
    String(event.created_at || '').trim() ||
    String((event as unknown as Record<string, unknown>).timestamp || '').trim()
  )
}

function latestEvent(events: RadAgentEvent[]): RadAgentEvent | undefined {
  return events
    .map((event, index) => ({ event, index }))
    .sort((a, b) => {
      const byTime = eventTimestamp(b.event).localeCompare(eventTimestamp(a.event))
      return byTime || b.index - a.index
    })
    .at(0)?.event
}

function workflowEvents(events: RadAgentEvent[]): RadAgentEvent[] {
  return events.filter((event) => !event.event_type.startsWith('copilot_'))
}

function sortEventsNewestFirst(events: RadAgentEvent[]): RadAgentEvent[] {
  return events
    .map((event, index) => ({ event, index }))
    .sort((a, b) => {
      const byTime = eventTimestamp(b.event).localeCompare(eventTimestamp(a.event))
      return byTime || b.index - a.index
    })
    .map((item) => item.event)
}

function latestWorkflowEvent(events: RadAgentEvent[], phase = ''): RadAgentEvent | undefined {
  const candidates = workflowEvents(events)
  const phaseMatches = phase ? candidates.filter((event) => event.phase === phase) : []
  return latestEvent(phaseMatches.length > 0 ? phaseMatches : candidates)
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

function statusRawValue(status: JobStatus | null, key: string): string {
  return String(status?.key_statuses?.[key] ?? status?.state?.[key] ?? '').trim()
}

function compactNodeLabel(status: JobStatus | null, fallbackPhase: string): string {
  const rawNode = statusRawValue(status, 'current_node')
  const confirmationApproved =
    statusRawValue(status, 'confirmation_status') === 'approved' &&
    status?.state?.human_confirmation_required !== true
  if (
    confirmationApproved &&
    fallbackPhase !== 'human_confirmation' &&
    rawNode === 'human_confirmation_subgraph'
  ) {
    return humanizeIdentifier(fallbackPhase)
  }
  return humanizeIdentifier(rawNode || fallbackPhase)
}

function codegenStatusChip(status: JobStatus | null): AgentCockpitStatusChip | null {
  if (status?.current_phase !== 'g4_codegen' && !statusRawValue(status, 'g4_codegen_status')) {
    return null
  }
  const raw = statusRawValue(status, 'g4_codegen_status') || status?.status || 'running'
  if (raw === 'running' && status?.status === 'running' && !runtimeActive(status)) {
    return { label: 'Codegen', value: '待继续', tone: 'warning' }
  }
  const mapped = codegenStatusLabels[raw] || {
    value: humanizeIdentifier(raw) || '运行中',
    tone: raw === 'failed' ? 'error' : raw === 'paused' ? 'warning' : 'running',
  }
  return { label: 'Codegen', value: mapped.value, tone: mapped.tone }
}

function latestModuleLabel(event: RadAgentEvent | undefined): string {
  const details = event ? eventDetails(event) : {}
  const metadata = record(details.metadata)
  const moduleName = String(
    (event ? eventField(event, 'module_name') : '') || metadata.module_name || '',
  ).trim()
  return humanizeIdentifier(moduleName || event?.event_type || '')
}

function repairTurnsChip(status: JobStatus | null): AgentCockpitStatusChip | null {
  const request = record(status?.state?.repair_continuation_request)
  const report = record(status?.state?.global_integration_agent_report)
  const agentic = record(report.agentic)
  const currentTurns = Number(request.current_turns ?? agentic.n_turns)
  const requestedTotal = Number(request.requested_total_turns)
  if (!Number.isFinite(currentTurns) || currentTurns <= 0) {
    return null
  }
  return {
    label: '修复轮数',
    value: Number.isFinite(requestedTotal) && requestedTotal > 0 ? `${currentTurns}/${requestedTotal}` : String(currentTurns),
    tone: 'warning',
  }
}

function waitingChip(status: JobStatus | null): AgentCockpitStatusChip | null {
  const repairStatus = statusRawValue(status, 'repair_continuation_status')
  const request = record(status?.state?.repair_continuation_request)
  if (repairStatus === 'pending' && request.status === 'pending') {
    return { label: '等待事项', value: '批准继续修复', tone: 'warning' }
  }
  if (status?.needs_confirmation) {
    if (statusRawValue(status, 'requirements_review_status')) {
      return { label: '等待事项', value: '参数核对', tone: 'warning' }
    }
    return { label: '等待事项', value: '确认', tone: 'warning' }
  }
  return null
}

function agentStatusChips(
  status: JobStatus | null,
  activePhase: string,
  currentEvent: RadAgentEvent | undefined,
): AgentCockpitStatusChip[] {
  const chips: AgentCockpitStatusChip[] = [
    { label: '当前节点', value: compactNodeLabel(status, activePhase), tone: 'neutral' },
  ]
  const codegen = codegenStatusChip(status)
  if (codegen) {
    chips.push(codegen)
  }
  const moduleLabel = latestModuleLabel(currentEvent)
  if (moduleLabel) {
    chips.push({ label: '构建模块', value: moduleLabel, tone: 'running' })
  }
  const repairTurns = repairTurnsChip(status)
  if (repairTurns) {
    chips.push(repairTurns)
  }
  const waiting = waitingChip(status)
  if (waiting) {
    chips.push(waiting)
  }
  return chips
}

function eventStatusLabel(status: unknown): string {
  const raw = String(status || '').trim()
  if (raw in statusLabels) {
    return statusLabels[raw as TimelineRow['status']]
  }
  if (['passed', 'complete', 'completed', 'succeeded'].includes(raw)) {
    return '通过'
  }
  if (['failed', 'failure'].includes(raw)) {
    return '失败'
  }
  return humanizeIdentifier(raw) || '记录'
}

function normalizeLlmStatus(status: unknown): LlmDebugCall['status'] {
  const raw = String(status || '').trim().toLowerCase()
  if (raw === 'running') {
    return 'running'
  }
  if (['passed', 'success', 'succeeded', 'complete', 'completed'].includes(raw)) {
    return 'success'
  }
  if (['failed', 'error', 'failure'].includes(raw)) {
    return 'error'
  }
  return 'info'
}

function normalizeLlmStatusForRuntime(
  status: unknown,
  runtimeIsActive: boolean,
): LlmDebugCall['status'] {
  const normalized = normalizeLlmStatus(status)
  if (normalized === 'running' && !runtimeIsActive) {
    return 'info'
  }
  return normalized
}

function numberValue(value: unknown): number {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : 0
}

function characterLabel(count: number): string {
  return count > 0 ? `${count.toLocaleString('en-US')} 字符` : ''
}

function durationLabel(durationMs: number, status: LlmDebugCall['status']): string {
  if (durationMs > 0) {
    if (durationMs < 1000) {
      return `${Math.round(durationMs)} ms`
    }
    if (durationMs < 600_000) {
      return `${(durationMs / 1000).toFixed(1)} 秒`
    }
    return `${(durationMs / 60_000).toFixed(1)} 分钟`
  }
  return status === 'running' ? '进行中' : '未记录'
}

function modelCallId(event: RadAgentEvent): string {
  const details = eventDetails(event)
  const metadata = record(details.metadata)
  const artifactPath = eventArtifacts(event)
    .map((artifact) => String(artifact.path || '').trim())
    .find(Boolean)
  return (
    String(metadata.model_call_id || eventField(event, 'model_call_id') || '').trim() ||
    artifactPath ||
    [eventTimestamp(event), event.event_type, event.phase, event.summary].join(':')
  )
}

function modelCallModuleName(event: RadAgentEvent): string {
  const details = eventDetails(event)
  const metadata = record(details.metadata)
  return String(
    eventField(event, 'module_name') || metadata.module_name || details.module_name || '',
  ).trim()
}

function modelCallModelName(event: RadAgentEvent): string {
  const details = eventDetails(event)
  return String(details.model_name || eventField(event, 'model_name') || '').trim()
}

type LlmCallDraft = {
  id: string
  phase: string
  moduleName: string
  modelName: string
  status: LlmDebugCall['status']
  durationMs: number
  promptSummary: string
  promptChars: number
  outputSummary: string
  outputChars: number
  artifactPath: string
  createdAt: string
  order: number
}

function mergeModelCallEvent(
  draft: LlmCallDraft,
  event: RadAgentEvent,
  index: number,
  runtimeIsActive: boolean,
): LlmCallDraft {
  const metrics = eventMetrics(event)
  const artifactPath = eventArtifacts(event)
    .map((artifact) => String(artifact.path || '').trim())
    .find(Boolean)
  const moduleName = modelCallModuleName(event)
  const modelName = modelCallModelName(event)
  const createdAt = eventTimestamp(event)
  const isStart = event.event_type === 'model_call_start'
  const status = normalizeLlmStatusForRuntime(event.status, runtimeIsActive)
  const systemPromptChars = numberValue(metrics.system_prompt_chars)
  const userPromptChars = numberValue(metrics.user_prompt_chars)
  const contentLength = numberValue(metrics.content_length)
  const errors = eventErrors(event)

  return {
    ...draft,
    phase: event.phase || draft.phase,
    moduleName: moduleName || draft.moduleName,
    modelName: modelName || draft.modelName,
    artifactPath: artifactPath || draft.artifactPath,
    createdAt: createdAt && createdAt >= draft.createdAt ? createdAt : draft.createdAt,
    order: Math.max(draft.order, index),
    status:
      status === 'running' && (draft.status === 'success' || draft.status === 'error')
        ? draft.status
        : status,
    durationMs: eventDurationMs(event) || draft.durationMs,
    promptSummary: isStart && event.summary ? event.summary : draft.promptSummary,
    promptChars: systemPromptChars + userPromptChars || draft.promptChars,
    outputSummary: !isStart
      ? errors[0] || event.summary || draft.outputSummary
      : draft.outputSummary,
    outputChars: contentLength || draft.outputChars,
  }
}

function createEmptyModelCallDraft(id: string): LlmCallDraft {
  return {
    id,
    phase: '',
    moduleName: '',
    modelName: '',
    status: 'info',
    durationMs: 0,
    promptSummary: '',
    promptChars: 0,
    outputSummary: '',
    outputChars: 0,
    artifactPath: '',
    createdAt: '',
    order: 0,
  }
}

function createLlmDebugCalls(events: RadAgentEvent[], runtimeIsActive: boolean): LlmDebugCall[] {
  const calls = new Map<string, LlmCallDraft>()

  events.forEach((event, index) => {
    if (event.event_type !== 'model_call_start' && event.event_type !== 'model_call') {
      return
    }
    const id = modelCallId(event)
    const draft = calls.get(id) || createEmptyModelCallDraft(id)
    calls.set(id, mergeModelCallEvent(draft, event, index, runtimeIsActive))
  })

  return [...calls.values()]
    .sort((left, right) => {
      const byTime = right.createdAt.localeCompare(left.createdAt)
      return byTime || right.order - left.order
    })
    .slice(0, 5)
    .map((call) => {
      const status = call.status
      return {
        id: call.id,
        phase: call.phase || 'unknown',
        phaseLabel: phaseLabel(call.phase || 'unknown'),
        moduleName: call.moduleName || 'unknown',
        moduleLabel: humanizeIdentifier(call.moduleName) || 'Unknown',
        modelName: call.modelName || '未知模型',
        status,
        statusLabel: llmStatusLabels[status],
        durationLabel: durationLabel(call.durationMs, status),
        promptSummary: call.promptSummary || '未收到 prompt 摘要',
        promptCharsLabel: characterLabel(call.promptChars) || '未知字符数',
        outputSummary:
          call.outputSummary ||
          (status === 'running'
            ? '等待模型输出'
            : !runtimeIsActive && call.durationMs === 0
              ? '等待继续后刷新'
              : '未收到输出摘要'),
        outputCharsLabel: characterLabel(call.outputChars),
        artifactPath: call.artifactPath || '未记录 artifact 路径',
        createdAt: call.createdAt,
      }
    })
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
      statusTone: 'idle',
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
    statusText: `${presentedRuntimeStatus(status)} · ${currentPhase}`,
    statusTone:
      status.status === 'running' && !runtimeActive(status)
        ? 'paused'
        : runtimeStatusTone(status.status),
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
      { label: '状态', value: presentedRuntimeStatus(status) },
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
  const activePhase = status?.current_phase || 'prepare_workspace'
  const currentEvent = latestWorkflowEvent(events, activePhase)
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

  const recentActivity = sortEventsNewestFirst(workflowEvents(events))
    .slice(0, 4)
    .map((event) => ({
      title: event.event_type.replaceAll('_', ' '),
      detail: event.summary,
      statusLabel: eventStatusLabel(event.status),
      phaseLabel: phaseLabel(event.phase),
    }))

  return {
    agent: {
      stateLabel: presentedRuntimeStatus(status),
      phaseLabel: heroPhaseLabel(activePhase),
      currentAction: currentEvent?.summary || phaseLabel(activePhase),
      workspace: status?.job_workspace || status?.workspace_root || '尚未创建工作区',
      changedFiles: changedFileLabel(events),
      statusChips: agentStatusChips(status, activePhase, currentEvent),
    },
    fileGroups,
    recentActivity,
    llmDebugCalls: createLlmDebugCalls(events, runtimeActive(status)),
    runtimeActive: runtimeActive(status),
  }
}
