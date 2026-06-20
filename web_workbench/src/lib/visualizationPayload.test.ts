import { describe, expect, it } from 'vitest'
import {
  layerStats,
  normalizeVisualizationPayload,
  type VisualizationPayload,
} from './visualizationPayload'

describe('visualization payload helpers', () => {
  it('normalizes real geometry tracks and energy deposits for the 3D viewport', () => {
    const payload = normalizeVisualizationPayload({
      status: 'ready',
      source: { visual_events: 100 },
      geometry: {
        components: [
          {
            id: 'detector',
            name: 'Silicon Detector',
            shape: 'box',
            material: 'G4_Si',
            size_mm: [10, 10, 0.3],
            position_mm: [0, 0, 0],
          },
        ],
      },
      source_rays: [
        {
          source_id: 'primary_gamma',
          particle: 'gamma',
          energy: { value: 662, unit: 'keV' },
          start_mm: [0, 0, -150.5],
          end_mm: [0, 0, 75.25],
        },
      ],
      tracks: [
        {
          event_id: 1,
          track_id: 7,
          particle: 'proton',
          points_mm: [
            [0, 0, -5],
            [0, 0, 0],
            [0.1, 0, 5],
          ],
        },
      ],
      deposits: [{ event_id: 1, track_id: 7, position_mm: [0, 0, 0], edep_MeV: 0.5 }],
      analysis: {
        source: 'full_run',
        stats: { track_count: 250, deposit_count: 500, total_edep_MeV: 12.5 },
        particle_counts: [
          { particle: 'proton', count: 180 },
          { particle: 'gamma', count: 70 },
        ],
        energy_points: [
          { x: 0, y: 0, z: 0, edep_MeV: 0.5 },
        ],
        slice_planes: {
          z: {
            axis: 'z',
            values: [0],
            slices: [
              {
                value: 0,
                x_axis: 'x',
                y_axis: 'y',
                x: [-1, 0, 1],
                y: [-1, 0, 1],
                z: [
                  [0, 0, 0],
                  [0, 0.5, 0],
                  [0, 0, 0],
                ],
              },
            ],
          },
        },
      },
    })

    expect(payload.status).toBe('ready')
    expect(payload.visualEvents).toBe(100)
    expect(payload.components[0].size).toEqual([10, 10, 0.3])
    expect(payload.sourceRays[0].start).toEqual([0, 0, -150.5])
    expect(payload.sourceRays[0].end).toEqual([0, 0, 75.25])
    expect(payload.tracks[0].points.at(-1)).toEqual([0.1, 0, 5])
    expect(payload.deposits[0].edepMeV).toBe(0.5)
    expect(payload.analysis!.stats.trackCount).toBe(250)
    expect(payload.analysis!.particleCounts).toEqual([
      { particle: 'proton', count: 180 },
      { particle: 'gamma', count: 70 },
    ])
    expect(payload.analysis!.energyPoints[0]).toEqual({ x: 0, y: 0, z: 0, edepMeV: 0.5 })
    expect(payload.analysis!.slicePlanes.z?.slices[0].z[1][1]).toBe(0.5)
  })

  it('keeps deposits visible while particle tracks are toggled off', () => {
    const payload: VisualizationPayload = {
      status: 'ready',
      visualEvents: 100,
      components: [{ id: 'detector', name: 'Detector', shape: 'box', material: 'G4_Si', size: [1, 1, 1], position: [0, 0, 0], rotation: [0, 0, 0], opacity: 0.4 }],
      sourceRays: [],
      tracks: [{ eventId: 0, trackId: 1, particle: 'proton', energyMeV: 10, points: [[0, 0, -1], [0, 0, 1]] }],
      deposits: [{ eventId: 0, trackId: 1, volume: 'detector', position: [0, 0, 0], edepMeV: 1 }],
      analysis: {
        source: 'full_run',
        stats: { trackCount: 1, depositCount: 1, totalEdepMeV: 1 },
        particleCounts: [{ particle: 'proton', count: 1 }],
        energyPoints: [{ x: 0, y: 0, z: 0, edepMeV: 1 }],
        slicePlanes: {},
      },
      warnings: [],
    }

    expect(layerStats(payload, true)).toEqual({
      components: 1,
      tracks: 1,
      deposits: 1,
      visibleTrackPoints: 2,
    })
    expect(layerStats(payload, false)).toEqual({
      components: 1,
      tracks: 0,
      deposits: 1,
      visibleTrackPoints: 0,
    })
  })

  it('caps visible particle trajectories at the 100-event workbench view', () => {
    const tracks = Array.from({ length: 105 }, (_, index) => ({
      eventId: index,
      trackId: index + 1,
      particle: 'proton',
      energyMeV: 10,
      points: [
        [0, 0, -1],
        [0, 0, 1],
      ] as [number, number, number][],
    }))
    const payload: VisualizationPayload = {
      status: 'ready',
      visualEvents: 100,
      components: [],
      sourceRays: [],
      tracks,
      deposits: [{ eventId: 3, trackId: 4, volume: 'detector', position: [0, 0, 0], edepMeV: 0.2 }],
      analysis: {
        source: 'full_run',
        stats: { trackCount: 105, depositCount: 1, totalEdepMeV: 0.2 },
        particleCounts: [{ particle: 'proton', count: 105 }],
        energyPoints: [{ x: 0, y: 0, z: 0, edepMeV: 0.2 }],
        slicePlanes: {},
      },
      warnings: [],
    }

    expect(layerStats(payload, true)).toEqual({
      components: 0,
      tracks: 100,
      deposits: 1,
      visibleTrackPoints: 200,
    })
    expect(layerStats(payload, false)).toEqual({
      components: 0,
      tracks: 0,
      deposits: 1,
      visibleTrackPoints: 0,
    })
  })
})
