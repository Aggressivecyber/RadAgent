import type { RadAgentEvent, WebCommandResponse } from './api'
import { commandPresentation } from './commandPresentation'

export type TimelineStatus = 'info' | 'running' | 'success' | 'warning' | 'error'

export type TimelineRow = {
  id: string
  kind: 'system' | 'command' | 'event'
  title: string
  body: string
  status: TimelineStatus
  meta?: string
  details?: unknown
}

export type WorkbenchState = {
  activeInspector: string
  inspectorData: Record<string, unknown>
  timeline: TimelineRow[]
  seenEventIds: Set<string>
}

export function createInitialWorkbenchState(): WorkbenchState {
  return {
    activeInspector: 'overview',
    inspectorData: {},
    seenEventIds: new Set(),
    timeline: [
      {
        id: 'system:init',
        kind: 'system',
        title: '工作台已就绪',
        body: '命令、事件、审查面板状态已连接。',
        status: 'info',
      },
    ],
  }
}

function commandTitle(response: WebCommandResponse): string {
  if (!response.command) {
    return '功能执行'
  }
  return commandPresentation({
    name: response.command,
    description: response.command,
  }).primary
}

function summarizeData(value: unknown): string {
  if (value == null) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'object') {
    if ('message' in value && typeof (value as { message?: unknown }).message === 'string') {
      return String((value as { message: string }).message)
    }
    if ('status' in value && typeof (value as { status?: unknown }).status === 'string') {
      return `Status: ${(value as { status: string }).status}`
    }
  }
  return JSON.stringify(value, null, 2)
}

export function reduceCommandResponse(
  state: WorkbenchState,
  response: WebCommandResponse,
): WorkbenchState {
  const status: TimelineStatus = response.ok ? 'success' : 'error'
  const title = commandTitle(response)
  const body = response.ok ? summarizeData(response.data) : response.error || 'Command failed'
  const timeline = [
    ...state.timeline,
    {
      id: `command:${Date.now()}:${state.timeline.length}`,
      kind: 'command' as const,
      title,
      body,
      status,
      meta: response.view,
      details: response.data,
    },
  ]

  if (!response.ok || response.view === 'composer') {
    return { ...state, timeline }
  }

  return {
    ...state,
    activeInspector: response.view,
    inspectorData: {
      ...state.inspectorData,
      [response.view]: response.data,
    },
    timeline,
  }
}

function eventId(event: RadAgentEvent): string {
  return [
    event.created_at,
    event.event_type,
    event.phase,
    event.job_id,
    event.run_id,
    event.summary,
  ].join(':')
}

export function reduceEvents(state: WorkbenchState, events: RadAgentEvent[]): WorkbenchState {
  const seenEventIds = new Set(state.seenEventIds)
  const timeline = [...state.timeline]

  for (const event of events) {
    const id = eventId(event)
    if (seenEventIds.has(id)) {
      continue
    }
    seenEventIds.add(id)
    timeline.push({
      id: `event:${id}`,
      kind: 'event',
      title: event.event_type.replaceAll('_', ' '),
      body: event.summary || event.phase || event.job_id || 'Service event',
      status: event.status,
      meta: event.phase || undefined,
      details: event.payload,
    })
  }

  return { ...state, seenEventIds, timeline }
}

export function reduceDetailSelection(
  state: WorkbenchState,
  view: string,
  data: unknown,
): WorkbenchState {
  return {
    ...state,
    activeInspector: view,
    inspectorData: {
      ...state.inspectorData,
      [view]: data,
    },
    timeline: [
      ...state.timeline,
      {
        id: `detail:${view}:${Date.now()}:${state.timeline.length}`,
        kind: 'system',
        title: `Selected ${view}`,
        body: summarizeData(data),
        status: 'info',
        meta: view,
        details: data,
      },
    ],
  }
}

export function reduceInitialJobSelection(
  state: WorkbenchState,
  job: Record<string, unknown>,
): WorkbenchState {
  return {
    ...state,
    activeInspector: 'job',
    inspectorData: {
      ...state.inspectorData,
      job,
    },
    timeline: [
      ...state.timeline,
      {
        id: `home-job:${String(job.job_id || 'selected')}:${Date.now()}:${state.timeline.length}`,
        kind: 'system',
        title: 'Opened project job',
        body: summarizeData(job),
        status: 'info',
        meta: 'job',
        details: job,
      },
    ],
  }
}
