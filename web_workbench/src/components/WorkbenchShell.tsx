import {
  Activity,
  Home,
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
  updateModelConfig,
  type ArtifactContent,
  type ArtifactSummary,
  type CommandCatalogEntry,
  type JobStatus,
  type RadAgentEvent,
  type ModelUpdatePayload,
} from '../lib/api'
import { buildRunCommand, buildSimulateCommand, composeCommandTemplate } from '../lib/commandAssist'
import { commandPresentation } from '../lib/commandPresentation'
import {
  buildSimulationPresetPrompt,
  createSimulationPresetSummary,
  defaultSimulationPresetSelection,
  simulationPresetGroups,
  type SimulationPresetSelection,
} from '../lib/simulationPresets'
import { createSubmissionFeedback, type SubmissionStatus } from '../lib/submissionFeedback'
import { createWorkbenchControlSections } from '../lib/workbenchControls'
import {
  createAgentCockpit,
  createPhaseTrack,
  createWorkbenchHero,
  presentTimelineRow,
} from '../lib/workbenchPresentation'
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
import PresetTaskPreview from './PresetTaskPreview'
import SimulationViewportFallback from './SimulationViewportFallback'

const SimulationViewport = lazy(() => import('./SimulationViewport'))

type WorkbenchShellProps = {
  onHome: () => void
  launchTarget?: HomeLaunchTarget | null
}

const navItems = [
  { label: '概览', labelEn: 'Overview', command: '', inspector: 'overview', icon: Activity },
  { label: '运行', labelEn: 'Run', command: '/help', inspector: 'help', icon: Play },
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
  const [runRequest, setRunRequest] = useState('重点评估屏蔽后硅敏感体剂量')
  const [presetSelection, setPresetSelection] = useState<SimulationPresetSelection>(defaultSimulationPresetSelection)
  const [simulationEvents, setSimulationEvents] = useState(1000)
  const [loadState, setLoadState] = useState('连接中')
  const [visualization, setVisualization] = useState<VisualizationPayload | null>(null)
  const [visualizationLoading, setVisualizationLoading] = useState(false)
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([])
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactContent | null>(null)
  const [artifactLoading, setArtifactLoading] = useState(false)
  const [artifactError, setArtifactError] = useState('')
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [submission, setSubmission] = useState<{ status: SubmissionStatus; command?: string; message?: string }>({
    status: 'idle',
  })
  const [busy, setBusy] = useState(false)

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

  useEffect(() => {
    let cancelled = false

    async function loadInitialData() {
      try {
        const [catalog, currentStatus, currentEvents, currentVisualization] = await Promise.all([
          fetchCommandCatalog(),
          fetchStatus(),
          fetchEvents(),
          fetchVisualization().catch(() => null),
        ])
        if (cancelled) {
          return
        }
        setCommands(catalog)
        setStatus(currentStatus)
        setEvents(currentEvents)
        if (currentVisualization) {
          setVisualization(normalizeVisualizationPayload(currentVisualization))
        }
        await refreshArtifacts(currentStatus.job_id)
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
    setComposerText(composeCommandTemplate('/run'))
    setLoadState(`示例已载入 ${launchTarget.exampleId}`)
    setState((current) => ({
      ...current,
      activeInspector: 'help',
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
          await refreshArtifacts(nextStatus.job_id)
          try {
            const nextVisualization = await fetchVisualization(nextStatus.job_id)
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
  }, [])

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
  const generatedRunRequest = useMemo(
    () => buildSimulationPresetPrompt(presetSelection, runRequest),
    [presetSelection, runRequest],
  )
  const presetSummary = useMemo(
    () => createSimulationPresetSummary(presetSelection, runRequest),
    [presetSelection, runRequest],
  )
  const submissionFeedback = useMemo(() => createSubmissionFeedback(submission), [submission])

  const controlSections = useMemo(() => createWorkbenchControlSections(commands), [commands])
  const quickActions = useMemo(
    () =>
      navItems.map((item) => ({
        label: item.label,
        labelEn: item.labelEn,
        active: state.activeInspector === item.inspector,
        onSelect: () => {
          if (item.command) {
            selectCommand(item.command)
          } else {
            setState((current) => ({ ...current, activeInspector: item.inspector }))
            setInspectorOpen(true)
          }
        },
      })),
    [state.activeInspector],
  )

  async function executeCommand(text: string) {
    const trimmed = text.trim()
    if (!trimmed || busy) {
      return
    }
    const commandName = trimmed.replace(/^\//, '').split(/\s+/)[0]
    setBusy(true)
    setSubmission({ status: 'running', command: commandName })
    setLoadState(`执行中 ${commandPresentation({ name: commandName, description: commandName }).primary}`)
    try {
      const result = await sendCommand(trimmed)
      setState((current) => reduceCommandResponse(current, result))
      const [nextStatus, nextEvents] = await Promise.all([fetchStatus(), fetchEvents()])
      setStatus(nextStatus)
      setEvents(nextEvents)
      await refreshVisualization(nextStatus.job_id)
      await refreshArtifacts(nextStatus.job_id)
      setState((current) => reduceEvents(current, nextEvents))
      setLoadState(result.ok ? `${result.command || '功能'} 已完成` : result.error || '执行失败')
      setSubmission({
        status: result.ok ? 'success' : 'error',
        command: result.command || commandName,
        message: result.ok ? undefined : result.error || '执行失败',
      })
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
      setSubmission({ status: 'error', command: commandName, message })
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
      executeCommand(buildRunCommand(generatedRunRequest))
      return
    }
    executeCommand(`/${name}`)
  }

  function updatePreset(kind: keyof SimulationPresetSelection, id: string) {
    setPresetSelection((current) => ({ ...current, [kind]: id }))
  }

  async function selectRecord(view: string, record: Record<string, unknown>) {
    try {
      if (view === 'jobs' && typeof record.job_id === 'string') {
        const detail = await fetchJobDetail(record.job_id)
        setState((current) => reduceDetailSelection(current, 'job', detail))
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

  return (
    <main className="workbench-shell">
      <AgentStatusRail cockpit={cockpit} quickActions={quickActions} onHome={onHome} />
      <section className="workbench-main">
        <header className="workbench-header">
          <div>
            <div className="eyebrow">{workbenchHero.eyebrow}</div>
            <h1>{workbenchHero.title}</h1>
            <p>{workbenchHero.subtitle}</p>
          </div>
          <div className="header-cluster">
            <div className="status-pill">
              <Activity size={16} />
              {workbenchHero.statusText}
            </div>
            <div className="status-pill">{workbenchHero.modeText}</div>
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

        <section className="phase-track" aria-label="RadAgent 工作流阶段">
          {phaseTrack.map((phase) => (
            <div className={`phase-track-item ${phase.state}`} key={phase.id}>
              <span />
              <strong>{phase.label}</strong>
              <small>{phase.labelEn}</small>
            </div>
          ))}
        </section>

        <Suspense fallback={<SimulationViewportFallback />}>
          <SimulationViewport
            payload={visualization}
            loading={visualizationLoading}
            onRefresh={() => refreshVisualization(status?.job_id || '')}
          />
        </Suspense>

        <section className="timeline-panel">
          <div className="panel-title">
            <TerminalSquare size={18} />
            Agent 时间线
            <small>Auditable Timeline</small>
          </div>
          {state.timeline.map((row) => (
            <TimelineItem row={row} key={row.id} />
          ))}
        </section>

        <section className="workflow-console" aria-label="仿真工作流控制台">
          <div className="preset-control-grid" aria-label="仿真任务选型">
            {simulationPresetGroups.map((group) => (
              <fieldset className="preset-control-group" key={group.kind}>
                <legend>
                  {group.label}
                  <small>{group.labelEn}</small>
                </legend>
                <div className="preset-option-list">
                  {group.options.map((option) => (
                    <button
                      className={presetSelection[group.kind] === option.id ? 'active' : ''}
                      type="button"
                      key={option.id}
                      title={option.description}
                      onClick={() => updatePreset(group.kind, option.id)}
                    >
                      <strong>{option.label}</strong>
                      <small>{option.labelEn}</small>
                    </button>
                  ))}
                </div>
              </fieldset>
            ))}
          </div>
          <PresetTaskPreview summary={presetSummary} fullPrompt={generatedRunRequest} />
          <div className="workflow-request">
            <label>
              <span>补充要求</span>
              <input value={runRequest} onChange={(event) => setRunRequest(event.target.value)} />
            </label>
            <label className="events-field">
              <span>粒子事件</span>
              <input
                type="number"
                min={1}
                value={simulationEvents}
                onChange={(event) => setSimulationEvents(Math.max(1, Number(event.target.value) || 1))}
              />
            </label>
            <button
              className="primary-action"
              type="button"
              title={commandPresentation({ name: 'run', description: 'run', visible: true }).tip}
              onClick={() => executeCommand(buildRunCommand(generatedRunRequest))}
              disabled={busy || !generatedRunRequest.trim()}
            >
              <Play size={15} />
              <span>启动 Agent</span>
              <small>Start</small>
            </button>
            <div className={`submission-feedback ${submissionFeedback.tone}`} role="status">
              <strong>{submissionFeedback.title}</strong>
              <span>{submissionFeedback.detail}</span>
            </div>
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
          onExecuteCommand={executeCommand}
        />
      </div>
    </main>
  )
}
