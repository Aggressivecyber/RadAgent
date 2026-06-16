import {
  Activity,
  CircleDot,
  PanelRightOpen,
  Play,
  Send,
  TerminalSquare,
  X,
} from 'lucide-react'
import { FormEvent, Suspense, lazy, useEffect, useMemo, useState } from 'react'
import {
  fetchCommandCatalog,
  fetchArtifactContent,
  fetchArtifacts,
  fetchEvents,
  fetchJobDetail,
  fetchStatus,
  fetchVisualization,
  sendCommand,
  testModelHealth,
  updateModelConfig,
  type ArtifactContent,
  type ArtifactSummary,
  type CommandCatalogEntry,
  type JobStatus,
  type ModelHealthReport,
  type RadAgentEvent,
  type ModelUpdatePayload,
} from '../lib/api'
import { buildRunCommand, buildSimulateCommand, composeCommandTemplate } from '../lib/commandAssist'
import { commandPresentation } from '../lib/commandPresentation'
import { createSubmissionFeedback, type SubmissionStatus } from '../lib/submissionFeedback'
import { createWorkbenchControlSections } from '../lib/workbenchControls'
import {
  createAgentCockpit,
  createPhaseTrack,
  createReviewCallout,
  createWorkbenchHero,
  type LlmDebugCall,
  presentTimelineRow,
} from '../lib/workbenchPresentation'
import { createLlmResponsePreview, type LlmResponsePreview } from '../lib/llmTranscriptPreview'
import { normalizeVisualizationPayload, type VisualizationPayload } from '../lib/visualizationPayload'
import {
  createInitialWorkbenchState,
  reduceCommandResponse,
  reduceDetailSelection,
  reduceEvents,
  type TimelineRow,
  type WorkbenchState,
} from '../lib/workbenchState'
import type { HomeLaunchTarget } from '../lib/homeNavigation'
import AgentStatusRail from './AgentStatusRail'
import ArtifactWorkspace from './ArtifactWorkspace'
import InspectorPanel from './InspectorPanel'
import LlmDebugPanel from './LlmDebugPanel'
import SimulationViewportFallback from './SimulationViewportFallback'

const SimulationViewport = lazy(() => import('./SimulationViewport'))

type WorkbenchShellProps = {
  onHome: () => void
  launchTarget?: HomeLaunchTarget | null
}

type WorkflowRunState = 'idle' | 'confirming' | 'running'

const navItems = [
  { label: '概览', labelEn: 'Overview', command: '', inspector: 'overview', icon: Activity },
  { label: '运行', labelEn: 'Run', command: '', inspector: 'overview', icon: Play },
  { label: '状态', labelEn: 'Status', command: '/status', inspector: 'status', icon: Activity },
  { label: '作业', labelEn: 'Jobs', command: '/jobs', inspector: 'jobs', icon: TerminalSquare },
  { label: '产物', labelEn: 'Files', command: '/artifacts', inspector: 'artifacts', icon: TerminalSquare },
  { label: '门禁', labelEn: 'Gates', command: '/gates', inspector: 'gates', icon: Activity },
  { label: '日志', labelEn: 'Logs', command: '/logs', inspector: 'logs', icon: TerminalSquare },
  { label: '模型', labelEn: 'Model', command: '/model', inspector: 'model', icon: Activity },
] as const

function timelineBody(row: TimelineRow) {
  if (!row.body) {
    return null
  }
  const clipped = row.body.length > 600 ? `${row.body.slice(0, 600)}...` : row.body
  return <p>{clipped}</p>
}

function timelineDetails(row: TimelineRow) {
  if (!row.details) {
    return null
  }
  const text = JSON.stringify(row.details, null, 2)
  if (!text || text === '{}' || text === '[]') {
    return null
  }
  return (
    <details className="timeline-details">
      <summary>详情 <span>Details</span></summary>
      <pre>{text.length > 2400 ? `${text.slice(0, 2400)}...` : text}</pre>
    </details>
  )
}

function compactWorkspaceLabel(path: string) {
  return path.split('/').filter(Boolean).at(-1) || path
}

const selectedJobStorageKey = 'radagent:selected-job-id'

function readStoredSelectedJobId() {
  if (typeof window === 'undefined') {
    return ''
  }
  return window.localStorage.getItem(selectedJobStorageKey) || ''
}

function rememberSelectedJobId(jobId: string) {
  if (typeof window === 'undefined') {
    return
  }
  if (jobId) {
    window.localStorage.setItem(selectedJobStorageKey, jobId)
  } else {
    window.localStorage.removeItem(selectedJobStorageKey)
  }
}

function isRuntimeActive(status: JobStatus | null): boolean {
  return status?.key_statuses?.runtime_active === true || status?.state?.runtime_active === true
}

function TimelineItem({ row }: { row: TimelineRow }) {
  const presented = presentTimelineRow(row)
  return (
    <article className={`timeline-row ${row.status}`} key={row.id}>
      <span className="timeline-dot" />
      <div className="timeline-content">
        <div className="timeline-meta">
          <span>{presented.label}</span>
          <span>{presented.phase}</span>
          <strong>{presented.statusLabel}</strong>
        </div>
        <strong>{presented.title}</strong>
        {row.meta ? <em>{row.meta}</em> : null}
        {timelineBody(row)}
        {timelineDetails(row)}
      </div>
    </article>
  )
}

export default function WorkbenchShell({ onHome, launchTarget = null }: WorkbenchShellProps) {
  const [commands, setCommands] = useState<CommandCatalogEntry[]>([])
  const [status, setStatus] = useState<JobStatus | null>(null)
  const [events, setEvents] = useState<RadAgentEvent[]>([])
  const [state, setState] = useState<WorkbenchState>(() => createInitialWorkbenchState())
  const [composerText, setComposerText] = useState('')
  const [runRequest, setRunRequest] = useState('')
  const [simulationEvents, setSimulationEvents] = useState(1000)
  const [loadState, setLoadState] = useState('连接中')
  const [visualization, setVisualization] = useState<VisualizationPayload | null>(null)
  const [visualizationLoading, setVisualizationLoading] = useState(false)
  const [selectedJobId, setSelectedJobIdState] = useState(() => readStoredSelectedJobId())
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([])
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactContent | null>(null)
  const [artifactLoading, setArtifactLoading] = useState(false)
  const [artifactError, setArtifactError] = useState('')
  const [llmResponsePreviews, setLlmResponsePreviews] = useState<Record<string, LlmResponsePreview>>({})
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [submission, setSubmission] = useState<{ status: SubmissionStatus; command?: string; message?: string }>({
    status: 'idle',
  })
  const [workflowRunState, setWorkflowRunState] = useState<WorkflowRunState>('idle')
  const [busy, setBusy] = useState(false)
  const runtimeActive = isRuntimeActive(status)

  useEffect(() => {
    if (runtimeActive && workflowRunState !== 'confirming') {
      setWorkflowRunState('running')
      return
    }
    if (status?.status && !runtimeActive && workflowRunState === 'running') {
      setWorkflowRunState('idle')
    }
  }, [runtimeActive, status?.status, workflowRunState])

  function setSelectedJobId(jobId: string) {
    setSelectedJobIdState(jobId)
    rememberSelectedJobId(jobId)
  }

  async function refreshVisualization(jobId = '') {
    setVisualizationLoading(true)
    try {
      const payload = await fetchVisualization(jobId)
      setVisualization(normalizeVisualizationPayload(payload))
    } catch (error) {
      setVisualization(
        normalizeVisualizationPayload({
          status: 'waiting',
          warnings: [error instanceof Error ? error.message : 'Unable to load visualization data.'],
        }),
      )
    } finally {
      setVisualizationLoading(false)
    }
  }

  async function refreshArtifacts(jobId = '') {
    try {
      const nextArtifacts = await fetchArtifacts(jobId)
      setArtifacts(nextArtifacts)
      setArtifactError('')
      return nextArtifacts
    } catch (error) {
      setArtifactError(error instanceof Error ? error.message : '无法加载文件列表')
      return []
    }
  }

  async function selectArtifactPath(path: string) {
    if (!path) {
      return
    }
    setArtifactLoading(true)
    setArtifactError('')
    try {
      const detail = await fetchArtifactContent(path)
      setSelectedArtifact(detail)
      setState((current) => reduceDetailSelection(current, 'artifact', detail))
    } catch (error) {
      setArtifactError(error instanceof Error ? error.message : '无法加载文件内容')
    } finally {
      setArtifactLoading(false)
    }
  }

  function llmCallsFromData(
    nextStatus: JobStatus | null,
    nextEvents: RadAgentEvent[],
    nextArtifacts: ArtifactSummary[],
    selectedPath = '',
  ): LlmDebugCall[] {
    return createAgentCockpit({
      status: nextStatus,
      events: nextEvents,
      artifacts: nextArtifacts,
      selectedPath,
    }).llmDebugCalls
  }

  async function refreshLlmResponsePreviews(calls: LlmDebugCall[]) {
    const candidates = calls
      .filter((call) => call.artifactPath && call.artifactPath !== '未记录 artifact 路径')
      .slice(0, 5)
    if (candidates.length === 0) {
      setLlmResponsePreviews({})
      return
    }
    const entries = await Promise.all(
      candidates.map(async (call) => {
        try {
          const artifact = await fetchArtifactContent(call.artifactPath, 260_000)
          if (!artifact.exists) {
            return null
          }
          return [call.id, createLlmResponsePreview(artifact)] as const
        } catch {
          return null
        }
      }),
    )
    setLlmResponsePreviews(
      Object.fromEntries(
        entries.filter((entry): entry is readonly [string, LlmResponsePreview] => Boolean(entry)),
      ),
    )
  }

  useEffect(() => {
    let cancelled = false

    async function loadInitialData() {
      try {
        const [catalog, currentStatus, currentEvents] = await Promise.all([
          fetchCommandCatalog(),
          fetchStatus(),
          fetchEvents(),
        ])
        if (cancelled) {
          return
        }
        let initialJobId = selectedJobId || currentStatus.job_id
        if (!initialJobId) {
          const jobs = await sendCommand('/jobs').catch(() => null)
          const firstJob =
            jobs?.ok && Array.isArray(jobs.data) && jobs.data[0] && typeof jobs.data[0] === 'object'
              ? String((jobs.data[0] as { job_id?: unknown }).job_id || '')
              : ''
          initialJobId = firstJob
        }
        const currentVisualization = await fetchVisualization(initialJobId).catch(() => null)
        if (cancelled) {
          return
        }
        setCommands(catalog)
        setStatus(currentStatus)
        setSelectedJobId(initialJobId)
        setEvents(currentEvents)
        if (currentVisualization) {
          setVisualization(normalizeVisualizationPayload(currentVisualization))
        }
        const initialArtifacts = await refreshArtifacts(initialJobId)
        await refreshLlmResponsePreviews(llmCallsFromData(currentStatus, currentEvents, initialArtifacts))
        setState((current) => reduceEvents(current, currentEvents))
        setLoadState(`${catalog.length} 个功能可用`)
      } catch (error) {
        if (!cancelled) {
          setLoadState(error instanceof Error ? error.message : '工作台 API 不可用')
        }
      }
    }

    loadInitialData()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!launchTarget) {
      return
    }

    if (launchTarget.kind !== 'example') {
      return
    }
    setRunRequest(launchTarget.prompt)
    setLoadState(`示例已载入 ${launchTarget.exampleId}`)
    setState((current) => ({
      ...current,
      activeInspector: 'overview',
      timeline: [
        ...current.timeline,
        {
          id: `example:${launchTarget.exampleId}:${Date.now()}:${current.timeline.length}`,
          kind: 'system',
          title: '示例需求已载入',
          body: launchTarget.prompt,
          status: 'info',
          meta: launchTarget.exampleId,
        },
      ],
    }))
  }, [launchTarget])

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden) {
        return
      }
      Promise.all([fetchStatus(), fetchEvents()])
        .then(async ([nextStatus, nextEvents]) => {
          setStatus(nextStatus)
          setEvents(nextEvents)
          setState((current) => reduceEvents(current, nextEvents))
          const refreshJobId = selectedJobId || nextStatus.job_id
          if (!selectedJobId && nextStatus.job_id) {
            setSelectedJobId(nextStatus.job_id)
          }
          const nextArtifacts = await refreshArtifacts(refreshJobId)
          await refreshLlmResponsePreviews(
            llmCallsFromData(nextStatus, nextEvents, nextArtifacts, selectedArtifact?.path || ''),
          )
          try {
            const nextVisualization = await fetchVisualization(refreshJobId)
            setVisualization(normalizeVisualizationPayload(nextVisualization))
          } catch {
            // Keep the last rendered 3D payload during transient polling failures.
          }
        })
        .catch((error: unknown) => {
          setLoadState(error instanceof Error ? error.message : '轮询失败')
        })
    }, 2000)

    return () => window.clearInterval(timer)
  }, [selectedJobId])

  const activeData = state.activeInspector === 'status' ? status : state.inspectorData[state.activeInspector]
  const workbenchHero = createWorkbenchHero(status)
  const phaseTrack = createPhaseTrack(status)
  const cockpit = useMemo(
    () =>
      createAgentCockpit({
        status,
        events,
        artifacts,
        selectedPath: selectedArtifact?.path || '',
      }),
    [status, events, artifacts, selectedArtifact],
  )
  const submissionFeedback = useMemo(() => createSubmissionFeedback(submission), [submission])
  const workflowInstruction = runRequest.trim()
  const reviewCallout = createReviewCallout(status)
  const isWorkflowRunning = workflowRunState === 'running' || runtimeActive

  const controlSections = useMemo(() => createWorkbenchControlSections(commands), [commands])
  const quickActions = useMemo(
    () =>
      navItems.map((item) => ({
        label: item.label,
        labelEn: item.labelEn,
        active:
          item.labelEn === 'Run'
            ? workflowRunState === 'confirming' || isWorkflowRunning
            : state.activeInspector === item.inspector,
        onSelect: () => {
          if (item.labelEn === 'Run') {
            focusWorkflowConsole()
            return
          }
          if (item.command) {
            selectCommand(item.command)
          } else {
            setState((current) => ({ ...current, activeInspector: item.inspector }))
            setInspectorOpen(true)
          }
        },
      })),
    [state.activeInspector, workflowRunState, isWorkflowRunning],
  )
  const topQuickActions = quickActions.slice(0, 3)
  const bottomQuickActions = quickActions.slice(3)

  async function executeCommand(text: string, options: { workflow?: boolean } = {}) {
    const trimmed = text.trim()
    if (!trimmed || busy) {
      return
    }
    const commandName = trimmed.replace(/^\//, '').split(/\s+/)[0]
    setBusy(true)
    if (options.workflow) {
      setSubmission({ status: 'running', command: commandName })
    }
    setLoadState(`执行中 ${commandPresentation({ name: commandName, description: commandName }).primary}`)
    try {
      const result = await sendCommand(trimmed)
      setState((current) => reduceCommandResponse(current, result))
      const [nextStatus, nextEvents] = await Promise.all([fetchStatus(), fetchEvents()])
      setStatus(nextStatus)
      setEvents(nextEvents)
      const resultJobId =
        result.data && typeof result.data === 'object' && 'job_id' in result.data
          ? String((result.data as { job_id?: unknown }).job_id || '')
          : ''
      const refreshJobId = resultJobId || nextStatus.job_id || selectedJobId
      if (refreshJobId) {
        setSelectedJobId(refreshJobId)
      }
      await refreshVisualization(refreshJobId)
      const nextArtifacts = await refreshArtifacts(refreshJobId)
      await refreshLlmResponsePreviews(
        llmCallsFromData(nextStatus, nextEvents, nextArtifacts, selectedArtifact?.path || ''),
      )
      setState((current) => reduceEvents(current, nextEvents))
      setLoadState(result.ok ? `${result.command || '功能'} 已完成` : result.error || '执行失败')
      if (options.workflow) {
        if (result.ok) {
          setWorkflowRunState('running')
          setSubmission({
            status: 'running',
            command: result.command || commandName,
            message: '仿真工作流正在运行，状态已同步到侧边栏。',
          })
        } else {
          setWorkflowRunState('idle')
          setSubmission({
            status: 'error',
            command: result.command || commandName,
            message: result.error || '执行失败',
          })
        }
      } else {
        setLoadState(result.ok ? `${result.command || '功能'} 已完成` : result.error || '执行失败')
      }
    } catch (error) {
      setState((current) =>
        reduceCommandResponse(current, {
          ok: false,
          view: 'composer',
          command: commandName,
          error: error instanceof Error ? error.message : '执行失败',
        }),
      )
      const message = error instanceof Error ? error.message : '执行失败'
      setLoadState(message)
      if (options.workflow) {
        setSubmission({ status: 'error', command: commandName, message })
        setWorkflowRunState('idle')
      }
    } finally {
      setBusy(false)
    }
  }

  function submitComposer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    executeCommand(composerText)
  }

  function composeIntoComposer(command: string) {
    setComposerText(composeCommandTemplate(command))
  }

  function selectCommand(command: string) {
    composeIntoComposer(command)
    const nav = navItems.find((item) => item.command === command)
    if (nav) {
      setInspectorOpen(true)
      executeCommand(command)
    }
  }

  function executeNamedAction(name: string) {
    if (name === 'run') {
      requestWorkflowStart()
      return
    }
    executeCommand(`/${name}`)
  }

  function focusWorkflowConsole() {
    const consoleElement = document.getElementById('workflow-console')
    consoleElement?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    const input = document.getElementById('simulation-instruction')
    if (input instanceof HTMLTextAreaElement) {
      input.focus()
    }
  }

  function focusRuntimeProgress() {
    setState((current) => ({ ...current, activeInspector: 'status' }))
    setInspectorOpen(true)
    const debugPanel = document.getElementById('llm-debug-panel')
    if (debugPanel) {
      debugPanel.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    focusWorkflowConsole()
  }

  function requestWorkflowStart() {
    if (isWorkflowRunning) {
      focusRuntimeProgress()
      return
    }
    if (!workflowInstruction || busy) {
      return
    }
    setWorkflowRunState('confirming')
  }

  function cancelWorkflowStart() {
    setWorkflowRunState('idle')
  }

  function confirmWorkflowStart() {
    const command = buildRunCommand(workflowInstruction)
    if (!command) {
      setWorkflowRunState('idle')
      setSubmission({ status: 'idle' })
      return
    }
    setWorkflowRunState('running')
    setSubmission({ status: 'running', command: 'run' })
    setLoadState('仿真工作流正在运行')
    void executeCommand(command, { workflow: true })
  }

  function askCopilot(message: string) {
    executeCommand(`/chat ${message}`)
  }

  function executeReviewCommand(command: string) {
    const normalized = command.trim().toLowerCase()
    const opensConfirmationReview =
      normalized.startsWith('/confirm') &&
      !['/confirm approve', '/confirm approved', '/confirm yes', '/confirm y', '/confirm 确认', '/confirm 同意'].includes(
        normalized,
      )
    if (opensConfirmationReview) {
      setState((current) => ({ ...current, activeInspector: 'confirmation' }))
      setInspectorOpen(true)
    }
    executeCommand(command)
  }

  async function selectRecord(view: string, record: Record<string, unknown>) {
    try {
      if (view === 'jobs' && typeof record.job_id === 'string') {
        const detail = await fetchJobDetail(record.job_id)
        setSelectedJobId(record.job_id)
        setState((current) => reduceDetailSelection(current, 'job', detail))
        const nextArtifacts = await refreshArtifacts(record.job_id)
        await refreshLlmResponsePreviews(
          llmCallsFromData(status, events, nextArtifacts, selectedArtifact?.path || ''),
        )
        await refreshVisualization(record.job_id)
        setLoadState(`已切换到作业 ${record.job_id}`)
        return
      }
      if (view === 'artifacts' && typeof record.path === 'string') {
        await selectArtifactPath(record.path)
        return
      }
      setState((current) => reduceDetailSelection(current, view.slice(0, -1) || view, record))
    } catch (error) {
      setState((current) =>
        reduceCommandResponse(current, {
          ok: false,
          view: 'composer',
          command: view,
          error: error instanceof Error ? error.message : '无法加载详情',
        }),
      )
    }
  }

  async function saveModelConfig(update: ModelUpdatePayload) {
    try {
      const model = await updateModelConfig(update)
      setState((current) => reduceDetailSelection(current, 'model', model))
      setLoadState('模型配置已更新')
    } catch (error) {
      const message = error instanceof Error ? error.message : '无法更新模型配置'
      setState((current) =>
        reduceCommandResponse(current, {
          ok: false,
          view: 'model',
          command: 'model',
          error: message,
        }),
      )
      setLoadState(message)
      throw new Error(message)
    }
  }

  async function runModelHealthTest(): Promise<ModelHealthReport> {
    try {
      const health = await testModelHealth()
      setLoadState('模型健康测试已完成')
      return health
    } catch (error) {
      const message = error instanceof Error ? error.message : '模型健康测试失败'
      setState((current) =>
        reduceCommandResponse(current, {
          ok: false,
          view: 'model',
          command: 'model-health',
          error: message,
        }),
      )
      setLoadState(message)
      throw new Error(message)
    }
  }

  return (
    <main className="workbench-shell">
      <AgentStatusRail
        cockpit={cockpit}
        timeline={state.timeline}
        submissionFeedback={submissionFeedback}
        copilotDisabled={busy}
        onAskCopilot={askCopilot}
        onHome={onHome}
      />
      <section className="workbench-main">
        <header className="workbench-header">
          <div>
            <div className="eyebrow">{workbenchHero.eyebrow}</div>
            <h1>{workbenchHero.title}</h1>
            <p>{workbenchHero.subtitle}</p>
          </div>
          <div className="header-cluster">
            <div className={`status-pill workflow-status ${workbenchHero.statusTone}`}>
              <Activity size={16} />
              {workbenchHero.statusText}
            </div>
            <div className="status-pill">{loadState}</div>
            <button
              className="inspector-toggle"
              type="button"
              onClick={() => setInspectorOpen((current) => !current)}
              aria-expanded={inspectorOpen}
            >
              <PanelRightOpen size={16} />
              审查
            </button>
          </div>
        </header>

        <section className="workbench-command-strip" aria-label="工作区与工作台导航">
          <div className="center-command-top-row">
            <div className="center-workspace-metrics">
              <article>
                <span>文件变更</span>
                <strong>{cockpit.agent.changedFiles}</strong>
              </article>
              <article title={cockpit.agent.workspace}>
                <span>工作区</span>
                <strong>{compactWorkspaceLabel(cockpit.agent.workspace)}</strong>
              </article>
            </div>
            <nav className="center-quick-actions top" aria-label="Workbench primary actions">
              {topQuickActions.map((action) => (
                <button
                  className={action.active ? 'active' : ''}
                  type="button"
                  key={`${action.label}-${action.labelEn}`}
                  onClick={action.onSelect}
                >
                  <Activity size={15} />
                  <span>
                    <strong>{action.label}</strong>
                    <small>{action.labelEn}</small>
                  </span>
                </button>
              ))}
            </nav>
          </div>
          <nav className="center-quick-actions bottom" aria-label="Workbench secondary actions">
            {bottomQuickActions.map((action) => (
              <button
                className={action.active ? 'active' : ''}
                type="button"
                key={`${action.label}-${action.labelEn}`}
                onClick={action.onSelect}
              >
                <Activity size={15} />
                <span>
                  <strong>{action.label}</strong>
                  <small>{action.labelEn}</small>
                </span>
              </button>
            ))}
          </nav>
        </section>

        <section className="phase-track" aria-label="RadAgent 工作流阶段">
          {phaseTrack.map((phase) => (
            <div className={`phase-track-item ${phase.state}`} key={phase.id}>
              <span />
              <strong>{phase.label}</strong>
              <small>{phase.labelEn}</small>
            </div>
          ))}
        </section>

        <section className="agent-activity-panel" aria-label="Agent 活动状态">
          <div className="agent-activity-summary">
            <span className={workbenchHero.statusTone}>{cockpit.agent.stateLabel}</span>
            <strong>{cockpit.agent.phaseLabel}</strong>
            <p>{cockpit.agent.currentAction}</p>
            <div className="agent-status-chip-grid" aria-label="Agent 运行细节">
              {cockpit.agent.statusChips.map((chip) => (
                <small className={`agent-status-chip ${chip.tone}`} key={`${chip.label}-${chip.value}`}>
                  <span>{chip.label}</span>
                  <strong>{chip.value}</strong>
                </small>
              ))}
            </div>
          </div>
          <div className="agent-activity-feed">
            {cockpit.recentActivity.length > 0 ? (
              cockpit.recentActivity.map((item, index) => (
                <article key={`${item.title}-${item.phaseLabel}-${index}`}>
                  <CircleDot size={13} />
                  <div>
                    <strong>{item.title}</strong>
                    <span>
                      {item.statusLabel} · {item.phaseLabel}
                    </span>
                    {item.detail ? <p>{item.detail}</p> : null}
                  </div>
                </article>
              ))
            ) : (
              <p>等待 Agent 运行记录。</p>
            )}
          </div>
        </section>

        <LlmDebugPanel cockpit={cockpit} responsePreviews={llmResponsePreviews} />

        {reviewCallout ? (
          <section className="confirmation-callout" aria-live="polite">
            <div>
              <span>{reviewCallout.eyebrow}</span>
              <strong>{reviewCallout.title}</strong>
              <p>{reviewCallout.detail}</p>
            </div>
            <button type="button" onClick={() => executeReviewCommand(reviewCallout.primaryCommand)}>
              {reviewCallout.primaryLabel}
            </button>
            {reviewCallout.secondaryCommand ? (
              <button type="button" onClick={() => executeReviewCommand(reviewCallout.secondaryCommand || '')}>
                {reviewCallout.secondaryLabel}
              </button>
            ) : null}
          </section>
        ) : null}

        <Suspense fallback={<SimulationViewportFallback />}>
          <SimulationViewport
            payload={visualization}
            loading={visualizationLoading}
            reviewFocus={reviewCallout?.kind === 'human-confirmation'}
            onRefresh={() => refreshVisualization(selectedJobId || status?.job_id || '')}
          />
        </Suspense>

        <section className="timeline-panel">
          <div className="panel-title">
            <TerminalSquare size={18} />
            Agent 时间线
            <small>Auditable Timeline</small>
          </div>
          <div className="timeline-scroll">
            {state.timeline.map((row) => (
              <TimelineItem row={row} key={row.id} />
            ))}
          </div>
        </section>

        <section className="workflow-console" id="workflow-console" aria-label="仿真工作流控制台">
          <div className="workflow-direct-panel">
            <label className="workflow-instruction-field" htmlFor="simulation-instruction">
              <span>仿真指令</span>
              <textarea
                id="simulation-instruction"
                value={runRequest}
                rows={4}
                onChange={(event) => setRunRequest(event.target.value)}
                placeholder="输入要仿真的目标、几何条件、入射条件、材料约束、计分输出和报告要求"
              />
            </label>
            <div className="workflow-action-column">
              <button
                className={`workflow-start-button ${isWorkflowRunning ? 'running' : workflowRunState}`}
                type="button"
                title={
                  isWorkflowRunning
                    ? '查看当前仿真工作流进度'
                    : '确认后开始执行 RadAgent 仿真工作流'
                }
                onClick={requestWorkflowStart}
                disabled={!isWorkflowRunning && (busy || !workflowInstruction)}
              >
                {isWorkflowRunning ? <Activity size={15} /> : <Play size={15} />}
                <span>{isWorkflowRunning ? '查看进度' : '开始工作流'}</span>
                <small>{isWorkflowRunning ? 'Progress' : 'Start'}</small>
              </button>
            </div>
          </div>
          {workflowRunState === 'confirming' ? (
            <div className="workflow-confirm-backdrop" role="presentation">
              <section
                className="workflow-confirm-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="workflow-confirm-title"
              >
                <span>确认提交</span>
                <strong id="workflow-confirm-title">确认开始工作流</strong>
                <p>{workflowInstruction}</p>
                <div className="workflow-confirm-actions">
                  <button type="button" onClick={cancelWorkflowStart}>
                    取消
                  </button>
                  <button type="button" onClick={confirmWorkflowStart}>
                    开始
                  </button>
                </div>
              </section>
            </div>
          ) : null}
          <div className="workflow-request">
            <button
              className="primary-action"
              type="button"
              title={commandPresentation({ name: 'simulate', description: 'simulate', visible: true }).tip}
              onClick={() => executeCommand(buildSimulateCommand(simulationEvents))}
              disabled={busy}
            >
              <Play size={15} />
              <span>运行模拟</span>
              <small>{simulationEvents} events</small>
            </button>
            <label className="events-field">
              <span>事件数</span>
              <input
                type="number"
                min={1}
                value={simulationEvents}
                onChange={(event) => setSimulationEvents(Math.max(1, Number(event.target.value) || 1))}
              />
            </label>
          </div>
          <div className="control-section-grid">
            {controlSections.map((section) => (
              <div className="control-section" key={section.title}>
                <div className="control-section-heading">
                  <strong>{section.title}</strong>
                  <small>{section.subtitle}</small>
                </div>
                <div className="control-action-grid">
                  {section.actions.map((action) => (
                    <button
                      className={`control-action ${action.intent}`}
                      type="button"
                      key={action.name}
                      title={action.tip}
                      onClick={() =>
                        action.name === 'simulate'
                          ? executeCommand(buildSimulateCommand(simulationEvents))
                          : executeNamedAction(action.name)
                      }
                      disabled={busy}
                    >
                      <strong>{action.primary}</strong>
                      <small>{action.secondary}</small>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <details className="advanced-command">
            <summary>高级兼容入口 <span>Advanced</span></summary>
            <form className="composer" onSubmit={submitComposer}>
              <input
                aria-label="高级兼容命令"
                value={composerText}
                onChange={(event) => setComposerText(event.target.value)}
                placeholder="仅用于复现 TUI 内部指令或调试服务连接"
              />
              <button className="primary-button compact" type="submit" disabled={busy || !composerText.trim()}>
                <Send size={16} />
                {busy ? '执行中' : '发送'}
              </button>
            </form>
          </details>
        </section>
      </section>
      <ArtifactWorkspace
        cockpit={cockpit}
        selectedArtifact={selectedArtifact}
        loading={artifactLoading}
        error={artifactError}
        onSelectArtifact={selectArtifactPath}
        onOpenInspector={() => {
          setState((current) => ({
            ...current,
            activeInspector: selectedArtifact ? 'artifact' : current.activeInspector,
          }))
          setInspectorOpen(true)
        }}
      />
      <div className={`inspector-drawer${inspectorOpen ? ' open' : ''}`}>
        <button
          className="inspector-close"
          type="button"
          onClick={() => setInspectorOpen(false)}
          aria-label="关闭审查面板"
        >
          <X size={16} />
          关闭
        </button>
        <InspectorPanel
          active={state.activeInspector}
          data={activeData}
          commands={commands}
          status={status}
          events={events}
          onSelectCommand={composeIntoComposer}
          onSelectRecord={selectRecord}
          onSaveModelConfig={saveModelConfig}
          onTestModelHealth={runModelHealthTest}
          onExecuteCommand={executeCommand}
        />
      </div>
    </main>
  )
}
