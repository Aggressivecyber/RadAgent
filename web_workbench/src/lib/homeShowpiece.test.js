import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readApp() {
  return readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8')
}

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

describe('home showpiece effects', () => {
  it('adds decorative home-only effect layers without changing content structure', () => {
    const app = readApp()

    expect(app).toContain('home-scan-beam')
    expect(app).toContain('home-signal-dots')
    expect(app).toContain('aria-hidden="true"')
    expect(app).toContain('<h1>Radagent</h1>')
    expect(app).toContain('className="hero-copy"')
    expect(app).not.toContain('home-orbital-field')
  })

  it('styles the home hero with one-shot shimmer and signal effects without the halo orbital layer', () => {
    const css = readStyles()

    expect(css).toContain('.home-scan-beam')
    expect(css).toContain('.home-signal-dots')
    expect(css).toContain('.home-hero::before')
    expect(css).toContain('@keyframes home-beam-sweep')
    expect(css).toContain('@keyframes home-signal-ping')
    expect(css).not.toContain('.home-orbital-field')
    expect(css).not.toContain('@keyframes home-orbit-drift')
    expect(css).not.toContain('.hero-copy h1::after')
    expect(css).not.toContain('@keyframes home-title-shine')

    const scanBeamRule = css.slice(
      css.indexOf('.home-scan-beam {'),
      css.indexOf('.home-signal-dots span', css.indexOf('.home-scan-beam {')),
    )
    expect(scanBeamRule).toContain('animation: home-beam-sweep')
    expect(scanBeamRule).not.toContain('infinite')
    expect(scanBeamRule).toContain('both')

    const beamKeyframes = cssBetween(
      css,
      '@keyframes home-beam-sweep',
      '@keyframes home-signal-ping',
    )
    expect(beamKeyframes).toContain('transform:')
    expect(beamKeyframes).toContain('opacity:')
    expect(beamKeyframes).not.toMatch(/^\s+(left|top|width|height|margin|padding):/m)
  })

  it('includes home showpiece effects in reduced-motion shutdown', () => {
    const css = readStyles()
    const reducedMotion = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))

    expect(reducedMotion).toContain('.home-scan-beam')
    expect(reducedMotion).toContain('.home-signal-dots span')
    expect(reducedMotion).not.toContain('.home-orbital-field')
    expect(reducedMotion).toContain('animation: none !important')
  })

  it('adds scroll-driven unfold animations to lower home cards', () => {
    const css = readStyles()

    expect(css).toContain('.home-metric')
    expect(css).toContain('.advantage-panel')
    expect(css).toContain('.advantage-panel.is-visible')
    expect(css).toContain('@keyframes home-card-unfold')
    expect(css).toContain('@keyframes home-card-line-grow')
    expect(css).toContain('animation-timeline: view()')
    expect(css).toContain('animation-range: entry 4% cover 34%')

    const unfoldKeyframes = cssBetween(
      css,
      '@keyframes home-card-unfold',
      '@keyframes home-card-line-grow',
    )
    expect(unfoldKeyframes).toContain('transform:')
    expect(unfoldKeyframes).toContain('opacity:')
    expect(unfoldKeyframes).not.toMatch(/^\s+(left|top|width|height|margin|padding):/m)

    const projectCardRule = css.slice(
      css.indexOf('.project-card {'),
      css.indexOf('.project-card::before', css.indexOf('.project-card {')),
    )
    expect(projectCardRule).not.toContain('home-card-unfold')
    expect(projectCardRule).not.toContain('animation-timeline: view()')
  })

  it('reveals advantage cards with explicit viewport visibility classes', () => {
    const app = readApp()

    expect(app).toContain('IntersectionObserver')
    expect(app).toContain('visibleAdvantageCards')
    expect(app).toContain('next.delete(index)')
    expect(app).toContain('data-advantage-index={item.index}')
    expect(app).toContain("advantage-panel is-visible")
    expect(app).not.toContain('observer.unobserve(entry.target)')
    expect(app).not.toContain("onWheel={() => collapseIntro('wheel')}")
    expect(app).not.toContain("onTouchStart={() => collapseIntro('touch')}")
  })
})
