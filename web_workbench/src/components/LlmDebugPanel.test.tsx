import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import LlmDebugPanel from './LlmDebugPanel'
import type { AgentCockpit } from '../lib/workbenchPresentation'
import type { LlmResponsePreview } from '../lib/llmTranscriptPreview'

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
  runtimeActive: true,
}

describe('LlmDebugPanel', () => {
  it('renders current and recent LLM call fields for live debugging', () => {
    const markup = renderToStaticMarkup(<LlmDebugPanel cockpit={cockpit} responsePreviews={{}} />)

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

  it('renders recent response lines and folds older response text', () => {
    const responsePreviews: Record<string, LlmResponsePreview> = {
      'call-running': {
        visibleLines: ['third visible line', 'fourth visible line', 'fifth visible line'],
        foldedText: 'first hidden line\nsecond hidden line',
        emptyLabel: '',
        isLive: true,
      },
    }

    const markup = renderToStaticMarkup(
      <LlmDebugPanel cockpit={cockpit} responsePreviews={responsePreviews} />,
    )

    expect(markup).toContain('third visible line')
    expect(markup).toContain('fourth visible line')
    expect(markup).toContain('fifth visible line')
    expect(markup).toContain('展开较早响应')
    expect(markup).toContain('first hidden line')
    expect(markup).toContain('second hidden line')
    expect(markup).toContain('实时片段')
  })

  it('renders only the two most recent LLM call cards', () => {
    const olderCall = {
      ...cockpit.llmDebugCalls[1],
      id: 'call-older',
      moduleLabel: 'Older Hidden Module',
      artifactPath: 'logs/model_calls/call-older_hidden.json',
      createdAt: '2026-06-14T08:00:00Z',
    }

    const markup = renderToStaticMarkup(
      <LlmDebugPanel
        cockpit={{ ...cockpit, llmDebugCalls: [...cockpit.llmDebugCalls, olderCall] }}
        responsePreviews={{}}
      />,
    )

    expect(markup).toContain('Coordinate Core Modules Context')
    expect(markup).toContain('Detector Construction')
    expect(markup).not.toContain('Older Hidden Module')
    expect(markup).not.toContain('logs/model_calls/call-older_hidden.json')
  })

  it('renders a waiting-for-stream state when no model_call events are available', () => {
    const markup = renderToStaticMarkup(
      <LlmDebugPanel cockpit={{ ...cockpit, llmDebugCalls: [] }} responsePreviews={{}} />,
    )

    expect(markup).toContain('等待模型响应片段')
    expect(markup).toContain('工作流运行时会在这里显示最近三行响应。')
  })

  it('renders a resumable state when the job is not actively running', () => {
    const markup = renderToStaticMarkup(
      <LlmDebugPanel
        cockpit={{ ...cockpit, llmDebugCalls: [], runtimeActive: false }}
        responsePreviews={{}}
      />,
    )

    expect(markup).toContain('后台未运行')
    expect(markup).toContain('当前作业可继续；恢复后会在这里显示最近三行模型响应。')
    expect(markup).not.toContain('工作流运行时会在这里显示最近三行响应。')
  })
})
