import { AlertCircle, CheckCircle2, CircleDot, Database, FileText } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import type { CommandCatalogEntry, JobStatus, RadAgentEvent } from '../lib/api'
import { groupCommandCatalog } from '../lib/commands'
import { commandGroupPresentation, commandPresentation } from '../lib/commandPresentation'
import {
  buildAskMoreCommand,
  buildConfirmationCommand,
  buildRejectCommand,
} from '../lib/confirmationActions'
import {
  buildModelUpdate,
  createModelSaveState,
  createModelSettingsDraft,
  reduceModelSaveFailure,
  reduceModelSaveStart,
  reduceModelSaveSuccess,
  reduceModelViewRefresh,
  type ModelSettingsDraft,
  type ModelSaveState,
} from '../lib/modelSettings'
import { createCollectionPanel } from '../lib/collectionPanels'
import { createDetailPanel, isDetailPanelView } from '../lib/detailPanels'
import { createDomainPanel, isDomainPanelView } from '../lib/domainPanels'
import { createOperationPanel, isOperationPanelView } from '../lib/operationPanels'
import { createOverviewPanel } from '../lib/overviewPanel'

type InspectorPanelProps = {
  active: string
  data: unknown
  commands: CommandCatalogEntry[]
  status: JobStatus | null
  events: RadAgentEvent[]
  onSelectCommand: (command: string) => void
  onSelectRecord: (view: string, record: Record<string, unknown>) => void
  onSaveModelConfig: (update: ReturnType<typeof buildModelUpdate>) => Promise<void>
  onExecuteCommand: (command: string) => Promise<void>
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function renderJson(value: unknown) {
  return <pre className="json-preview">{JSON.stringify(value ?? {}, null, 2)}</pre>
}

function StatusPanel({ status }: { status: JobStatus | null }) {
  if (!status) {
    return <p className="empty-state">状态尚未加载。Status has not loaded yet.</p>
  }

  const phases = ['prepare_workspace', 'context', 'g4_modeling', 'g4_codegen', 'validation', 'report']

  return (
    <div className="inspector-stack">
      <article className="metric-tile">
        <span>活动作业 Active job</span>
        <strong>{status.job_id || '暂无活动作业'}</strong>
      </article>
      <article className="metric-tile">
        <span>状态 State</span>
        <strong>{status.status}</strong>
      </article>
      <div className="phase-list">
        {phases.map((phase, index) => {
          const completed = status.completed_phases.includes(phase)
          const current = status.current_phase === phase
          return (
            <div className="phase-row" key={phase}>
              {completed ? <CheckCircle2 size={16} /> : <CircleDot size={16} />}
              <span>{phase}</span>
              {current ? <em>当前</em> : <em>{index + 1}</em>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function OverviewPanel({
  status,
  events,
  commands,
  onExecuteCommand,
  onSelectCommand,
}: {
  status: JobStatus | null
  events: RadAgentEvent[]
  commands: CommandCatalogEntry[]
  onExecuteCommand: (command: string) => Promise<void>
  onSelectCommand: (command: string) => void
}) {
  const panel = createOverviewPanel({ status, events, commands })

  return (
    <div className="overview-panel">
      <header className="detail-header">
        <span>概览 Overview</span>
        <strong>{panel.title}</strong>
        <p>{panel.subtitle}</p>
      </header>
      <div className="operation-metrics">
        {panel.metrics.map((metric) => (
          <article className="metric-tile" key={`${metric.label}-${metric.value}`}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </div>
      {panel.alerts.length > 0 ? (
        <div className="overview-alerts">
          {panel.alerts.map((alert) => (
            <article className={`overview-alert ${alert.status}`} key={`${alert.title}-${alert.detail}`}>
              <strong>{alert.title}</strong>
              <p>{alert.detail}</p>
            </article>
          ))}
        </div>
      ) : null}
      <div className="overview-actions">
        {panel.actions.map((action) => (
          <button
            className={action.tone === 'primary' ? 'primary-action' : ''}
            type="button"
            key={action.command}
            onClick={() => {
              if (action.mode === 'compose') {
                onSelectCommand(action.command)
              } else {
                onExecuteCommand(action.command)
              }
            }}
            title={action.tip}
          >
            <span>{action.label}</span>
            <small>{action.labelEn}</small>
          </button>
        ))}
      </div>
      {panel.recentEvents.length > 0 ? (
        <section className="overview-events">
          <h3>最近活动 Recent activity</h3>
          {panel.recentEvents.map((event) => (
            <article className={`overview-event ${event.status}`} key={`${event.title}-${event.meta}-${event.detail}`}>
              <span>{event.status}</span>
              <div>
                <strong>{event.title}</strong>
                <p>{event.detail}</p>
              </div>
            </article>
          ))}
        </section>
      ) : null}
    </div>
  )
}

function CommandPanel({
  commands,
  onSelectCommand,
}: {
  commands: CommandCatalogEntry[]
  onSelectCommand: (command: string) => void
}) {
  const groups = groupCommandCatalog(commands)
  return (
    <div className="command-group-list">
      {groups.map((group) => {
        const groupLabel = commandGroupPresentation(group.label)
        return (
        <section className="command-group" key={group.label}>
          <h3>
            <span>{groupLabel.primary}</span>
            <small>{groupLabel.secondary}</small>
          </h3>
          <div className="command-list">
            {group.commands.map((command) => {
              const action = commandPresentation(command)
              return (
                <button
                  className="command-row button-row"
                  type="button"
                  key={command.name}
                  title={action.tip}
                  onClick={() => onSelectCommand(action.internalCommand)}
                >
                  <strong>{action.primary}</strong>
                  <span>{action.secondary}</span>
                  <p>{action.tip}</p>
                  {action.module ? <em>{action.module}</em> : null}
                </button>
              )
            })}
          </div>
        </section>
        )
      })}
    </div>
  )
}

function EventPanel({ events }: { events: RadAgentEvent[] }) {
  if (events.length === 0) {
    return <p className="empty-state">暂无服务事件。No service events yet.</p>
  }

  return (
    <div className="event-list">
      {events.slice(-16).reverse().map((event) => (
        <article className="event-row" key={`${event.created_at}-${event.event_type}-${event.summary}`}>
          <AlertCircle size={15} />
          <div>
            <strong>{event.event_type.replaceAll('_', ' ')}</strong>
            <p>{event.summary || event.phase || event.job_id || '服务事件'}</p>
          </div>
        </article>
      ))}
    </div>
  )
}

function CollectionPanel({
  active,
  data,
  onSelectRecord,
}: {
  active: string
  data: unknown
  onSelectRecord: (view: string, record: Record<string, unknown>) => void
}) {
  const panel = createCollectionPanel(active, data)
  if (!panel) {
    return renderJson(data)
  }
  if (panel.rows.length === 0) {
    return <p className="empty-state">暂无记录。No records available.</p>
  }
  return (
    <div className="collection-panel">
      <p className="collection-summary">{panel.summary}</p>
      <div className="record-list">
        {panel.rows.map((row, index) => {
          return (
            <button
              className="record-row button-row"
              type="button"
              key={`${row.title}-${row.meta}-${index}`}
              onClick={() => onSelectRecord(active, row.record)}
            >
              <Database size={16} />
              <div>
                <span>{row.status}</span>
                <strong>{row.title}</strong>
                {row.detail ? <p>{row.detail}</p> : null}
                {row.meta ? <em>{row.meta}</em> : null}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ArtifactPanel({ data }: { data: unknown }) {
  const artifact = asRecord(data)
  const text = typeof artifact.text === 'string' ? artifact.text : ''
  return (
    <div className="inspector-stack">
      <article className="metric-tile">
        <span>路径 Path</span>
        <strong>{String(artifact.path || '未选择产物')}</strong>
      </article>
      <article className="metric-tile">
        <span>类型 Kind</span>
        <strong>{String(artifact.kind || 'unknown')}</strong>
      </article>
      {text ? <pre className="artifact-preview">{text}</pre> : renderJson(data)}
    </div>
  )
}

function DetailPanelView({ active, data }: { active: string; data: unknown }) {
  const panel = createDetailPanel(active, data)
  if (!panel) {
    return renderJson(data)
  }

  return (
    <div className="detail-panel">
      <header className="detail-header">
        <span>{panel.status}</span>
        <strong>{panel.title}</strong>
        {panel.subtitle ? <p>{panel.subtitle}</p> : null}
      </header>
      {panel.metrics.length > 0 ? (
        <div className="operation-metrics">
          {panel.metrics.map((metric) => (
            <article className="metric-tile" key={`${metric.label}-${metric.value}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </article>
          ))}
        </div>
      ) : null}
      {panel.preview ? <pre className="artifact-preview compact-preview">{panel.preview}</pre> : null}
      {panel.sections.map((section) => (
        <section className="detail-section" key={section.title}>
          <h3>{section.title}</h3>
          {section.rows.map((row) => (
            <div className="detail-row" key={`${section.title}-${row.label}`}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}

function OperationPanelView({
  active,
  data,
  onSelectRecord,
}: {
  active: string
  data: unknown
  onSelectRecord: (view: string, record: Record<string, unknown>) => void
}) {
  const panel = createOperationPanel(active, data)
  if (!panel) {
    return renderJson(data)
  }

  return (
    <div className="operation-panel">
      {panel.summary ? <p className="operation-summary">{panel.summary}</p> : null}
      {panel.metrics.length > 0 ? (
        <div className="operation-metrics">
          {panel.metrics.map((metric) => (
            <article className="metric-tile" key={`${metric.label}-${metric.value}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </article>
          ))}
        </div>
      ) : null}
      {panel.preview ? <pre className="artifact-preview">{panel.preview}</pre> : null}
      {panel.artifacts.length > 0 ? (
        <div className="record-list compact">
          {panel.artifacts.map((artifact) => (
            <button
              className="record-row button-row"
              type="button"
              key={artifact.path}
              onClick={() => onSelectRecord('artifacts', artifact)}
            >
              <Database size={16} />
              <div>
                <strong>{artifact.path}</strong>
                <p>{[artifact.kind, artifact.stage].filter(Boolean).join(' · ')}</p>
              </div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function DomainPanelView({ active, data }: { active: string; data: unknown }) {
  const panel = createDomainPanel(active, data)
  if (!panel) {
    return renderJson(data)
  }

  return (
    <div className="domain-panel">
      {panel.summary ? <p className="operation-summary">{panel.summary}</p> : null}
      {panel.metrics.length > 0 ? (
        <div className="operation-metrics">
          {panel.metrics.map((metric) => (
            <article className="metric-tile" key={`${metric.label}-${metric.value}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </article>
          ))}
        </div>
      ) : null}
      {panel.rows.length > 0 ? (
        <div className="domain-row-list">
          {panel.rows.map((row) => (
            <article className="domain-row" key={`${row.title}-${row.status}-${row.meta}`}>
              <span>{row.status}</span>
              <div>
                <strong>{row.title}</strong>
                {row.detail ? <p>{row.detail}</p> : null}
                {row.meta ? <em>{row.meta}</em> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function ModelSettingsPanel({
  data,
  onSave,
}: {
  data: unknown
  onSave: (update: ReturnType<typeof buildModelUpdate>) => Promise<void>
}) {
  const [draft, setDraft] = useState<ModelSettingsDraft>(() => createModelSettingsDraft(data))
  const [saveState, setSaveState] = useState<ModelSaveState>(() => createModelSaveState())

  useEffect(() => {
    setDraft(createModelSettingsDraft(data))
    setSaveState((current) => reduceModelViewRefresh(current))
  }, [data])

  function updateField(key: keyof ModelSettingsDraft, value: string) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaveState((current) => reduceModelSaveStart(current))
    try {
      await onSave(buildModelUpdate(draft))
      const nextState = reduceModelSaveSuccess(saveState, draft)
      if (nextState.draft) {
        setDraft(nextState.draft)
      }
      setSaveState(nextState)
    } catch (error) {
      setSaveState((current) =>
        reduceModelSaveFailure(
          current,
          draft,
          error instanceof Error ? error.message : 'Unable to save model settings.',
        ),
      )
    } finally {
    }
  }

  return (
    <form className="model-settings-form" onSubmit={submit}>
      <label>
        <span>基础地址 Base URL</span>
        <input value={draft.base_url} onChange={(event) => updateField('base_url', event.target.value)} />
      </label>
      <label>
        <span>密钥环境变量 API key env</span>
        <input value={draft.api_key_env} onChange={(event) => updateField('api_key_env', event.target.value)} />
      </label>
      <label>
        <span>接口密钥 API key</span>
        <input
          value={draft.api_key}
          type="password"
          placeholder="只写 Write-only"
          onChange={(event) => updateField('api_key', event.target.value)}
        />
      </label>
      <label>
        <span>轻量模型 Lite model</span>
        <input value={draft.lite_model} onChange={(event) => updateField('lite_model', event.target.value)} />
      </label>
      <label>
        <span>专业模型 Pro model</span>
        <input value={draft.pro_model} onChange={(event) => updateField('pro_model', event.target.value)} />
      </label>
      <label>
        <span>最大模型 Max model</span>
        <input value={draft.max_model} onChange={(event) => updateField('max_model', event.target.value)} />
      </label>
      {saveState.message ? (
        <p className={`model-save-message ${saveState.status}`}>{saveState.message}</p>
      ) : null}
      <button type="submit" disabled={saveState.status === 'saving'}>
        {saveState.status === 'saving' ? '保存中' : '保存模型设置'}
      </button>
    </form>
  )
}

function ConfirmationPanel({
  data,
  onExecuteCommand,
}: {
  data: unknown
  onExecuteCommand: (command: string) => Promise<void>
}) {
  const review = asRecord(data)
  const [rejectReason, setRejectReason] = useState('')
  const [question, setQuestion] = useState('')
  const preview = typeof review.preview === 'string' ? review.preview : ''
  const status = String(review.status || 'unknown')

  function run(command: string) {
    if (command) {
      onExecuteCommand(command)
    }
  }

  return (
    <div className="confirmation-panel">
      <article className="metric-tile">
        <span>状态 Status</span>
        <strong>{status || '未加载确认项'}</strong>
      </article>
      {preview ? <pre className="artifact-preview">{preview}</pre> : <p className="empty-state">暂无确认预览。No confirmation preview available.</p>}
      <div className="confirmation-actions">
        <button type="button" className="approve-button" onClick={() => run(buildConfirmationCommand())}>
          批准
        </button>
        <label>
          <span>拒绝原因 Reject reason</span>
          <textarea value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
        </label>
        <button type="button" onClick={() => run(buildRejectCommand(rejectReason))} disabled={!rejectReason.trim()}>
          拒绝
        </button>
        <label>
          <span>追问 Ask for more</span>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
        </label>
        <button type="button" onClick={() => run(buildAskMoreCommand(question))} disabled={!question.trim()}>
          追问
        </button>
      </div>
    </div>
  )
}

export default function InspectorPanel({
  active,
  data,
  commands,
  status,
  events,
  onSelectCommand,
  onSelectRecord,
  onSaveModelConfig,
  onExecuteCommand,
}: InspectorPanelProps) {
  const title = active.replaceAll('-', ' ')
  const operationActive =
    isOperationPanelView(active) || (active === 'artifacts' && Array.isArray(asRecord(data).artifacts))
  const detailActive =
    isDetailPanelView(active) || (active === 'projects' && !Array.isArray(data) && Object.keys(asRecord(data)).length > 0)
  const detailView = active === 'projects' ? 'project' : active

  return (
    <aside className="inspector">
      <div className="panel-title">
        <FileText size={16} />
        {title}
      </div>
      {active === 'overview' ? (
        <OverviewPanel
          status={status}
          events={events}
          commands={commands}
          onSelectCommand={onSelectCommand}
          onExecuteCommand={onExecuteCommand}
        />
      ) : null}
      {active === 'status' ? <StatusPanel status={status} /> : null}
      {active === 'artifact' ? <ArtifactPanel data={data} /> : null}
      {detailActive ? <DetailPanelView active={detailView} data={data} /> : null}
      {active === 'model' ? <ModelSettingsPanel data={data} onSave={onSaveModelConfig} /> : null}
      {active === 'confirmation' ? (
        <ConfirmationPanel data={data} onExecuteCommand={onExecuteCommand} />
      ) : null}
      {active === 'help' ? <CommandPanel commands={commands} onSelectCommand={onSelectCommand} /> : null}
      {active === 'logs' ? <EventPanel events={events} /> : null}
      {isDomainPanelView(active) ? <DomainPanelView active={active} data={data} /> : null}
      {operationActive ? (
        <OperationPanelView active={active} data={data} onSelectRecord={onSelectRecord} />
      ) : null}
      {!operationActive && !detailActive && ['jobs', 'artifacts', 'gates', 'projects', 'revisions'].includes(active) ? (
        <CollectionPanel active={active} data={data} onSelectRecord={onSelectRecord} />
      ) : null}
      {![
        'status',
        'overview',
        'artifact',
        ...['job', 'gate', 'revision', 'project'],
        'model',
        'confirmation',
        'help',
        'logs',
        ...['tools', 'credibility', 'memory'],
        ...['build', 'simulation', 'workbench', 'visual-review', 'report', 'demo', 'mode', 'history', 'exit'],
        'jobs',
        'artifacts',
        'gates',
        'projects',
        'revisions',
      ].includes(active)
        ? renderJson(data)
        : null}
    </aside>
  )
}
