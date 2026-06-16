import type { CommandCatalogEntryLike } from './commands'
import { normalizeCommandName } from './commands'
import { commandPresentation, type CommandPresentation } from './commandPresentation'

export type WorkbenchControlSection = {
  title: string
  subtitle: string
  actions: WorkbenchControlAction[]
}

export type WorkbenchControlAction = CommandPresentation & {
  name: string
  intent: 'primary' | 'neutral'
}

const sectionDefinitions = [
  {
    title: '执行推进',
    subtitle: 'Workflow',
    actions: ['retry', 'build', 'simulate'],
  },
  {
    title: '审查门禁',
    subtitle: 'Review',
    actions: ['diagnose', 'confirm', 'gates', 'credibility'],
  },
  {
    title: '结果与环境',
    subtitle: 'Results',
    actions: ['artifacts', 'jobs', 'logs', 'model'],
  },
] as const

const controlActionNames: Set<string> = new Set(sectionDefinitions.flatMap((section) => section.actions))

export function isWorkbenchControlAction(name: string) {
  return controlActionNames.has(normalizeCommandName(name))
}

export function createWorkbenchControlSections(commands: CommandCatalogEntryLike[]): WorkbenchControlSection[] {
  const commandByName = new Map(
    commands
      .filter((command) => command.visible !== false)
      .map((command) => [normalizeCommandName(command.name), command]),
  )

  return sectionDefinitions.map((section) => ({
    title: section.title,
    subtitle: section.subtitle,
    actions: section.actions.flatMap((name) => {
      const command = commandByName.get(name)
      if (!command) {
        return []
      }
      return [
        {
          ...commandPresentation({ ...command, name }),
          name,
          intent: name === 'retry' || name === 'build' || name === 'simulate' ? 'primary' : 'neutral',
        },
      ]
    }),
  }))
}
