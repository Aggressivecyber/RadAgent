import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyles() {
  return readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
}

function readApp() {
  return readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8')
}

describe('home rotating particle sphere presence', () => {
  it('uses a dedicated no-dispersion particle field on the home hero', () => {
    const app = readApp()

    expect(app).toContain('<HeroSphere variant="field" />')
  })

  it('keeps the home rotating particle sphere prominent without overwhelming the hero copy', () => {
    const css = readStyles()

    expect(css).toContain('width: min(132vw, 1180px)')
    expect(css).toContain('opacity: 0.82')
    expect(css).toContain('mix-blend-mode: multiply')
    expect(css).toContain('.home-ambient-sphere .hero-sphere-field')
  })

  it('keeps the home field center clear while restoring the static outer rainbow atmosphere', () => {
    const css = readStyles()

    const homeSphereRuleStart = css.indexOf('.home-ambient-sphere {', css.indexOf('.home-signal-dots'))
    const homeSphereStyles = css.slice(
      homeSphereRuleStart,
      css.indexOf('.hero-copy', homeSphereRuleStart),
    )

    expect(homeSphereStyles).toContain('border-color: rgba(23, 22, 20, 0.06)')
    expect(homeSphereStyles).toContain('.home-ambient-sphere .hero-sphere-field::before')
    expect(homeSphereStyles).toContain('content: none')
    expect(homeSphereStyles).toContain('.home-ambient-sphere .hero-sphere-field::after')
    expect(homeSphereStyles).toContain('conic-gradient')
    expect(homeSphereStyles).toContain('transparent 0 56%')
    expect(homeSphereStyles).not.toContain('radial-gradient(circle at 50% 50%')
    expect(homeSphereStyles).not.toContain('rgba(255, 255, 255, 0.86)')
    expect(homeSphereStyles).not.toContain('home-particle-field-drift')
  })

  it('does not add extra home-field CSS animation for reduced-motion users to disable', () => {
    const css = readStyles()
    const reducedMotion = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))

    expect(css).not.toContain('@keyframes home-particle-field-drift')
    expect(reducedMotion).not.toContain('.home-ambient-sphere .hero-sphere-field')
    expect(reducedMotion).toContain('animation: none !important')
  })
})
