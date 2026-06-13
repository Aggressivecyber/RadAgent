import { describe, expect, it } from 'vitest'
import { createDetailPanel, isDetailPanelView } from './detailPanels'

describe('detail inspector presentation', () => {
  it('formats a job detail without requiring raw JSON', () => {
    const panel = createDetailPanel('job', {
      job_id: 'job-1',
      user_query: 'Build a silicon slab detector',
      status: 'paused',
      current_phase: 'g4_codegen',
      project_name: 'Detector Workflows',
      created_at: '2026-06-13T08:00:00Z',
      workspace_root: '/workspace/radagent',
      completed_phases: ['prepare_workspace', 'context'],
    })

    expect(isDetailPanelView('job')).toBe(true)
    expect(panel).toMatchObject({
      title: 'Build a silicon slab detector',
      status: 'paused',
      subtitle: 'job-1',
      metrics: [
        { label: 'Phase', value: 'g4_codegen' },
        { label: 'Project', value: 'Detector Workflows' },
        { label: 'Completed', value: '2 phases' },
      ],
    })
    expect(panel?.sections[0].rows).toContainEqual({ label: 'Workspace', value: '/workspace/radagent' })
  })

  it('formats gate, revision, and project records as first-class details', () => {
    const gate = createDetailPanel('gate', {
      gate_id: 20,
      status: 'pass',
      message: 'Credibility evidence is consistent.',
      credibility_level: 'high',
      phase: 'validation',
    })
    const revision = createDetailPanel('revision', {
      revision_id: 'rev-1',
      status: 'ready',
      user_request: 'Tighten detector spacing.',
      patch_status: 'generated',
      candidate_project_dir: '/workspace/revisions/rev-1',
    })
    const project = createDetailPanel('project', {
      slug: 'default',
      name: 'Default Project',
      description: 'Default RadAgent workspace project',
      root_path: '/workspace',
      last_opened_at: '2026-06-13T09:00:00Z',
    })

    expect(gate).toMatchObject({
      title: 'Gate 20',
      status: 'pass',
      subtitle: 'validation',
      preview: 'Credibility evidence is consistent.',
      metrics: [
        { label: 'Level', value: 'high' },
        { label: 'Phase', value: 'validation' },
      ],
    })
    expect(revision).toMatchObject({
      title: 'rev-1',
      status: 'ready',
      subtitle: 'Tighten detector spacing.',
      preview: 'Tighten detector spacing.',
    })
    expect(revision?.sections[0].rows).toContainEqual({
      label: 'Candidate',
      value: '/workspace/revisions/rev-1',
    })
    expect(project).toMatchObject({
      title: 'Default Project',
      status: 'default',
      subtitle: '/workspace',
      preview: 'Default RadAgent workspace project',
    })
  })
})
