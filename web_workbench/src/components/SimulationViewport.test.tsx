import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import SimulationViewport, {
  depositPointSizeForExtent,
  focusComponentsForViewport,
  highlightedParticleTracks,
  orderedParticleTracks,
  particleColorForName,
  particleColorLegendFor,
  shouldShowSourcePreview,
  sourceStartMarkersForViewport,
  trackPointsForViewport,
  trackTubeRadiusForExtent,
  visualizationSceneSignature,
} from './SimulationViewport'
import type { VisualizationPayload } from '../lib/visualizationPayload'

const viewportPayload: VisualizationPayload = {
  status: 'ready',
  visualEvents: 100,
  warnings: [],
  sourceRays: [
    {
      sourceId: 'primary_gamma',
      particle: 'gamma',
      energy: { value: 662, unit: 'keV' },
      sourceShape: 'point',
      directionMode: 'mono',
      sampleIndex: 0,
      sampleCount: 1,
      start: [0, 0, -150.5],
      end: [0, 0, 75.25],
    },
  ],
  components: [
    {
      id: 'world',
      name: 'World',
      shape: 'box',
      material: 'G4_AIR',
      role: 'world',
      size: [2000, 2000, 2000],
      position: [0, 0, 0],
      rotation: [0, 0, 0],
      opacity: 0.08,
    },
    {
      id: 'detector',
      name: 'Detector',
      shape: 'cylinder',
      material: 'G4_Ge',
      role: 'edep_region',
      size: [1, 1, 150],
      position: [0, 0, 0],
      rotation: [0, 0, 0],
      opacity: 0.72,
    },
  ],
  tracks: [
    {
      eventId: 0,
      trackId: 1,
      particle: 'e-',
      energyMeV: 0.2,
      points: [
        [0, 0, -75],
        [0.01, 0.01, -74.9],
      ],
    },
    {
      eventId: 0,
      trackId: 2,
      particle: 'gamma',
      energyMeV: 1.25,
      points: [
        [0, 0, -180],
        [0, 0, -75],
      ],
    },
  ],
  deposits: [
    {
      eventId: 0,
      trackId: 1,
      volume: 'detector',
      position: [0, 0, -40],
      edepMeV: 0.1,
    },
  ],
}

describe('SimulationViewport', () => {
  it('uses Chinese-first workbench copy for visual simulation controls', () => {
    const markup = renderToStaticMarkup(<SimulationViewport payload={null} onRefresh={() => {}} />)

    expect(markup).toContain('等待可视化产物')
    expect(markup).toContain('参考网格')
    expect(markup).toContain('显示轨迹')
    expect(markup).toContain('刷新数据')
    expect(markup).toContain('几何 0')
    expect(markup).toContain('轨迹 0')
    expect(markup).toContain('能量沉积 0')
    expect(markup).toContain('仿真事件 100')
    expect(markup).toContain('运行模拟后生成几何、轨迹和能量沉积分布。')
  })

  it('focuses detector geometry instead of the large world box', () => {
    const components = focusComponentsForViewport(viewportPayload)

    expect(components.map((component) => component.id)).toEqual(['detector'])
  })

  it('keeps energy deposit markers small and distance attenuated', () => {
    expect(depositPointSizeForExtent(150)).toBeLessThan(2)
    expect(depositPointSizeForExtent(150)).toBeGreaterThanOrEqual(0.75)
  })

  it('prioritizes long incoming particle tracks over tiny secondaries', () => {
    const tracks = orderedParticleTracks(viewportPayload, true, 1)

    expect(tracks).toHaveLength(1)
    expect(tracks[0].particle).toBe('gamma')
  })

  it('does not promote long secondary electrons to highlighted incoming tracks', () => {
    const payload: VisualizationPayload = {
      ...viewportPayload,
      sourceRays: [],
      tracks: [
        {
          eventId: 0,
          trackId: 1,
          particle: 'e-',
          energyMeV: 0.12,
          points: [
            [0, 0, -75],
            [-103, -64, -140],
          ],
        },
      ],
    }

    expect(highlightedParticleTracks(payload, true)).toEqual([])
  })

  it('clips secondary electron tracks to the model bounds', () => {
    const track = {
      eventId: 0,
      trackId: 1,
      particle: 'e-',
      energyMeV: 0.12,
      points: [
        [0, 0, -75],
        [0, 0, -74.9],
        [-103, -64, -140],
      ],
    } satisfies VisualizationPayload['tracks'][number]

    expect(
      trackPointsForViewport(track, {
        min: [-100, -100, -75],
        max: [100, 100, 75],
      }),
    ).toEqual([
      [0, 0, -75],
      [0, 0, -74.9],
    ])
  })

  it('uses a stable scene signature for equivalent polling payloads', () => {
    const equivalentPayload = structuredClone(viewportPayload)

    expect(visualizationSceneSignature(viewportPayload)).toBe(visualizationSceneSignature(equivalentPayload))
  })

  it('assigns stable colors to common and unknown particle species', () => {
    const legend = particleColorLegendFor({
      ...viewportPayload,
      sourceRays: [
        ...viewportPayload.sourceRays,
        {
          sourceId: 'face_source',
          particle: 'neutron',
          energy: { value: 1, unit: 'MeV' },
          sourceShape: 'rectangle',
          directionMode: 'mono',
          sampleIndex: 0,
          sampleCount: 1,
          start: [0, -2, 0],
          end: [0, 2, 0],
        },
      ],
      tracks: [
        ...viewportPayload.tracks,
        { eventId: 1, trackId: 4, particle: 'proton', energyMeV: 150, points: [[0, 0, -1], [0, 0, 1]] },
        { eventId: 1, trackId: 5, particle: 'mu-', energyMeV: 2, points: [[0, 0, -1], [1, 0, 1]] },
        { eventId: 1, trackId: 6, particle: 'alpha', energyMeV: 5, points: [[0, 0, -1], [0, 1, 1]] },
      ],
    })

    expect(particleColorForName('electron')).toBe('#2aa7ff')
    expect(particleColorForName('gamma')).toBe('#f2cf3a')
    expect(particleColorForName('photon')).toBe('#f2cf3a')
    expect(particleColorForName('proton')).toBe('#ff8d3a')
    expect(particleColorForName('neutron')).toBe('#7c5cff')
    expect(legend.map((row) => row.particle)).toEqual(['gamma', 'neutron', 'e-', 'proton', 'mu-', 'alpha'])
    expect(legend.find((row) => row.particle === 'mu-')?.label).toBe('其他粒子1')
    expect(legend.find((row) => row.particle === 'alpha')?.label).toBe('其他粒子2')
  })

  it('shows source direction preview only before real particle tracks exist', () => {
    expect(shouldShowSourcePreview({ ...viewportPayload, tracks: [] })).toBe(true)
    expect(shouldShowSourcePreview(viewportPayload)).toBe(false)
  })

  it('marks source start points from real particle-flow samples before preview rays', () => {
    const tracks = Array.from({ length: 12 }, (_, index) => ({
      eventId: index,
      trackId: index + 1,
      particle: 'proton',
      energyMeV: 150,
      points: [
        [index, 0, -10],
        [index, 0, 10],
      ],
    })) satisfies VisualizationPayload['tracks']
    const markers = sourceStartMarkersForViewport({ ...viewportPayload, tracks }, true)

    expect(markers).toHaveLength(10)
    expect(markers.every((marker) => marker.kind === 'track')).toBe(true)
    expect(markers[0]).toMatchObject({
      label: 'source-start-1',
      start: [0, 0, -10],
      end: [0, 0, 10],
      particle: 'proton',
    })
  })

  it('keeps source start markers visible for point, beam, and surface preview rays', () => {
    const markers = sourceStartMarkersForViewport(
      {
        ...viewportPayload,
        tracks: [],
        sourceRays: [
          {
            sourceId: 'isotropic_point',
            particle: 'gamma',
            energy: {},
            sourceShape: 'point',
            directionMode: 'random',
            sampleIndex: 0,
            sampleCount: 3,
            start: [0, 0, 0],
            end: [10, 0, 0],
          },
          {
            sourceId: 'isotropic_point:1',
            particle: 'gamma',
            energy: {},
            sourceShape: 'point',
            directionMode: 'random',
            sampleIndex: 1,
            sampleCount: 3,
            start: [0, 0, 0],
            end: [0, 10, 0],
          },
          {
            sourceId: 'face_source',
            particle: 'neutron',
            energy: {},
            sourceShape: 'rectangle',
            directionMode: 'mono',
            sampleIndex: 0,
            sampleCount: 2,
            start: [-5, -5, -20],
            end: [-5, -5, 20],
          },
          {
            sourceId: 'face_source:1',
            particle: 'neutron',
            energy: {},
            sourceShape: 'rectangle',
            directionMode: 'mono',
            sampleIndex: 1,
            sampleCount: 2,
            start: [5, 5, -20],
            end: [5, 5, 20],
          },
        ],
      },
      true,
    )

    expect(markers.map((marker) => marker.kind)).toEqual(['point', 'point', 'surface', 'surface'])
    expect(markers.every((marker) => marker.label.startsWith('source-start-'))).toBe(true)
  })

  it('keeps neutron tracks from becoming oversized while thickening secondary tracks', () => {
    const neutronRadius = trackTubeRadiusForExtent(
      { eventId: 0, trackId: 1, particle: 'neutron', energyMeV: 14, points: [[0, 0, 0], [0, 0, 1]] },
      150,
    )
    const electronRadius = trackTubeRadiusForExtent(
      { eventId: 0, trackId: 2, particle: 'e-', energyMeV: 1, points: [[0, 0, 0], [0, 0, 1]] },
      150,
    )

    expect(neutronRadius).toBeLessThan(0.5)
    expect(electronRadius).toBeGreaterThan(0.2)
  })

  it('adds a human-review focus layer when model confirmation is pending', () => {
    const markup = renderToStaticMarkup(
      <SimulationViewport payload={viewportPayload} onRefresh={() => {}} reviewFocus />,
    )

    expect(markup).toContain('simulation-viewport review-focus')
    expect(markup).toContain('模型核对')
    expect(markup).toContain('请对照参数清单检查几何、材料和粒子源是否符合预期')
  })
})
