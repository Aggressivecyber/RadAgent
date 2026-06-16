import { describe, expect, it } from 'vitest'
import { createLlmResponsePreview } from './llmTranscriptPreview'
import type { ArtifactContent } from './api'

function artifact(jsonData: unknown): ArtifactContent {
  return {
    path: 'logs/model_calls/call-a_codegen.json',
    exists: true,
    kind: 'json',
    text: '',
    json_data: jsonData,
    size_bytes: 100,
    truncated: false,
    errors: [],
  }
}

describe('createLlmResponsePreview', () => {
  it('shows the latest three response lines and folds earlier lines', () => {
    const preview = createLlmResponsePreview(
      artifact({
        status: 'running',
        progress: {
          content: ['line one', 'line two', 'line three', 'line four', 'line five'].join('\n'),
        },
      }),
    )

    expect(preview.visibleLines).toEqual(['line three', 'line four', 'line five'])
    expect(preview.foldedText).toBe('line one\nline two')
    expect(preview.isLive).toBe(true)
    expect(preview.emptyLabel).toBe('')
  })

  it('falls back to final result content when progress is not available', () => {
    const preview = createLlmResponsePreview(
      artifact({
        status: 'passed',
        result: {
          content: 'final one\nfinal two\nfinal three\nfinal four',
        },
      }),
    )

    expect(preview.visibleLines).toEqual(['final two', 'final three', 'final four'])
    expect(preview.foldedText).toBe('final one')
    expect(preview.isLive).toBe(false)
  })

  it('shows tool-call activity when final assistant content is empty', () => {
    const preview = createLlmResponsePreview(
      artifact({
        status: 'passed',
        progress: {
          content: '准备调用工具 build_project{}',
          chunk_count: 2,
        },
        result: {
          content: '',
          reasoning_content: 'Now let me rebuild and run smoke.',
          tool_calls: [{ id: 'call_1', name: 'build_project', arguments: '{}' }],
          finish_reason: 'tool_calls',
        },
      }),
    )

    expect(preview.visibleLines).toEqual(['准备调用工具 build_project{}'])
    expect(preview.foldedText).toBe('')
    expect(preview.emptyLabel).toBe('')
  })

  it('falls back to reasoning and tool call names when progress is missing', () => {
    const preview = createLlmResponsePreview(
      artifact({
        status: 'passed',
        result: {
          content: '',
          reasoning_content: 'Now let me rebuild and run smoke.',
          tool_calls: [
            { id: 'call_1', name: 'build_project', arguments: '{}' },
            { id: 'call_2', name: 'run_smoke', arguments: '{"events":1000}' },
          ],
          finish_reason: 'tool_calls',
        },
      }),
    )

    expect(preview.visibleLines).toEqual([
      'Now let me rebuild and run smoke.',
      '准备调用工具 build_project, run_smoke',
    ])
    expect(preview.emptyLabel).toBe('')
  })

  it('returns a running placeholder when a call has started but no text has arrived', () => {
    const preview = createLlmResponsePreview(
      artifact({
        status: 'running',
        progress: { content: '' },
      }),
    )

    expect(preview.visibleLines).toEqual([])
    expect(preview.foldedText).toBe('')
    expect(preview.isLive).toBe(true)
    expect(preview.emptyLabel).toBe('模型正在生成响应...')
  })
})
