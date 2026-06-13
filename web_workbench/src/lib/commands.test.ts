import { describe, expect, it } from 'vitest'
import { coreCommandNames, groupCommandCatalog, isCoreCommand } from './commands'

describe('workbench command metadata', () => {
  it('covers the current TUI command surface', () => {
    expect(coreCommandNames).toEqual(
      expect.arrayContaining([
        'run',
        'chat',
        'jobs',
        'artifacts',
        'confirm',
        'build',
        'simulate',
        'model',
        'projects',
        'revisions',
        'workbench',
        'visual-approve',
        'visual-reject',
      ]),
    )
  })

  it('recognizes slash-command names without accepting arbitrary strings', () => {
    expect(isCoreCommand('/status')).toBe(true)
    expect(isCoreCommand('status')).toBe(true)
    expect(isCoreCommand('/unknown')).toBe(false)
  })

  it('groups only useful visible commands into the commercial command palette', () => {
    const groups = groupCommandCatalog(
      coreCommandNames.map((name) => ({
        name,
        description: `${name} command`,
        tip: `${name} tip`,
        module: `${name} module`,
        connection: 'service',
        visible: !['demo', 'history', 'inspect', 'mode', 'options', 'exit'].includes(name),
      })),
    )
    const groupedNames = groups.flatMap((group) => group.commands.map((command) => command.name))

    expect(groups.map((group) => group.label)).toEqual([
      'Workflow',
      'Review',
      'Navigation',
      'System',
    ])
    expect(groupedNames).not.toEqual(expect.arrayContaining(['demo', 'history', 'inspect', 'mode', 'options', 'exit']))
    expect(groupedNames).toEqual(expect.arrayContaining(['run', 'report', 'build', 'confirm', 'model']))
    expect(groupedNames.filter((name) => name === 'run')).toHaveLength(1)
    expect(groups.find((group) => group.label === 'Review')?.commands.map((command) => command.name)).toEqual(
      expect.arrayContaining(['confirm', 'revise', 'accept-revision', 'visual-reject']),
    )
    expect(groups[0].commands[0]).toMatchObject({
      tip: expect.stringContaining('tip'),
      module: expect.stringContaining('module'),
    })
  })
})
