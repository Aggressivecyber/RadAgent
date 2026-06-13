export const coreCommandNames = [
  'run',
  'approve',
  'check',
  'open',
  'report',
  'demo',
  'help',
  'history',
  'jobs',
  'job',
  'artifacts',
  'inspect',
  'status',
  'mode',
  'resume',
  'retry',
  'revise',
  'revisions',
  'artifact',
  'build',
  'chat',
  'confirm',
  'credibility',
  'exit',
  'gates',
  'logs',
  'memory',
  'model',
  'options',
  'project',
  'projects',
  'accept-revision',
  'ask-more',
  'reject-revision',
  'reject',
  'revision',
  'simulate',
  'visual-approve',
  'visual-reject',
  'workbench',
  'step',
] as const

export type CoreCommandName = (typeof coreCommandNames)[number]

export type CommandCatalogEntryLike = {
  name: string
  description: string
  tip?: string
  module?: string
  connection?: string
  visible?: boolean
}

export type CommandCatalogGroup = {
  label: 'Workflow' | 'Review' | 'Navigation' | 'System'
  commands: CommandCatalogEntryLike[]
}

const coreCommandSet = new Set<string>(coreCommandNames)

const commandGroups: Array<{
  label: CommandCatalogGroup['label']
  commands: CoreCommandName[]
}> = [
  {
    label: 'Workflow',
    commands: ['run', 'step', 'build', 'simulate', 'workbench', 'demo', 'resume', 'retry'],
  },
  {
    label: 'Review',
    commands: [
      'confirm',
      'approve',
      'reject',
      'ask-more',
      'gates',
      'credibility',
      'revise',
      'revisions',
      'revision',
      'accept-revision',
      'reject-revision',
      'visual-approve',
      'visual-reject',
    ],
  },
  {
    label: 'Navigation',
    commands: [
      'status',
      'jobs',
      'job',
      'artifacts',
      'artifact',
      'open',
      'report',
      'history',
      'logs',
      'memory',
      'projects',
      'project',
      'check',
      'inspect',
    ],
  },
  {
    label: 'System',
    commands: ['help', 'mode', 'model', 'options', 'chat', 'exit'],
  },
]

export function normalizeCommandName(value: string): string {
  return value.trim().replace(/^\//, '').split(/\s+/)[0]?.toLowerCase() ?? ''
}

export function isCoreCommand(value: string): value is CoreCommandName {
  return coreCommandSet.has(normalizeCommandName(value))
}

export function groupCommandCatalog(commands: CommandCatalogEntryLike[]): CommandCatalogGroup[] {
  const byName = new Map(
    commands
      .filter((command) => command.visible !== false)
      .map((command) => [normalizeCommandName(command.name), command]),
  )

  return commandGroups.map((group) => ({
    label: group.label,
    commands: group.commands.flatMap((name) => {
      const command = byName.get(name)
      return command ? [{ ...command, name }] : []
    }),
  }))
}
