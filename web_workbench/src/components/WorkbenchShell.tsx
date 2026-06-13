import {
  Activity,
  Archive,
  Boxes,
  ClipboardCheck,
  FileCode2,
  Gauge,
  Home,
  LayoutDashboard,
  Play,
  Send,
  Settings,
  TerminalSquare,
} from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import {
  fetchCommandCatalog,
  fetchArtifactContent,
  fetchEvents,
  fetchJobDetail,
  fetchStatus,
  sendCommand,
  updateModelConfig,
  type CommandCatalogEntry,
  type JobStatus,
  type RadAgentEvent,
  type ModelUpdatePayload,
} from '../lib/api'
import { buildRunCommand, buildSimulateCommand, composeCommandTemplate } from '../lib/commandAssist'
import { commandPresentation } from '../lib/commandPresentation'
import {
  createInitialWorkbenchState,
  reduceCommandResponse,
  reduceDetailSelection,
  reduceEvents,
  type TimelineRow,
  type WorkbenchState,
} from '../lib/workbenchState'
import type { HomeLaunchTarget } from '../lib/homeNavigation'
import InspectorPanel from './InspectorPanel'

type WorkbenchShellProps = {
  onHome: () => void
  launchTarget?: HomeLaunchTarget | null
}

const navItems = [
  { label: '概览', labelEn: 'Overview', command: '', inspector: 'overview', icon: LayoutDashboard },
  { label: '运行', labelEn: 'Run', command: '/help', inspector: 'help', icon: Play },
  { label: '状态', labelEn: 'Status', command: '/status', inspector: 'status', icon: Gauge },
  { label: '作业', labelEn: 'Jobs', command: '/jobs', inspector: 'jobs', icon: Boxes },
  { label: '产物', labelEn: 'Artifacts', command: '/artifacts', inspector: 'artifacts', icon: Archive },
  { label: '门禁', labelEn: 'Gates', command: '/gates', inspector: 'gates', icon: ClipboardCheck },
  { label: '日志', labelEn: 'Logs', command: '/logs', inspector: 'logs', icon: FileCode2 },
  { label: '模型', labelEn: 'Model', command: '/model', inspector: 'model', icon: Settings },
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
      <summary>详情 Details</summary>
      <pre>{text.length > 2400 ? `${text.slice(0, 2400)}...` : text}</pre>
    </details>
  )
}

export default function WorkbenchShell({ onHome, launchTarget = null }: WorkbenchShellProps) {
  const [commands, setCommands] = useState<CommandCatalogEntry[]>([])
  const [status, setStatus] = useState<JobStatus | null>(null)
  const [events, setEvents] = useState<RadAgentEvent[]>([])
  const [state, setState] = useState<WorkbenchState>(() => createInitialWorkbenchState())
  const [composerText, setComposerText] = useState('')
  const [runRequest, setRunRequest] = useState('构建一个 Geant4 探测器仿真')
  const [simulationEvents, setSimulationEvents] = useState(1000)
  const [loadState, setLoadState] = useState('连接中 Connecting')
  const [busy, setBusy] = useState(false)

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
        setCommands(catalog)
        setStatus(currentStatus)
        setEvents(currentEvents)
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
        .then(([nextStatus, nextEvents]) => {
          setStatus(nextStatus)
          setEvents(nextEvents)
          setState((current) => reduceEvents(current, nextEvents))
        })
        .catch((error: unknown) => {
          setLoadState(error instanceof Error ? error.message : '轮询失败')
        })
    }, 2000)

    return () => window.clearInterval(timer)
  }, [])

  const activeData = state.activeInspector === 'status' ? status : state.inspectorData[state.activeInspector]
  const projectLabel = String(status?.state.project_slug || status?.workspace_root || 'simulation_workspace')
  const phaseLabel = status?.current_phase || 'prepare_workspace'

  const quickCommands = useMemo(
    () =>
      commands.filter(
        (command) =>
          command.visible &&
          ['run', 'status', 'jobs', 'artifacts', 'gates', 'logs', 'model'].includes(command.name),
      ),
    [commands],
  )

  async function executeCommand(text: string) {
    const trimmed = text.trim()
    if (!trimmed || busy) {
      return
    }
    setBusy(true)
    setLoadState(`执行中 ${trimmed.replace(/^\//, '')}`)
    try {
      const result = await sendCommand(trimmed)
      setState((current) => reduceCommandResponse(current, result))
      const [nextStatus, nextEvents] = await Promise.all([fetchStatus(), fetchEvents()])
      setStatus(nextStatus)
      setEvents(nextEvents)
      setState((current) => reduceEvents(current, nextEvents))
      setLoadState(result.ok ? `${result.command || '功能'} 已完成` : result.error || '执行失败')
    } catch (error) {
      setState((current) =>
        reduceCommandResponse(current, {
          ok: false,
          view: 'composer',
          command: trimmed.replace(/^\//, '').split(/\s+/)[0],
          error: error instanceof Error ? error.message : '执行失败',
        }),
      )
      setLoadState(error instanceof Error ? error.message : '执行失败')
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
      executeCommand(command)
    }
  }

  function executeNamedAction(name: string) {
    if (name === 'run') {
      executeCommand(buildRunCommand(runRequest))
      return
    }
    executeCommand(`/${name}`)
  }

  async function selectRecord(view: string, record: Record<string, unknown>) {
    try {
      if (view === 'jobs' && typeof record.job_id === 'string') {
        const detail = await fetchJobDetail(record.job_id)
        setState((current) => reduceDetailSelection(current, 'job', detail))
        return
      }
      if (view === 'artifacts' && typeof record.path === 'string') {
        const detail = await fetchArtifactContent(record.path)
        setState((current) => reduceDetailSelection(current, 'artifact', detail))
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
      <aside className="workbench-sidebar">
        <button className="icon-button" type="button" onClick={onHome} aria-label="返回首页">
          <Home size={18} />
        </button>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon
            const active = state.activeInspector === item.inspector
            return (
              <button
                className={`nav-button${active ? ' active' : ''}`}
                type="button"
                key={item.label}
                onClick={() => {
                  if (item.command) {
                    selectCommand(item.command)
                  } else {
                    setState((current) => ({ ...current, activeInspector: item.inspector }))
                  }
                }}
              >
                <Icon size={16} />
                <span className="nav-label">
                  <strong>{item.label}</strong>
                  <small>{item.labelEn}</small>
                </span>
              </button>
            )
          })}
        </nav>
      </aside>
      <section className="workbench-main">
        <header className="workbench-header">
          <div>
            <div className="eyebrow">{projectLabel}</div>
            <h1>RadAgent 工作台</h1>
          </div>
          <div className="header-cluster">
            <div className="status-pill">
              <Activity size={16} />
              {status?.status || 'idle'} · {phaseLabel}
            </div>
            <div className="status-pill">{loadState}</div>
          </div>
        </header>

        <section className="timeline-panel">
          <div className="panel-title">
            <TerminalSquare size={18} />
            历史记录 Timeline
          </div>
          {state.timeline.map((row) => (
            <article className={`timeline-row ${row.status}`} key={row.id}>
              <span className="timeline-dot" />
              <div>
                <strong>{row.title}</strong>
                {row.meta ? <em>{row.meta}</em> : null}
                {timelineBody(row)}
                {timelineDetails(row)}
              </div>
            </article>
          ))}
        </section>

        <details className="advanced-command">
          <summary>高级命令 <span>Advanced</span></summary>
          <form className="composer" onSubmit={submitComposer}>
            <input
              aria-label="高级命令 Advanced command"
              value={composerText}
              onChange={(event) => setComposerText(event.target.value)}
              placeholder="内部命令，仅用于调试或兼容 TUI"
            />
            <button className="primary-button compact" type="submit" disabled={busy || !composerText.trim()}>
              <Send size={16} />
              {busy ? '执行中' : '发送'}
            </button>
          </form>
        </details>

        <div className="quick-command-strip" aria-label="快捷操作 Quick actions">
          {quickCommands.map((command) => (
            <button
              type="button"
              key={command.name}
              title={commandPresentation(command).tip}
              onClick={() => executeNamedAction(command.name)}
            >
              <strong>{commandPresentation(command).primary}</strong>
              <small>{commandPresentation(command).secondary}</small>
            </button>
          ))}
        </div>
        <section className="command-assist" aria-label="工作流选型 Workflow controls">
          <label>
            <span>运行需求 Run request</span>
            <input value={runRequest} onChange={(event) => setRunRequest(event.target.value)} />
          </label>
          <button type="button" onClick={() => executeCommand(buildRunCommand(runRequest))} disabled={busy || !runRequest.trim()}>
            <Play size={15} />
            开始
          </button>
          <button type="button" onClick={() => executeCommand('/build')} disabled={busy}>
            构建
          </button>
          <label className="events-field">
            <span>事件数 Events</span>
            <input
              type="number"
              min={1}
              value={simulationEvents}
              onChange={(event) => setSimulationEvents(Math.max(1, Number(event.target.value) || 1))}
            />
          </label>
          <button type="button" onClick={() => executeCommand(buildSimulateCommand(simulationEvents))} disabled={busy}>
            模拟
          </button>
          <button type="button" onClick={() => executeCommand('/confirm')} disabled={busy}>
            确认
          </button>
        </section>
      </section>
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
    </main>
  )
}
