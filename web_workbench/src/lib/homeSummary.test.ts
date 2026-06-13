import { describe, expect, it } from 'vitest'
import { normalizeHomeSummary } from './homeSummary'

describe('normalizeHomeSummary', () => {
  it('uses showcase examples instead of exposing user project cards on Home', () => {
    const summary = normalizeHomeSummary({
      metrics: {
        projects: 2,
        jobs: 4,
        completed_jobs: 3,
        active_jobs: 1,
        artifacts: 9,
      },
      workflow_capabilities: [
        {
          name: 'Intent capture',
          description: 'Turn a request into a structured simulation objective.',
          command: '/run',
        },
      ],
      projects: [
        {
          job_id: 'job-1',
          title: 'HPGe detector response workflow',
          project_name: 'Detector Workflows',
          status: 'completed',
          phase: 'report',
          updated_at: '2026-06-13 09:12:00',
          artifact_count: 2,
          artifact_kinds: ['report', 'source'],
        },
      ],
      showcase_examples: [
        {
          id: 'example-hpge-coincidence',
          title: 'HPGe 反符合谱仪',
          subtitle: 'Anti-coincidence HPGe spectrometer',
          prompt: 'Build a Geant4 workflow for an HPGe anti-coincidence gamma spectrometer.',
          difficulty: 'advanced',
          tags: ['HPGe', 'anti-coincidence', 'spectrum'],
          validation_focus: ['geometry', 'scoring'],
        },
      ],
    })

    expect(summary.metrics.completed_jobs).toBe(3)
    expect(summary.metricTiles[0]).toEqual({ label: '项目 Projects', value: '2' })
    expect(summary.workflowCapabilities[0].name).toBe('Intent capture')
    expect(summary.showcaseCards[0]).toMatchObject({
      id: 'example-hpge-coincidence',
      title: 'HPGe 反符合谱仪',
      subtitle: 'Anti-coincidence HPGe spectrometer',
      prompt: expect.stringContaining('Geant4'),
      difficulty: 'advanced',
      tags: ['HPGe', 'anti-coincidence', 'spectrum'],
    })
  })

  it('keeps the home screen populated when there are no persisted jobs yet', () => {
    const summary = normalizeHomeSummary({
      metrics: {
        projects: 0,
        jobs: 0,
        completed_jobs: 0,
        active_jobs: 0,
        artifacts: 0,
      },
      workflow_capabilities: [],
      projects: [],
      showcase_examples: [],
    })

    expect(summary.workflowCapabilities).toHaveLength(6)
    expect(summary.showcaseCards).toHaveLength(4)
    expect(summary.showcaseCards[0].title).toBe('HPGe 反符合谱仪')
    expect(summary.showcaseCards[0].prompt).toContain('coincidence')
    expect(summary.metricTiles.map((tile) => tile.value)).toEqual(['0', '0', '0', '0'])
  })
})
