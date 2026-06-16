import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import HeroSphere from './HeroSphere'

describe('HeroSphere', () => {
  it('renders Chinese-first labels with auxiliary English text', () => {
    const markup = renderToStaticMarkup(<HeroSphere />)

    expect(markup).toContain('<strong>需求</strong>')
    expect(markup).toContain('<small>Intent</small>')
    expect(markup).toContain('<strong>构建</strong>')
    expect(markup).toContain('<small>Build</small>')
  })

  it('measures canvas from layout size so body zoom does not offset the sphere rings', () => {
    const source = HeroSphere.toString()

    expect(source).toContain('container.clientWidth')
    expect(source).toContain('container.clientHeight')
    expect(source).not.toContain('const box = container.getBoundingClientRect()\\n      width')
  })

  it('draws prism glass dispersion instead of a plain particle sphere', () => {
    const source = HeroSphere.toString()

    expect(source).toContain('drawPrismCaustics')
    expect(source).toContain('dispersionPalette')
    expect(source).toMatch(/globalCompositeOperation\s*=\s*["']screen["']/)
    expect(source).toContain('createLinearGradient')
  })

  it('supports a home field variant with a plain rotating particle sphere and no caustics', () => {
    const markup = renderToStaticMarkup(<HeroSphere variant="field" />)
    const source = HeroSphere.toString()

    expect(markup).toContain('hero-sphere-field')
    expect(source).toMatch(/variant\s*===\s*["']field["']/)
    expect(source).toMatch(/variant\s*!==\s*["']field["']/)
    expect(source).not.toContain('drawParticleFlight')
    expect(source).not.toContain('createRadialGradient')
  })
})
