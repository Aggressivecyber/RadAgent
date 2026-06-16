import { describe, expect, it } from 'vitest'
import { createCollectionPanel } from './collectionPanels'

describe('collection inspector presentation', () => {
  it('formats jobs as workflow records', () => {
    const panel = createCollectionPanel('jobs', [
      {
        job_id: 'job-1',
        user_query: 'Build a silicon slab detector',
        status: 'completed',
        current_phase: 'report',
        project_name: 'Detector Workflows',
      },
    ])

    expect(panel?.title).toBe('作业列表')
    expect(panel?.summary).toBe('1 个作业')
    expect(panel?.rows[0]).toMatchObject({
      title: 'Build a silicon slab detector',
      status: '已完成',
      detail: '报告 · Detector Workflows',
      meta: 'job-1',
    })
  })

  it('formats artifacts with path, kind, stage and size', () => {
    const panel = createCollectionPanel('artifacts', [
      {
        path: '/tmp/final_report.md',
        kind: 'report',
        stage: 'report',
        size_bytes: 4096,
      },
    ])

    expect(panel?.rows[0]).toMatchObject({
      title: 'final_report.md',
      status: '报告',
      detail: '报告 · 4 KB',
      meta: '/tmp/final_report.md',
    })
  })

  it('formats gates and revisions with their decision context', () => {
    const gates = createCollectionPanel('gates', [
      {
        gate_id: 20,
        status: 'pass',
        message: 'Credibility evidence is consistent.',
        credibility_level: 'high',
      },
    ])
    const revisions = createCollectionPanel('revisions', [
      {
        revision_id: 'rev-1',
        status: 'completed',
        patch_status: 'applied',
        user_request: 'Tighten detector spacing.',
      },
    ])

    expect(gates?.rows[0]).toMatchObject({
      title: '门禁 20',
      status: '通过',
      detail: 'Credibility evidence is consistent.',
      meta: '高',
    })
    expect(revisions?.rows[0]).toMatchObject({
      title: 'rev-1',
      status: '已完成',
      detail: 'Tighten detector spacing.',
      meta: '已应用',
    })
  })

  it('formats projects as selectable workspaces', () => {
    const panel = createCollectionPanel('projects', [
      {
        slug: 'default',
        name: 'Default Project',
        description: 'Default RadAgent workspace project',
        root_path: '/workspace',
      },
    ])

    expect(panel?.rows[0]).toMatchObject({
      title: 'Default Project',
      status: '默认',
      detail: 'Default RadAgent workspace project',
      meta: '/workspace',
    })
  })
})
