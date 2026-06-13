import { describe, expect, it } from 'vitest'
import { createShowcaseLaunchTarget } from './homeNavigation'
import type { ShowcaseCard } from './homeSummary'

describe('home showcase navigation', () => {
  it('creates a workbench example target with the natural-language task request', () => {
    const example: ShowcaseCard = {
      id: 'example-hpge-coincidence',
      title: 'HPGe 反符合谱仪',
      subtitle: 'Anti-coincidence HPGe spectrometer',
      prompt: 'Build a Geant4 workflow for an HPGe anti-coincidence gamma spectrometer.',
      difficulty: 'advanced',
      tags: ['HPGe', 'anti-coincidence'],
      validationFocus: ['geometry', 'scoring'],
    }

    expect(createShowcaseLaunchTarget(example)).toEqual({
      kind: 'example',
      exampleId: 'example-hpge-coincidence',
      prompt: 'Build a Geant4 workflow for an HPGe anti-coincidence gamma spectrometer.',
    })
  })

  it('does not create a target for empty showcase prompts', () => {
    const example: ShowcaseCard = {
      id: 'empty',
      title: '空示例',
      subtitle: 'Empty',
      prompt: '   ',
      difficulty: 'advanced',
      tags: [],
      validationFocus: [],
    }

    expect(createShowcaseLaunchTarget(example)).toBeNull()
  })
})
