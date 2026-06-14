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
      status: '暂停审查',
      subtitle: 'job-1',
      metrics: [
        { label: '阶段', value: '工程生成' },
        { label: '项目', value: 'Detector Workflows' },
        { label: '已完成', value: '2 个阶段' },
      ],
    })
    expect(panel?.sections[0].title).toBe('工作流')
    expect(panel?.sections[0].rows).toContainEqual({ label: '工作区', value: '/workspace/radagent' })
    expect(panel?.actions).toEqual([
      {
        label: '切换到工作区',
        labelEn: 'Switch workspace',
        command: '/resume job-1',
        intent: 'neutral',
      },
      {
        label: '继续运行',
        labelEn: 'Continue run',
        command: '/retry job-1',
        intent: 'primary',
      },
    ])
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
      title: '门禁 20',
      status: '通过',
      subtitle: '验证门禁',
      preview: 'Credibility evidence is consistent.',
      metrics: [
        { label: '级别', value: '高' },
        { label: '阶段', value: '验证门禁' },
      ],
    })
    expect(revision).toMatchObject({
      title: 'rev-1',
      status: '就绪',
      subtitle: 'Tighten detector spacing.',
      preview: 'Tighten detector spacing.',
    })
    expect(revision?.sections[0].rows).toContainEqual({
      label: '候选目录',
      value: '/workspace/revisions/rev-1',
    })
    expect(project).toMatchObject({
      title: 'Default Project',
      status: '默认',
      subtitle: '/workspace',
      preview: 'Default RadAgent workspace project',
    })
  })
})
