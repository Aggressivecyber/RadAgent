import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import WorkflowMiniDemo from './WorkflowMiniDemo'

describe('WorkflowMiniDemo', () => {
  it('renders a distinct animated demo for each workflow step', () => {
    const indexes = ['01', '02', '03', '04', '05', '06']

    indexes.forEach((index) => {
      const markup = renderToStaticMarkup(<WorkflowMiniDemo index={index} />)

      expect(markup).toContain(`mini-demo-${index}`)
      expect(markup).toContain('mini-scene')
      expect(markup).toContain('viewBox="0 0 520 320"')
      expect(markup).toContain('preserveAspectRatio="xMidYMid slice"')
      expect(markup).toContain('scene-grid')
      expect(markup).toContain('aria-label="')
    })
  })

  it('uses domain-specific scenes instead of generic line placeholders', () => {
    const expectedScenes = [
      ['01', 'scene-spacecraft-shielding', 'particle-stream'],
      ['02', 'scene-geant4-model', 'world-volume'],
      ['03', 'scene-radiation-belt', 'earth-orbit'],
      ['04', 'scene-local-run', 'terminal-window'],
      ['05', 'scene-validation-gates', 'gate-stack'],
      ['06', 'scene-artifact-report', 'report-sheet'],
    ]

    expectedScenes.forEach(([index, sceneClass, detailClass]) => {
      const markup = renderToStaticMarkup(<WorkflowMiniDemo index={index} />)

      expect(markup).toContain(sceneClass)
      expect(markup).toContain(detailClass)
    })
  })
})
