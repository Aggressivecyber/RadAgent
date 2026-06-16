import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyles() {
  return readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
}

function cssBetween(css, start, end) {
  const startIndex = css.indexOf(start)
  const endIndex = css.indexOf(end, startIndex + start.length)
  expect(startIndex).toBeGreaterThanOrEqual(0)
  expect(endIndex).toBeGreaterThan(startIndex)
  return css.slice(startIndex, endIndex)
}

describe('commercial motion polish CSS', () => {
  it('adds a stronger welcome sequence without changing the home layout contract', () => {
    const css = readStyles()

    expect(css).toContain('.intro-sphere-stage::before')
    expect(css).toContain('.intro-sphere-stage::after')
    expect(css).toContain('@keyframes intro-radiation-ring')
    expect(css).toContain('@keyframes intro-scan-sweep')
    expect(css).toContain('@keyframes intro-title-arrive')
    expect(css).toContain('@keyframes intro-hint-drift')
    expect(css).toContain('--intro-home-scale: 0.74;')

    const ringKeyframes = cssBetween(
      css,
      '@keyframes intro-radiation-ring',
      '@keyframes intro-scan-sweep',
    )
    expect(ringKeyframes).toContain('transform:')
    expect(ringKeyframes).toContain('opacity:')
    expect(ringKeyframes).not.toMatch(/^\s+(left|top|width|height|margin|padding):/m)
  })

  it('adds scoped micro-interactions to existing workbench elements', () => {
    const css = readStyles()

    expect(css).toContain('--motion-fast: 150ms;')
    expect(css).toContain('.workbench-shell .agent-status-rail')
    expect(css).toContain('.workbench-shell .workbench-main')
    expect(css).toContain('.workbench-shell .artifact-workspace')
    expect(css).toContain('@keyframes workbench-panel-enter')
    expect(css).toContain('@keyframes status-pill-breathe')
    expect(css).toContain('@keyframes status-text-shimmer')
    expect(css).toContain('@keyframes timeline-row-enter')
    expect(css).toContain('@keyframes dialog-pop')

    const panelKeyframes = cssBetween(
      css,
      '@keyframes workbench-panel-enter',
      '@keyframes timeline-row-enter',
    )
    expect(panelKeyframes).toContain('transform:')
    expect(panelKeyframes).toContain('opacity:')
    expect(panelKeyframes).not.toMatch(/^\s+(left|top|width|height|margin|padding):/m)
  })

  it('disables the added motion for reduced-motion users', () => {
    const css = readStyles()
    const reducedMotion = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))

    expect(reducedMotion).toContain('.intro-sphere-stage::before')
    expect(reducedMotion).toContain('.intro-sphere-stage::after')
    expect(reducedMotion).toContain('.workbench-shell .agent-status-rail')
    expect(reducedMotion).toContain('.timeline-row')
    expect(reducedMotion).toContain('.workflow-confirm-dialog')
    expect(reducedMotion).toContain('animation: none')
    expect(reducedMotion).toContain('transition-duration: 0.01ms')
  })
})
