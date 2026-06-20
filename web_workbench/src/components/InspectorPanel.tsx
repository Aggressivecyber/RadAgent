import { AlertCircle, CheckCircle2, CircleDot, Database, FileText } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import type { CommandCatalogEntry, JobStatus, ModelHealthReport, RadAgentEvent } from '../lib/api'
import { groupCommandCatalog } from '../lib/commands'
import { commandGroupPresentation, commandPresentation } from '../lib/commandPresentation'
import {
  buildAskMoreCommand,
  buildConfirmationCommand,
  buildRejectCommand,
} from '../lib/confirmationActions'
import {
  buildQuestionCardSupplement,
  createConfirmationReviewView,
  type ConfirmationQuestionAnswer,
} from '../lib/confirmationReview'
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
import { createStatusPanelSummary, presentConfirmationStatus } from '../lib/workbenchPresentation'

type InspectorPanelProps = {
  active: string
  data: unknown
  commands: CommandCatalogEntry[]
  status: JobStatus | null
  events: RadAgentEvent[]
  onSelectCommand: (command: string) => void
  onSelectRecord: (view: string, record: Record<string, unknown>) => void
  onSaveModelConfig: (update: ReturnType<typeof buildModelUpdate>) => Promise<void>
  onTestModelHealth: () => Promise<ModelHealthReport>
  onExecuteCommand: (command: string) => Promise<void>
}

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

const inspectorTitles: Record<string, { label: string; labelEn: string }> = {
  overview: { label: '概览', labelEn: 'Overview' },
  help: { label: '功能选择', labelEn: 'Actions' },
  status: { label: '状态', labelEn: 'Status' },
  jobs: { label: '作业', labelEn: 'Jobs' },
  job: { label: '作业详情', labelEn: 'Job' },
  artifacts: { label: '产物', labelEn: 'Artifacts' },
  artifact: { label: '产物详情', labelEn: 'Artifact' },
  gates: { label: '门禁', labelEn: 'Gates' },
  gate: { label: '门禁详情', labelEn: 'Gate' },
  logs: { label: '日志', labelEn: 'Logs' },
  model: { label: '模型设置', labelEn: 'Model' },
  confirmation: { label: '参数核对', labelEn: 'Requirements' },
  diagnosis: { label: '诊断', labelEn: 'Workflow diagnosis' },
  memory: { label: '工作记忆', labelEn: 'Memory' },
  credibility: { label: '可信度', labelEn: 'Credibility' },
  revisions: { label: '修订', labelEn: 'Revisions' },
  revision: { label: '修订详情', labelEn: 'Revision' },
  projects: { label: '项目', labelEn: 'Projects' },
  project: { label: '项目详情', labelEn: 'Project' },
}

function inspectorTitle(active: string) {
  return inspectorTitles[active] || {
    label: active.replaceAll('-', ' '),
    labelEn: '',
  }
}

function renderJson(value: unknown) {
  return <pre className="json-preview">{JSON.stringify(value ?? {}, null, 2)}</pre>
}

function StatusPanel({ status }: { status: JobStatus | null }) {
  if (!status) {
    return <p className="empty-state">状态尚未加载。</p>
  }

  const summary = createStatusPanelSummary(status)

  return (
    <div className="inspector-stack">
      {summary.metrics.map((metric) => (
        <article className="metric-tile" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </article>
      ))}
      <div className="phase-list">
        {summary.phases.map((phase, index) => {
          return (
            <div className={`phase-row ${phase.state}`} key={phase.id}>
              {phase.state === 'done' ? <CheckCircle2 size={16} /> : <CircleDot size={16} />}
              <span>{phase.label}</span>
              <em>{phase.marker || index + 1}</em>
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
        <span>概览 <small>Overview</small></span>
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
          {panel.recentEvents.map((event, index) => (
            <article className={`overview-event ${event.status}`} key={`${event.title}-${event.meta}-${event.detail}-${index}`}>
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
    return <p className="empty-state">暂无服务事件。</p>
  }

  return (
    <div className="event-list">
      {events.slice(-16).reverse().map((event, index) => (
        <article className="event-row" key={`${event.created_at}-${event.event_type}-${event.summary}-${index}`}>
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
    return <p className="empty-state">暂无记录。</p>
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
        <span>路径</span>
        <strong>{String(artifact.path || '未选择产物')}</strong>
      </article>
      <article className="metric-tile">
        <span>类型</span>
        <strong>{String(artifact.kind || '未知')}</strong>
      </article>
      {text ? <pre className="artifact-preview">{text}</pre> : renderJson(data)}
    </div>
  )
}

function DiagnosisPanel({ data }: { data: unknown }) {
  const diagnosis = asRecord(data)
  const allowedActions = asArray(diagnosis.allowed_actions).map((item) => text(item)).filter(Boolean)
  const artifacts = asArray(diagnosis.artifacts).map((item) => text(item)).filter(Boolean)
  const hardRules = asRecord(diagnosis.hard_rules)
  const actionable = diagnosis.confirmation_actionable === true
  const modelEnhanced = diagnosis.model_enhanced === true
  const severity = text(diagnosis.severity, 'info')

  return (
    <div className={`diagnosis-panel ${severity}`}>
      <section className="confirmation-summary-card">
        <span>{modelEnhanced ? 'Lite 模型辅助说明' : '规则诊断'}</span>
        <strong>{text(diagnosis.user_message, '当前没有可用诊断。')}</strong>
        <p>{text(diagnosis.blocking_reason, '未检测到明确阻塞原因。')}</p>
      </section>
      <div className="operation-metrics">
        <article className="metric-tile">
          <span>阶段</span>
          <strong>{text(diagnosis.phase, '未知')}</strong>
        </article>
        <article className="metric-tile">
          <span>审批状态</span>
          <strong>{actionable ? '可审批' : '不可审批'}</strong>
        </article>
        <article className="metric-tile">
          <span>状态</span>
          <strong>{text(diagnosis.ui_state, 'unknown').replaceAll('_', ' ')}</strong>
        </article>
      </div>
      <section className="confirmation-review-section">
        <h3>下一步</h3>
        <p>{text(diagnosis.next_step_hint, '查看状态和日志确认下一步。')}</p>
      </section>
      {allowedActions.length > 0 ? (
        <section className="confirmation-review-section">
          <h3>允许动作</h3>
          {allowedActions.map((action) => (
            <article key={action}>
              <span>action</span>
              <strong>{action}</strong>
            </article>
          ))}
        </section>
      ) : null}
      {Object.keys(hardRules).length > 0 ? (
        <section className="confirmation-review-section">
          <h3>硬规则</h3>
          {Object.entries(hardRules).map(([key, value]) => (
            <article key={key}>
              <span>{key}</span>
              <strong>{text(value, 'false')}</strong>
            </article>
          ))}
        </section>
      ) : null}
      {artifacts.length > 0 ? (
        <section className="confirmation-review-section">
          <h3>相关产物</h3>
          {artifacts.map((artifact) => (
            <p key={artifact}>{artifact}</p>
          ))}
        </section>
      ) : null}
    </div>
  )
}

function DetailPanelView({
  active,
  data,
  onExecuteCommand,
}: {
  active: string
  data: unknown
  onExecuteCommand: (command: string) => Promise<void>
}) {
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
      {panel.actions.length > 0 ? (
        <div className="detail-actions">
          {panel.actions.map((action) => (
            <button
              className={action.intent === 'primary' ? 'primary' : ''}
              type="button"
              key={action.command}
              onClick={() => onExecuteCommand(action.command)}
            >
              <span>{action.label}</span>
              <small>{action.labelEn}</small>
            </button>
          ))}
        </div>
      ) : null}
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
  onTestHealth,
}: {
  data: unknown
  onSave: (update: ReturnType<typeof buildModelUpdate>) => Promise<void>
  onTestHealth: () => Promise<ModelHealthReport>
}) {
  const [draft, setDraft] = useState<ModelSettingsDraft>(() => createModelSettingsDraft(data))
  const [saveState, setSaveState] = useState<ModelSaveState>(() => createModelSaveState())
  const [healthState, setHealthState] = useState<{
    status: 'idle' | 'testing' | 'ready' | 'error'
    message: string
    report: ModelHealthReport | null
  }>({ status: 'idle', message: '', report: null })

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
          error instanceof Error ? error.message : '无法保存模型设置。',
        ),
      )
    } finally {
    }
  }

  async function runHealthTest() {
    setHealthState({ status: 'testing', message: '测试中', report: null })
    try {
      const report = await onTestHealth()
      setHealthState({ status: 'ready', message: '测试完成', report })
    } catch (error) {
      setHealthState({
        status: 'error',
        message: error instanceof Error ? error.message : '模型健康测试失败。',
        report: null,
      })
    }
  }

  const healthRows = healthState.report ? Object.values(healthState.report.tiers) : []

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
        <span>Pro 输出 Token</span>
        <input
          value={draft.pro_max_tokens}
          type="number"
          min={1024}
          max={64000}
          step={512}
          onChange={(event) => updateField('pro_max_tokens', event.target.value)}
        />
      </label>
      <label>
        <span>Pro 上下文窗口</span>
        <input
          value={draft.pro_context_window_tokens}
          type="number"
          min={16000}
          max={400000}
          step={1000}
          onChange={(event) => updateField('pro_context_window_tokens', event.target.value)}
        />
      </label>
      <label>
        <span>最大模型 Max model</span>
        <input value={draft.max_model} onChange={(event) => updateField('max_model', event.target.value)} />
      </label>
      <label>
        <span>Max 输出 Token</span>
        <input
          value={draft.max_max_tokens}
          type="number"
          min={1024}
          max={96000}
          step={512}
          onChange={(event) => updateField('max_max_tokens', event.target.value)}
        />
      </label>
      <label>
        <span>Max 上下文窗口</span>
        <input
          value={draft.max_context_window_tokens}
          type="number"
          min={16000}
          max={400000}
          step={1000}
          onChange={(event) => updateField('max_context_window_tokens', event.target.value)}
        />
      </label>
      <label>
        <span>修复轮数上限 Repair turns</span>
        <input
          value={draft.agentic_repair_max_turns}
          type="number"
          min={1}
          max={80}
          onChange={(event) => updateField('agentic_repair_max_turns', event.target.value)}
        />
      </label>
      <label>
        <span>修复上下文窗口 Repair window</span>
        <input
          value={draft.agentic_repair_history_chars}
          type="number"
          min={4000}
          max={200000}
          step={1000}
          onChange={(event) => updateField('agentic_repair_history_chars', event.target.value)}
        />
      </label>
      {saveState.message ? (
        <p className={`model-save-message ${saveState.status}`}>{saveState.message}</p>
      ) : null}
      <div className="model-settings-actions">
        <button type="submit" disabled={saveState.status === 'saving'}>
          {saveState.status === 'saving' ? '保存中' : '保存模型设置'}
        </button>
        <button type="button" onClick={runHealthTest} disabled={healthState.status === 'testing'}>
          {healthState.status === 'testing' ? '测试中' : '模型健康测试'}
        </button>
      </div>
      {healthState.message ? (
        <p className={`model-save-message ${healthState.status === 'error' ? 'error' : 'saved'}`}>
          {healthState.message}
        </p>
      ) : null}
      {healthRows.length > 0 ? (
        <div className="model-health-list">
          {healthRows.map((row) => (
            <article className={`model-health-row ${row.status}`} key={row.tier}>
              <span>{row.tier.toUpperCase()}</span>
              <div>
                <strong>{row.model_name || '未配置'}</strong>
                <p>
                  {row.status === 'ok' ? `${Math.round(row.latency_ms)} ms` : row.error || row.status}
                </p>
                {row.response_preview ? <em>{row.response_preview}</em> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </form>
  )
}

function ConfirmationPanel({
  data,
  status,
  events,
  onExecuteCommand,
}: {
  data: unknown
  status: JobStatus | null
  events: RadAgentEvent[]
  onExecuteCommand: (command: string) => Promise<void>
}) {
  const review = asRecord(data)
  const isLoading = Boolean(review._loading)
  const view = createConfirmationReviewView(data)
  const [rejectReason, setRejectReason] = useState('')
  const [question, setQuestion] = useState('')
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, ConfirmationQuestionAnswer>>({})
  const [pendingAction, setPendingAction] = useState<'approve' | 'reject' | 'ask-more' | ''>('')
  const [slowPendingAction, setSlowPendingAction] = useState(false)
  const reviewJobId = text(review.job_id || status?.job_id)
  const displayStatus = presentConfirmationStatus(review.status)
  const questionCardKey = view.questionCards
    .map((item) => `${item.fieldPath}:${item.question}:${item.recommendedValue}`)
    .join('|')
  const workflowState = asRecord(status?.state)
  const workflowKeyStatuses = asRecord(status?.key_statuses)
  const requirementsStatus = text(
    workflowState.requirements_review_status || workflowKeyStatuses.requirements_review_status,
  )
  const confirmationStatus = text(
    workflowState.confirmation_status || workflowKeyStatuses.confirmation_status,
  )
  const hasSubmittedSupplements = asArray(workflowState.requirements_review_supplements).length > 0
  const requirementsModelRunning = events.some((event) => {
    const payload = asRecord(event.payload)
    const details = asRecord(payload.details)
    const metadata = asRecord(details.metadata)
    const moduleName = text(metadata.module_name).toLowerCase()
    return (
      event.status === 'running' &&
      (moduleName.includes('requirements_review') || event.phase === 'requirements_review')
    )
  })
  const reviewIterationRunning =
    pendingAction === 'ask-more' ||
    slowPendingAction ||
    requirementsModelRunning ||
    (status?.status === 'running' &&
      hasSubmittedSupplements &&
      requirementsStatus === 'needs_user_input' &&
      confirmationStatus === 'pending')

  useEffect(() => {
    setQuestionAnswers((current) => {
      const next: Record<string, ConfirmationQuestionAnswer> = {}
      for (const card of view.questionCards) {
        next[card.fieldPath] =
          current[card.fieldPath] || {
            mode: 'recommended',
            value: card.recommendedValue,
          }
      }
      return next
    })
  }, [questionCardKey])

  useEffect(() => {
    if (pendingAction !== 'ask-more' && pendingAction !== 'approve') {
      setSlowPendingAction(false)
      return
    }
    setSlowPendingAction(false)
    const timer = window.setTimeout(() => setSlowPendingAction(true), 1000)
    return () => window.clearTimeout(timer)
  }, [pendingAction])

  function updateQuestionAnswer(fieldPath: string, update: Partial<ConfirmationQuestionAnswer>) {
    setQuestionAnswers((current) => {
      const currentAnswer = current[fieldPath] || { mode: 'recommended', value: '' }
      return {
        ...current,
        [fieldPath]: {
          ...currentAnswer,
          ...update,
        },
      }
    })
  }

  function submitParameterAnswers() {
    const supplement = buildQuestionCardSupplement(view.questionCards, questionAnswers, question, {
      includeMachinePayload: true,
    })
    return run(buildAskMoreCommand(supplement || question || '确认当前推荐参数', reviewJobId), 'ask-more')
  }

  async function run(command: string, action: 'approve' | 'reject' | 'ask-more') {
    if (command) {
      setPendingAction(action)
      try {
        await onExecuteCommand(command)
      } finally {
        setPendingAction('')
      }
    }
  }

  if (isLoading) {
    return (
      <div className="confirmation-panel">
        <div className="confirmation-loading">
          <strong>正在加载参数核对数据...</strong>
          <p>正在从后端获取最新的模型参数建议，请稍候。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="confirmation-panel">
      <article className="metric-tile">
        <span>状态</span>
        <strong>{displayStatus || '未加载确认项'}</strong>
      </article>
      <section className="confirmation-summary-card">
        <span>核对对象</span>
        <strong>Geant4 建模前参数核对</strong>
        <p>{view.summary}</p>
      </section>
      {reviewIterationRunning ? (
        <section className="confirmation-iteration-status" aria-live="polite">
          <strong>模型正在复核参数</strong>
          <p>已提交你的参数补充，系统会重新评估是否还缺信息；通过后会自动进入 Geant4 建模。</p>
        </section>
      ) : null}
      {view.assumptions.length > 0 || view.missingInformation.length > 0 ? (
        <section className="confirmation-review-section warning">
          <h3>模型假设</h3>
          {view.assumptions.map((item, index) => (
            <p key={`${item}-${index}`}>{item}</p>
          ))}
          {view.missingInformation.map((item, index) => (
            <p key={`missing-${item}-${index}`}>{item}</p>
          ))}
        </section>
      ) : null}
      {view.questionCards.length > 0 ? (
        <section className="confirmation-question-cards" aria-label="需要确认的问题">
          <h3>需要确认的问题</h3>
          {view.questionCards.map((item) => (
            <article className="confirmation-question-card" key={`${item.fieldPath}-${item.question}`}>
              <div>
                <span>问题</span>
                <strong>{item.question}</strong>
              </div>
              <div>
                <span>推荐答案</span>
                <code>{item.recommendedValue || '请补充具体值'}</code>
              </div>
              {item.reason ? (
                <div className="confirmation-question-note">
                  <span>备注</span>
                  <p>{item.reason}</p>
                </div>
              ) : null}
              <div className="confirmation-question-actions">
                <button
                  type="button"
                  className={questionAnswers[item.fieldPath]?.mode !== 'modified' ? 'active' : ''}
                  onClick={() =>
                    updateQuestionAnswer(item.fieldPath, {
                      mode: 'recommended',
                      value: item.recommendedValue,
                    })
                  }
                >
                  确认推荐
                </button>
                <button
                  type="button"
                  className={questionAnswers[item.fieldPath]?.mode === 'modified' ? 'active' : ''}
                  onClick={() =>
                    updateQuestionAnswer(item.fieldPath, {
                      mode: 'modified',
                      value: questionAnswers[item.fieldPath]?.value || item.recommendedValue,
                    })
                  }
                >
                  修改
                </button>
              </div>
              {questionAnswers[item.fieldPath]?.mode === 'modified' ? (
                <label className="confirmation-question-edit">
                  <span>修改为</span>
                  <input
                    value={questionAnswers[item.fieldPath]?.value || ''}
                    onChange={(event) =>
                      updateQuestionAnswer(item.fieldPath, {
                        mode: 'modified',
                        value: event.target.value,
                      })
                    }
                  />
                </label>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}
      {view.actionable ? (
        <div className="confirmation-actions">
          <button
            type="button"
            className="approve-button"
            onClick={() =>
              view.questionCards.length > 0
                ? submitParameterAnswers()
                : run(buildConfirmationCommand(reviewJobId), 'approve')
            }
            disabled={Boolean(pendingAction)}
          >
            {pendingAction === 'approve' || pendingAction === 'ask-more' ? '提交中' : '确认所选参数'}
          </button>
          <label>
            <span>拒绝原因</span>
            <textarea value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
          </label>
          <button
            type="button"
            onClick={() => run(buildRejectCommand(rejectReason, reviewJobId), 'reject')}
            disabled={Boolean(pendingAction) || !rejectReason.trim()}
          >
            {pendingAction === 'reject' ? '提交中' : '拒绝'}
          </button>
          <label>
            <span>修改意见或补充参数</span>
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          </label>
          <button
            type="button"
            onClick={() => run(buildAskMoreCommand(question, reviewJobId), 'ask-more')}
            disabled={Boolean(pendingAction) || !question.trim()}
          >
            {pendingAction === 'ask-more' ? '发送中' : '发送补充'}
          </button>
        </div>
      ) : (
        <p className="empty-state">该确认项已经处理，无需再次审批。</p>
      )}
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
  onTestModelHealth,
  onExecuteCommand,
}: InspectorPanelProps) {
  const title = inspectorTitle(active)
  const operationActive =
    isOperationPanelView(active) || (active === 'artifacts' && Array.isArray(asRecord(data).artifacts))
  const detailActive =
    isDetailPanelView(active) || (active === 'projects' && !Array.isArray(data) && Object.keys(asRecord(data)).length > 0)
  const detailView = active === 'projects' ? 'project' : active

  return (
    <aside className="inspector">
      <div className="panel-title">
        <FileText size={16} />
        {title.label}
        {title.labelEn ? <small>{title.labelEn}</small> : null}
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
      {detailActive ? <DetailPanelView active={detailView} data={data} onExecuteCommand={onExecuteCommand} /> : null}
      {active === 'model' ? (
        <ModelSettingsPanel data={data} onSave={onSaveModelConfig} onTestHealth={onTestModelHealth} />
      ) : null}
      {active === 'confirmation' ? (
        <ConfirmationPanel data={data} status={status} events={events} onExecuteCommand={onExecuteCommand} />
      ) : null}
      {active === 'diagnosis' ? <DiagnosisPanel data={data} /> : null}
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
        'diagnosis',
        'help',
        'logs',
        ...['tools', 'credibility', 'memory'],
        ...['build', 'simulation', 'report', 'demo', 'mode', 'history', 'exit'],
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
