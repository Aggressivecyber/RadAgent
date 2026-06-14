import type { CommandCatalogEntry, JobStatus, RadAgentEvent } from './api'

export type OverviewMetric = {
  label: string
  value: string
}

export type OverviewAlert = {
  status: 'info' | 'warning' | 'error'
  title: string
  detail: string
}

export type OverviewAction = {
  label: string
  labelEn: string
  command: string
  tip: string
  tone: 'primary' | 'neutral'
  mode: 'compose' | 'execute'
}

export type OverviewEvent = {
  title: string
  status: RadAgentEvent['status']
  detail: string
  meta: string
}

export type OverviewPanel = {
  title: string
  subtitle: string
  metrics: OverviewMetric[]
  alerts: OverviewAlert[]
  actions: OverviewAction[]
  recentEvents: OverviewEvent[]
}

type OverviewInput = {
  status: JobStatus | null
  events: RadAgentEvent[]
  commands: CommandCatalogEntry[]
}

const phaseLabels: Record<string, string> = {
  prepare_workspace: '准备工作区',
  context: '上下文收集',
  task_planning: '任务规划',
  g4_modeling: 'Geant4 建模',
  human_confirmation: '人工确认',
  g4_codegen: '工程生成',
  patch: '修订补丁',
  gate: '验证门禁',
  validation: '验证门禁',
  artifact: '产物归档',
  report: '报告交付',
}

const statusLabels: Record<string, string> = {
  idle: '待命',
  running: '运行中',
  paused: '暂停审查',
  completed: '已完成',
  failed: '失败',
  error: '失败',
}

const modeLabels: Record<string, string> = {
  strict: '严格模式',
  local: '本地运行',
  interactive: '交互模式',
}

function phaseLabel(phase: string): string {
  return phaseLabels[phase] || phase.replaceAll('_', ' ')
}

function statusLabel(status: string): string {
  return statusLabels[status] || status || '未知'
}

function modeLabel(mode: string): string {
  return modeLabels[mode] || mode || '严格模式'
}

function phaseCount(count: number): string {
  return `${count} 个阶段`
}

function commandTip(commands: CommandCatalogEntry[], name: string): string {
  return commands.find((command) => command.visible && command.name === name)?.tip || ''
}

function action(
  commands: CommandCatalogEntry[],
  label: string,
  labelEn: string,
  name: string,
  tone: OverviewAction['tone'] = 'neutral',
  mode: OverviewAction['mode'] = 'execute',
): OverviewAction {
  return {
    label,
    labelEn,
    command: `/${name}`,
    tip: commandTip(commands, name),
    tone,
    mode,
  }
}

function recentEvents(events: RadAgentEvent[]): OverviewEvent[] {
  return events.slice(-5).reverse().map((event) => ({
    title: event.event_type.replaceAll('_', ' '),
    status: event.status,
    detail: event.summary || event.phase || event.job_id || 'Service event',
    meta: event.phase ? phaseLabel(event.phase) : event.created_at,
  }))
}

export function createOverviewPanel({ status, events, commands }: OverviewInput): OverviewPanel {
  if (!status || !status.job_id) {
    return {
      title: '暂无活动作业',
      subtitle: '从首页选择示例，或在工作台输入一个新的辐照防护仿真任务。',
      metrics: [
        { label: '状态', value: '待命' },
        { label: '阶段', value: '准备工作区' },
        { label: '已完成', value: '0 个阶段' },
        { label: '模式', value: '严格模式' },
      ],
      alerts: [],
      actions: [
        action(commands, '开始工作流', 'Start', 'run', 'primary', 'compose'),
        action(commands, '浏览作业', 'Jobs', 'jobs'),
      ],
      recentEvents: recentEvents(events),
    }
  }

  const alerts: OverviewAlert[] = status.needs_confirmation
    ? [
        {
          status: 'warning',
          title: '需要确认',
          detail: '继续前需要审查当前人工确认门禁。',
        },
      ]
    : []

  const actions = status.needs_confirmation
    ? [
        action(commands, '处理确认', 'Review', 'confirm', 'primary'),
        action(commands, '查看门禁', 'Gates', 'gates'),
      ]
    : [
        action(commands, '继续下一步', 'Continue', 'step', 'primary'),
        action(commands, '构建工程', 'Build', 'build'),
        action(commands, '查看产物', 'Artifacts', 'artifacts'),
      ]

  return {
    title: status.user_query || status.job_id,
    subtitle: status.job_workspace || status.workspace_root || status.job_id,
    metrics: [
      { label: '状态', value: statusLabel(status.status) },
      { label: '阶段', value: phaseLabel(status.current_phase || 'prepare_workspace') },
      { label: '已完成', value: phaseCount(status.completed_phases.length) },
      { label: '模式', value: modeLabel(status.run_mode || status.execution_mode || 'strict') },
    ],
    alerts,
    actions,
    recentEvents: recentEvents(events),
  }
}
