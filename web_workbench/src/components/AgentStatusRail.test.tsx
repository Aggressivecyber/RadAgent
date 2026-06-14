import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AgentStatusRail from './AgentStatusRail'
import type { AgentCockpit } from '../lib/workbenchPresentation'

const cockpit: AgentCockpit = {
  agent: {
    stateLabel: '运行中',
    phaseLabel: 'Geant4 工程生成',
    currentAction: 'Generating detector construction module',
    workspace: '/tmp/radagent/job-42',
    changedFiles: '3 个文件',
  },
  fileGroups: [],
  recentActivity: [
    { title: 'model call start', statusLabel: '运行中', phaseLabel: '工程生成' },
    { title: 'g4 codegen persist', statusLabel: '通过', phaseLabel: '工程生成' },
  ],
}

describe('AgentStatusRail', () => {
  it('renders a promo-style agent cockpit status summary', () => {
    const markup = renderToStaticMarkup(
      <AgentStatusRail
        cockpit={cockpit}
        onHome={() => {}}
        quickActions={[
          { label: '状态', labelEn: 'Status', active: true, onSelect: () => {} },
          { label: '产物', labelEn: 'Files', active: false, onSelect: () => {} },
        ]}
      />,
    )

    expect(markup).toContain('Agent Cockpit')
    expect(markup).toContain('运行中')
    expect(markup).toContain('Geant4 工程生成')
    expect(markup).toContain('Generating detector construction module')
    expect(markup).toContain('3 个文件')
    expect(markup).toContain('/tmp/radagent/job-42')
    expect(markup).toContain('model call start')
    expect(markup).toContain('状态')
  })
})
