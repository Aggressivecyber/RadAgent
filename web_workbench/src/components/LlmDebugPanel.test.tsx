import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import LlmDebugPanel from './LlmDebugPanel'
import type { AgentCockpit } from '../lib/workbenchPresentation'

const cockpit: AgentCockpit = {
  agent: {
    stateLabel: '运行中',
    phaseLabel: '工程生成',
    currentAction: 'Generating module',
    workspace: '/tmp/job',
    changedFiles: '2 个文件',
    statusChips: [],
  },
  fileGroups: [],
  recentActivity: [],
  llmDebugCalls: [
    {
      id: 'call-running',
      phase: 'context_summary',
      phaseLabel: 'context summary',
      moduleName: 'coordinate_core_modules_context',
      moduleLabel: 'Coordinate Core Modules Context',
      modelName: 'mimo-v2.5',
      status: 'running',
      statusLabel: '运行中',
      durationLabel: '进行中',
      promptSummary: 'Context summary prompt',
      promptCharsLabel: '300 字符',
      outputSummary: '等待模型输出',
      outputCharsLabel: '',
      artifactPath: 'logs/model_calls/call-running_context_summary.json',
      createdAt: '2026-06-14T08:02:00Z',
    },
    {
      id: 'call-failed',
      phase: 'codegen',
      phaseLabel: 'codegen',
      moduleName: 'detector_construction',
      moduleLabel: 'Detector Construction',
      modelName: 'mimo-v2.5-pro',
      status: 'error',
      statusLabel: '失败',
      durationLabel: '16.2 秒',
      promptSummary: 'Detector prompt',
      promptCharsLabel: '12,000 字符',
      outputSummary: 'Provider timeout',
      outputCharsLabel: '',
      artifactPath: 'logs/model_calls/call-failed_detector_codegen.json',
      createdAt: '2026-06-14T08:01:00Z',
    },
  ],
}

describe('LlmDebugPanel', () => {
  it('renders current and recent LLM call fields for live debugging', () => {
    const markup = renderToStaticMarkup(<LlmDebugPanel cockpit={cockpit} />)

    expect(markup).toContain('LLM 实时 debug')
    expect(markup).toContain('context summary')
    expect(markup).toContain('Coordinate Core Modules Context')
    expect(markup).toContain('mimo-v2.5')
    expect(markup).toContain('运行中')
    expect(markup).toContain('进行中')
    expect(markup).toContain('Context summary prompt')
    expect(markup).toContain('300 字符')
    expect(markup).toContain('等待模型输出')
    expect(markup).toContain('logs/model_calls/call-running_context_summary.json')
    expect(markup).toContain('Provider timeout')
    expect(markup).toContain('logs/model_calls/call-failed_detector_codegen.json')
  })

  it('renders a clear empty state when no model_call events are available', () => {
    const markup = renderToStaticMarkup(
      <LlmDebugPanel cockpit={{ ...cockpit, llmDebugCalls: [] }} />,
    )

    expect(markup).toContain('暂无 LLM 调用事件')
    expect(markup).toContain('等待工作流上报 model_call_start 或 model_call。')
  })
})
