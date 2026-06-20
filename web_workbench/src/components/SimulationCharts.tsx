import { useEffect, useMemo, useState, type ComponentType } from 'react'
import type {
  VisualizationParticleCount,
  VisualizationPayload,
  VisualizationSliceAxis,
} from '../lib/visualizationPayload'

type SimulationChartsProps = {
  payload: VisualizationPayload | null
}

type PlotlyData = Record<string, unknown>
type PlotlyLayout = Record<string, unknown>
type PlotlyConfig = Record<string, unknown>
type PlotlyComponent = ComponentType<Record<string, unknown>>

export type EnergyDistributionBin = {
  axis: VisualizationSliceAxis
  center: number
  low: number
  high: number
  edepMeV: number
}

const axisOptions: VisualizationSliceAxis[] = ['x', 'y', 'z']
const particlePalette = ['#b94138', '#23785a', '#2a7fba', '#7c5cff', '#b7840c', '#5f6f52', '#6b7b8c', '#d08a39']
const pieLabelPercentThreshold = 0.08
const plotConfig: PlotlyConfig = {
  displaylogo: false,
  responsive: true,
  scrollZoom: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
}

export function particlePieConfig(): PlotlyConfig {
  return {
    ...plotConfig,
    displayModeBar: false,
    scrollZoom: false,
  }
}

export function particlePieData(particles: VisualizationParticleCount[]): PlotlyData[] {
  const total = particles.reduce((sum, item) => sum + item.count, 0)
  const textposition = particles.map((item) =>
    total > 0 && item.count / total > pieLabelPercentThreshold ? 'inside' : 'none',
  )
  return [
    {
      type: 'pie',
      labels: particles.map((item) => item.particle),
      values: particles.map((item) => item.count),
      marker: { colors: particles.map((_, index) => particlePalette[index % particlePalette.length]) },
      hole: 0.42,
      sort: false,
      textinfo: 'none',
      textposition,
      texttemplate: textposition.map((position) => (position === 'inside' ? '%{label}<br>%{percent}' : '')),
      insidetextorientation: 'radial',
      hovertemplate: '%{label}<br>%{value} tracks<br>%{percent}<extra></extra>',
    },
  ]
}

let plotlyComponentPromise: Promise<PlotlyComponent> | null = null

export function resolvePlotlyFactory(moduleValue: unknown): (plotly: unknown) => PlotlyComponent {
  const direct = moduleValue as { default?: unknown }
  const candidate = direct.default
  if (typeof candidate === 'function') {
    return candidate as (plotly: unknown) => PlotlyComponent
  }
  const nested = candidate as { default?: unknown }
  if (nested && typeof nested.default === 'function') {
    return nested.default as (plotly: unknown) => PlotlyComponent
  }
  throw new Error('react-plotly factory module did not expose a callable default export')
}

function loadPlotlyComponent(): Promise<PlotlyComponent> {
  if (!plotlyComponentPromise) {
    plotlyComponentPromise = Promise.all([
      import('react-plotly.js/factory'),
      import('plotly.js-dist-min'),
    ]).then(([factoryModule, plotlyModule]) => {
      const createPlotlyComponent = resolvePlotlyFactory(factoryModule)
      return createPlotlyComponent(plotlyModule.default) as PlotlyComponent
    })
  }
  return plotlyComponentPromise
}

export function particleClassificationSeries(payload: VisualizationPayload): VisualizationParticleCount[] {
  return [...(payload.analysis?.particleCounts ?? [])]
    .filter((item) => item.count > 0)
    .sort((left, right) => right.count - left.count || left.particle.localeCompare(right.particle))
}

export function energyDistributionSeries(
  payload: VisualizationPayload,
  axis: VisualizationSliceAxis,
  bins = 28,
): EnergyDistributionBin[] {
  const points = payload.analysis?.energyPoints ?? []
  if (points.length === 0) {
    return []
  }
  const values = points.map((point) => point[axis]).filter(Number.isFinite)
  if (values.length === 0) {
    return []
  }
  const low = Math.min(...values)
  const high = Math.max(...values)
  const width = Math.max((high - low) / bins, Number.EPSILON)
  const result = Array.from({ length: bins }, (_, index) => ({
    axis,
    low: low + width * index,
    high: low + width * (index + 1),
    center: low + width * (index + 0.5),
    edepMeV: 0,
  }))
  for (const point of points) {
    const value = point[axis]
    const index = Math.min(bins - 1, Math.max(0, Math.floor((value - low) / width)))
    result[index].edepMeV += point.edepMeV
  }
  return result
}

function formatNumber(value: number, digits = 2): string {
  if (!Number.isFinite(value)) {
    return '0'
  }
  if (Math.abs(value) >= 1000) {
    return value.toExponential(2)
  }
  if (Math.abs(value) >= 100) {
    return value.toFixed(0)
  }
  if (Math.abs(value) >= 10) {
    return value.toFixed(1)
  }
  return value.toFixed(digits)
}

function axisLabel(axis: VisualizationSliceAxis): string {
  return `${axis.toUpperCase()} mm`
}

function baseLayout(height: number): PlotlyLayout {
  return {
    height,
    margin: { l: 54, r: 18, t: 12, b: 48 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {
      family: 'IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, monospace',
      color: '#5c554a',
      size: 10,
    },
  }
}

export function particlePieLayout(): PlotlyLayout {
  return {
    ...baseLayout(360),
    margin: { l: 8, r: 8, t: 8, b: 8 },
    showlegend: true,
    legend: { orientation: 'h', x: 0, y: -0.08, font: { size: 9 } },
  }
}

function PlotlyChart({
  data,
  layout,
  config = plotConfig,
  className,
  ariaLabel,
  identity,
}: {
  data: PlotlyData[]
  layout: PlotlyLayout
  config?: PlotlyConfig
  className?: string
  ariaLabel: string
  identity: string
}) {
  const [PlotComponent, setPlotComponent] = useState<PlotlyComponent | null>(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let cancelled = false
    loadPlotlyComponent()
      .then((component) => {
        if (!cancelled) {
          setLoadError('')
          setPlotComponent(() => component)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : String(error))
          setPlotComponent(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (loadError) {
    return (
      <div className={`plotly-chart-shell is-error ${className ?? ''}`} role="img" aria-label={ariaLabel}>
        <span>Plotly 图表初始化失败</span>
        <small>{loadError}</small>
      </div>
    )
  }

  if (!PlotComponent) {
    return (
      <div className={`plotly-chart-shell is-loading ${className ?? ''}`} role="img" aria-label={ariaLabel}>
        <span>Plotly 图表载入中</span>
      </div>
    )
  }

  return (
    <PlotComponent
      key={identity}
      data={data}
      layout={layout}
      config={config}
      className={`plotly-chart-shell ${className ?? ''}`}
      style={{ width: '100%', height: '100%' }}
      useResizeHandler
    />
  )
}

function EnergyAxisDistributionCard({ payload }: { payload: VisualizationPayload }) {
  const [axis, setAxis] = useState<VisualizationSliceAxis>('z')
  const energyPoints = payload.analysis?.energyPoints ?? []
  const totalEdep = payload.analysis?.stats.totalEdepMeV ?? 0
  const series = useMemo(() => energyDistributionSeries(payload, axis), [payload, axis])

  const lineData = useMemo<PlotlyData[]>(() => {
    return [
      {
        type: 'scatter',
        mode: 'lines+markers',
        x: series.map((bin) => bin.center),
        y: series.map((bin) => bin.edepMeV),
        line: { color: '#23785a', width: 3, shape: 'spline' },
        marker: { color: '#b94138', size: 5 },
        fill: 'tozeroy',
        fillcolor: 'rgba(35,120,90,0.12)',
        hovertemplate: `${axis.toUpperCase()} %{x:.3g} mm<br>Edep %{y:.4g} MeV<extra></extra>`,
      },
    ]
  }, [axis, series])

  const lineLayout = useMemo<PlotlyLayout>(() => {
    return {
      ...baseLayout(360),
      xaxis: { title: axisLabel(axis), gridcolor: 'rgba(104,98,90,0.18)' },
      yaxis: { title: 'Edep MeV', gridcolor: 'rgba(104,98,90,0.18)', rangemode: 'tozero' },
    }
  }, [axis])

  return (
    <article className="energy-axis-card">
      <header>
        <div>
          <strong>轴向能量沉积分布</strong>
          <span>全量运行数据 · {energyPoints.length} 个沉积采样点</span>
        </div>
        <em>Σ {formatNumber(totalEdep)} MeV</em>
      </header>
      <div className="axis-chart-controls" role="group" aria-label="能量沉积分布坐标轴">
        {axisOptions.map((item) => (
          <button
            key={item}
            type="button"
            className={item === axis ? 'active' : ''}
            onClick={() => setAxis(item)}
          >
            {item.toUpperCase()}
          </button>
        ))}
      </div>
      <PlotlyChart
        data={lineData}
        layout={lineLayout}
        ariaLabel="轴向能量沉积分布图"
        identity={`energy-axis-${axis}`}
      />
    </article>
  )
}

function ParticleTypePieCard({ payload }: { payload: VisualizationPayload }) {
  const particles = particleClassificationSeries(payload)
  const total = particles.reduce((sum, item) => sum + item.count, 0)
  const pieData = useMemo<PlotlyData[]>(() => {
    return particlePieData(particles)
  }, [particles])
  const pieLayout = useMemo<PlotlyLayout>(() => {
    return particlePieLayout()
  }, [])

  return (
    <article className="particle-pie-card">
      <header>
        <div>
          <strong>粒子类型饼图</strong>
          <span>全量运行数据 · 不受上方 100 粒子显示限制</span>
        </div>
        <em>{total} tracks</em>
      </header>
      <PlotlyChart
        data={pieData}
        layout={pieLayout}
        config={particlePieConfig()}
        className="particle-pie-plot"
        ariaLabel="粒子类型饼图"
        identity="particle-type-pie"
      />
      <div className="particle-pie-list" aria-label="粒子统计明细">
        {particles.slice(0, 6).map((item, index) => (
          <span key={item.particle}>
            <i style={{ backgroundColor: particlePalette[index % particlePalette.length] }} />
            {item.particle} {item.count}
          </span>
        ))}
      </div>
    </article>
  )
}

export default function SimulationCharts({ payload }: SimulationChartsProps) {
  const data = payload
  const hasEnergyDistribution = (data?.analysis?.energyPoints.length ?? 0) > 0
  const hasParticleClassification = (data?.analysis?.particleCounts.length ?? 0) > 0
  const hasData = Boolean(data && (hasEnergyDistribution || hasParticleClassification))

  return (
    <section className="simulation-analysis-panel" aria-label="Simulation data analysis charts">
      <div className="panel-title">
        数据分析
        <small>高级图表</small>
      </div>
      {data && hasData ? (
        <div className="simulation-chart-grid">
          {hasEnergyDistribution ? <EnergyAxisDistributionCard payload={data} /> : null}
          {hasParticleClassification ? <ParticleTypePieCard payload={data} /> : null}
        </div>
      ) : (
        <p className="simulation-analysis-empty">等待运行仿真后生成全量轴向能量沉积分布和粒子类型饼图。</p>
      )}
    </section>
  )
}
