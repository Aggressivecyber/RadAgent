import type { CommandCatalogEntryLike, CommandCatalogGroup } from './commands'
import { normalizeCommandName } from './commands'

export type CommandPresentation = {
  primary: string
  secondary: string
  tip: string
  internalCommand: string
  module?: string
  displayCommand?: string
}

const actionLabels: Record<string, Pick<CommandPresentation, 'primary' | 'secondary' | 'tip'>> = {
  run: {
    primary: '开始工作流',
    secondary: 'Run workflow',
    tip: '从仿真需求启动一个真实 RadAgent 工作流。',
  },
  step: {
    primary: '继续下一步',
    secondary: 'Continue step',
    tip: '推进当前作业的下一阶段。',
  },
  build: {
    primary: '构建工程',
    secondary: 'Build project',
    tip: '编译当前作业生成的 Geant4 代码。',
  },
  simulate: {
    primary: '运行模拟',
    secondary: 'Simulate',
    tip: '按选定事件数运行当前仿真批次。',
  },
  resume: {
    primary: '恢复作业',
    secondary: 'Resume',
    tip: '继续已暂停或中断的工作流。',
  },
  retry: {
    primary: '重试阶段',
    secondary: 'Retry stage',
    tip: '复用当前作业，重新执行失败的当前阶段。',
  },
  confirm: {
    primary: '处理确认',
    secondary: 'Review confirmation',
    tip: '打开需要人工确认的门禁并继续审批。',
  },
  diagnose: {
    primary: '诊断阻塞',
    secondary: 'Diagnose',
    tip: '解释当前失败或等待原因，并区分可审批事项与系统阻塞。',
  },
  approve: {
    primary: '批准',
    secondary: 'Approve',
    tip: '批准当前确认项。',
  },
  reject: {
    primary: '拒绝',
    secondary: 'Reject',
    tip: '带原因拒绝当前确认项。',
  },
  'ask-more': {
    primary: '追问补充',
    secondary: 'Ask more',
    tip: '向当前确认项追加问题或要求更多信息。',
  },
  gates: {
    primary: '查看门禁',
    secondary: 'Gates',
    tip: '查看验证门禁、阻塞原因和确认状态。',
  },
  credibility: {
    primary: '可信度',
    secondary: 'Credibility',
    tip: '查看当前模型和产物的可信度检查结果。',
  },
  revise: {
    primary: '提交修订',
    secondary: 'Revise',
    tip: '对当前结果提出修订要求。',
  },
  revisions: {
    primary: '修订列表',
    secondary: 'Revisions',
    tip: '查看历史修订记录。',
  },
  status: {
    primary: '查看状态',
    secondary: 'Status',
    tip: '查看当前作业、阶段和运行状态。',
  },
  jobs: {
    primary: '作业列表',
    secondary: 'Jobs',
    tip: '浏览已有作业并进入详情。',
  },
  artifacts: {
    primary: '产物列表',
    secondary: 'Artifacts',
    tip: '查看报告、源码、日志和交付物。',
  },
  logs: {
    primary: '运行日志',
    secondary: 'Logs',
    tip: '查看服务事件和执行日志。',
  },
  memory: {
    primary: '工作记忆',
    secondary: 'Memory',
    tip: '查看结构化仿真模型和上下文记忆。',
  },
  model: {
    primary: '模型设置',
    secondary: 'Model settings',
    tip: '配置 Lite、Pro、Max 模型和接口参数。',
  },
  help: {
    primary: '功能选择',
    secondary: 'Actions',
    tip: '查看可用功能并用按钮触发。',
  },
  chat: {
    primary: '对话',
    secondary: 'Chat',
    tip: '向 RadAgent 发送补充说明。',
  },
}

const groupLabels: Record<CommandCatalogGroup['label'], { primary: string; secondary: string }> = {
  Workflow: { primary: '工作流', secondary: 'Workflow' },
  Review: { primary: '审核', secondary: 'Review' },
  Navigation: { primary: '导航', secondary: 'Navigation' },
  System: { primary: '系统', secondary: 'System' },
}

export function commandGroupPresentation(label: CommandCatalogGroup['label']) {
  return groupLabels[label]
}

export function commandPresentation(command: CommandCatalogEntryLike): CommandPresentation {
  const name = normalizeCommandName(command.name)
  const curated = actionLabels[name]
  const fallback = name.replaceAll('-', ' ')
  const primary = curated?.primary || command.description || fallback
  const secondary = curated?.secondary || fallback

  return {
    primary,
    secondary,
    tip: curated?.tip || command.tip || command.description || fallback,
    internalCommand: `/${name}`,
    module: command.module,
  }
}
