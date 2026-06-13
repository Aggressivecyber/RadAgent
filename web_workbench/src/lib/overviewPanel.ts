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

function plural(count: number, singular: string): string {
  return `${count} ${singular}${count === 1 ? '' : 's'}`
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
    meta: event.phase || event.created_at,
  }))
}

export function createOverviewPanel({ status, events, commands }: OverviewInput): OverviewPanel {
  if (!status || !status.job_id) {
    return {
      title: '暂无活动作业',
      subtitle: 'Start a workflow or open a saved project from Home.',
      metrics: [
        { label: '状态 State', value: 'idle' },
        { label: '阶段 Phase', value: 'prepare_workspace' },
        { label: '已完成 Completed', value: '0 phases' },
        { label: '模式 Mode', value: 'strict' },
      ],
      alerts: [],
      actions: [
        action(commands, '开始工作流', 'Start workflow', 'run', 'primary', 'compose'),
        action(commands, '浏览作业', 'Browse jobs', 'jobs'),
      ],
      recentEvents: recentEvents(events),
    }
  }

  const alerts: OverviewAlert[] = status.needs_confirmation
    ? [
        {
          status: 'warning',
          title: '需要确认',
          detail: 'Review the active human-confirmation gate before continuing.',
        },
      ]
    : []

  const actions = status.needs_confirmation
    ? [
        action(commands, '处理确认', 'Review confirmation', 'confirm', 'primary'),
        action(commands, '查看门禁', 'Open gates', 'gates'),
      ]
    : [
        action(commands, '继续下一步', 'Continue step', 'step', 'primary'),
        action(commands, '构建工程', 'Build', 'build'),
        action(commands, '查看产物', 'Open artifacts', 'artifacts'),
      ]

  return {
    title: status.user_query || status.job_id,
    subtitle: status.job_workspace || status.workspace_root || status.job_id,
    metrics: [
      { label: '状态 State', value: status.status || 'unknown' },
      { label: '阶段 Phase', value: status.current_phase || 'idle' },
      { label: '已完成 Completed', value: plural(status.completed_phases.length, 'phase') },
      { label: '模式 Mode', value: status.run_mode || status.execution_mode || 'strict' },
    ],
    alerts,
    actions,
    recentEvents: recentEvents(events),
  }
}
