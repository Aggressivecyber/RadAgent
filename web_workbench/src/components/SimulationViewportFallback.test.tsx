import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import SimulationViewportFallback from './SimulationViewportFallback'

describe('SimulationViewportFallback', () => {
  it('keeps the 3D viewport footprint stable while the renderer loads', () => {
    const markup = renderToStaticMarkup(<SimulationViewportFallback />)

    expect(markup).toContain('simulation-viewport')
    expect(markup).toContain('加载 3D 可视化')
    expect(markup).toContain('Geant4 geometry preview')
    expect(markup).toContain('几何 0')
    expect(markup).toContain('轨迹 0')
    expect(markup).toContain('能量沉积 0')
  })
})
