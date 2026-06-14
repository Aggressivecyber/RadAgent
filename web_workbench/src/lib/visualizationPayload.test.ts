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
    })

    expect(payload.status).toBe('ready')
    expect(payload.visualEvents).toBe(100)
    expect(payload.components[0].size).toEqual([10, 10, 0.3])
    expect(payload.tracks[0].points.at(-1)).toEqual([0.1, 0, 5])
    expect(payload.deposits[0].edepMeV).toBe(0.5)
  })

  it('keeps deposits visible while particle tracks are toggled off', () => {
    const payload: VisualizationPayload = {
      status: 'ready',
      visualEvents: 100,
      components: [{ id: 'detector', name: 'Detector', shape: 'box', material: 'G4_Si', size: [1, 1, 1], position: [0, 0, 0], rotation: [0, 0, 0], opacity: 0.4 }],
      tracks: [{ eventId: 0, trackId: 1, particle: 'proton', energyMeV: 10, points: [[0, 0, -1], [0, 0, 1]] }],
      deposits: [{ eventId: 0, trackId: 1, volume: 'detector', position: [0, 0, 0], edepMeV: 1 }],
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
      tracks,
      deposits: [{ eventId: 3, trackId: 4, volume: 'detector', position: [0, 0, 0], edepMeV: 0.2 }],
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
