import { describe, expect, it } from 'vitest'
import { createWorkbenchControlSections, isWorkbenchControlAction } from './workbenchControls'
import type { CommandCatalogEntryLike } from './commands'

const catalog: CommandCatalogEntryLike[] = [
  'run',
  'workbench',
  'build',
  'simulate',
  'step',
  'confirm',
  'gates',
  'credibility',
  'artifacts',
  'jobs',
  'logs',
  'model',
  'history',
  'demo',
  'exit',
].map((name) => ({
  name,
  description: `${name} command`,
  tip: `${name} tip`,
  module: `${name}/module`,
  connection: 'service',
  visible: true,
}))

describe('workbench controls', () => {
  it('groups useful workflow commands into Chinese-first web control sections', () => {
    const sections = createWorkbenchControlSections(catalog)

    expect(sections.map((section) => section.title)).toEqual(['执行推进', '审查门禁', '结果与环境'])
    expect(sections[0].actions.map((action) => action.name)).toEqual(['workbench', 'build', 'simulate', 'step'])
    expect(sections[1].actions.map((action) => action.name)).toEqual(['confirm', 'gates', 'credibility'])
    expect(sections[2].actions.map((action) => action.name)).toEqual(['artifacts', 'jobs', 'logs', 'model'])
  })

  it('keeps command-line-only or low-value commands out of the web control panel', () => {
    const sections = createWorkbenchControlSections(catalog)
    const names = sections.flatMap((section) => section.actions.map((action) => action.name))

    expect(names).not.toEqual(expect.arrayContaining(['run', 'history', 'demo', 'exit']))
    expect(isWorkbenchControlAction('build')).toBe(true)
    expect(isWorkbenchControlAction('history')).toBe(false)
  })

  it('requires every rendered action to carry a tip and auxiliary label', () => {
    const sections = createWorkbenchControlSections(catalog)

    for (const action of sections.flatMap((section) => section.actions)) {
      expect(action.primary).toMatch(/[^\x00-\x7F]/)
      expect(action.secondary.length).toBeGreaterThan(0)
      expect(action.tip.length).toBeGreaterThan(8)
      expect(action.internalCommand).toMatch(/^\//)
    }
  })
})
