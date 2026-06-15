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
    statusChips: [],
  },
  fileGroups: [],
  recentActivity: [
    { title: 'model call start', detail: 'Generating module', statusLabel: '运行中', phaseLabel: '工程生成' },
    { title: 'g4 codegen persist', detail: 'Persisted files', statusLabel: '通过', phaseLabel: '工程生成' },
  ],
  llmDebugCalls: [],
}

describe('AgentStatusRail', () => {
  it('renders a fixed Copilot conversation rail without workspace navigation', () => {
    const markup = renderToStaticMarkup(
      <AgentStatusRail
        cockpit={cockpit}
        timeline={[
          {
            id: 'command:status',
            kind: 'command',
            title: '查看状态',
            body: 'Running g4_codegen',
            status: 'success',
            meta: 'status',
          },
          {
            id: 'command:chat',
            kind: 'command',
            title: '对话',
            body: '当前工作流下一步是什么？',
            status: 'success',
            meta: 'chat',
          },
        ]}
        onHome={() => {}}
        submissionFeedback={{
          tone: 'running',
          title: '正在仿真',
          detail: 'Agent 正在执行仿真工作流，状态会同步到侧边栏。',
        }}
        onAskCopilot={() => {}}
      />,
    )

    expect(markup).toContain('Copilot')
    expect(markup).toContain('对话历史')
    expect(markup).toContain('当前工作流下一步是什么？')
    expect(markup).not.toContain('Running g4_codegen')
    expect(markup).toContain('仿真协作助手')
    expect(markup).toContain('仿真工作流')
    expect(markup).toContain('正在仿真')
    expect(markup).toContain('问 Copilot')
    expect(markup).not.toContain('文件变更')
    expect(markup).not.toContain('/tmp/radagent/job-42')
    expect(markup).not.toContain('Geant4 工程生成')
    expect(markup).not.toContain('model call start')
    expect(markup).not.toContain('状态</strong>')
  })
})
