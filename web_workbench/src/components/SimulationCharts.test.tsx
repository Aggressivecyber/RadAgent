import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import SimulationCharts, {
  energyDistributionSeries,
  particlePieData,
  particlePieConfig,
  particlePieLayout,
  particleClassificationSeries,
  resolvePlotlyFactory,
} from './SimulationCharts'
import type { VisualizationPayload } from '../lib/visualizationPayload'

const payload: VisualizationPayload = {
  status: 'ready',
  visualEvents: 100,
  warnings: [],
  sourceRays: [],
  components: [],
  tracks: [
    { eventId: 0, trackId: 1, particle: 'proton', energyMeV: 150, points: [[0, 0, -5], [0, 0, 5]] },
    { eventId: 1, trackId: 2, particle: 'gamma', energyMeV: 1.25, points: [[0, 0, -3], [0, 0, 3]] },
    { eventId: 2, trackId: 3, particle: 'proton', energyMeV: 149, points: [[0, 0, -2], [0, 0, 4]] },
  ],
  deposits: [
    { eventId: 0, trackId: 1, volume: 'water', position: [0, 0, -4], edepMeV: 0.1 },
    { eventId: 0, trackId: 1, volume: 'water', position: [0, 0, 0], edepMeV: 0.5 },
    { eventId: 1, trackId: 2, volume: 'silicon', position: [0, 0, 4], edepMeV: 0.2 },
  ],
  analysis: {
    source: 'full_run',
    stats: {
      trackCount: 250,
      depositCount: 1000,
      totalEdepMeV: 42.8,
    },
    particleCounts: [
      { particle: 'proton', count: 210 },
      { particle: 'gamma', count: 32 },
      { particle: 'electron', count: 8 },
    ],
    energyPoints: [
      { x: -1, y: 0, z: -4, edepMeV: 0.1 },
      { x: 0, y: 0, z: 0, edepMeV: 0.5 },
      { x: 1, y: 0, z: 4, edepMeV: 0.2 },
    ],
    slicePlanes: {
      z: {
        axis: 'z',
        values: [-4, 0, 4],
        slices: [
          { value: -4, xAxis: 'x', yAxis: 'y', x: [-1, 0, 1], y: [-1, 0, 1], z: [[0, 0, 0], [0, 0.1, 0], [0, 0, 0]] },
          { value: 0, xAxis: 'x', yAxis: 'y', x: [-1, 0, 1], y: [-1, 0, 1], z: [[0, 0, 0], [0, 0.5, 0], [0, 0, 0]] },
          { value: 4, xAxis: 'x', yAxis: 'y', x: [-1, 0, 1], y: [-1, 0, 1], z: [[0, 0, 0], [0, 0.2, 0], [0, 0, 0]] },
        ],
      },
    },
  },
}

describe('SimulationCharts', () => {
  it('derives particle classification from full-run analysis instead of capped visible tracks', () => {
    expect(particleClassificationSeries(payload)).toEqual([
      { particle: 'proton', count: 210 },
      { particle: 'gamma', count: 32 },
      { particle: 'electron', count: 8 },
    ])
  })

  it('derives axis energy deposition distribution from full-run analysis points', () => {
    const series = energyDistributionSeries(payload, 'z', 3)

    expect(series.map((bin) => Number(bin.edepMeV.toFixed(1)))).toEqual([0.1, 0.5, 0.2])
    expect(series[0].axis).toBe('z')
  })

  it('unwraps Vite CommonJS default wrappers for react-plotly factory', () => {
    const factory = () => 'plot'

    expect(resolvePlotlyFactory({ default: factory })).toBe(factory)
    expect(resolvePlotlyFactory({ default: { default: factory } })).toBe(factory)
  })

  it('renders only the axis energy distribution and particle pie charts from full-run data', () => {
    const markup = renderToStaticMarkup(<SimulationCharts payload={payload} />)

    expect(markup).toContain('数据分析')
    expect(markup).toContain('高级图表')
    expect(markup).toContain('轴向能量沉积分布')
    expect(markup).toContain('X')
    expect(markup).toContain('Y')
    expect(markup).toContain('Z')
    expect(markup).toContain('粒子类型饼图')
    expect(markup).toContain('全量运行数据')
    expect(markup).not.toContain('三维能量沉积热图')
    expect(markup).not.toContain('二维截面热力图')
    expect(markup).not.toContain('Z 深度剂量')
    expect(markup).not.toContain('每步 Edep 频次')
  })

  it('keeps particle pie layout free of Cartesian axes that can leave stale tick marks', () => {
    const layout = particlePieLayout()

    expect(layout).not.toHaveProperty('xaxis')
    expect(layout).not.toHaveProperty('yaxis')
    expect(layout).toMatchObject({
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
    })
  })

  it('disables Plotly chrome on the particle pie so tool buttons do not read as tick marks', () => {
    const config = particlePieConfig()

    expect(config).toMatchObject({
      displayModeBar: false,
      scrollZoom: false,
    })
  })

  it('labels only particle slices above 8 percent inside the pie to avoid guide lines', () => {
    const trace = particlePieData([
      { particle: 'proton', count: 83 },
      { particle: 'gamma', count: 9 },
      { particle: 'electron', count: 8 },
    ])[0]

    expect(trace).toMatchObject({
      textinfo: 'none',
      textposition: ['inside', 'inside', 'none'],
      texttemplate: ['%{label}<br>%{percent}', '%{label}<br>%{percent}', ''],
    })
    expect(trace.textposition).not.toContain('outside')
  })
})
