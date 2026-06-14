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
})
