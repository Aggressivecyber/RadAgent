import type { ArtifactContent } from './api'

export type LlmResponsePreview = {
  visibleLines: string[]
  foldedText: string
  emptyLabel: string
  isLive: boolean
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function textValue(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }
  if (value == null) {
    return ''
  }
  return String(value)
}

function listValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function transcriptFromArtifact(artifact: ArtifactContent): Record<string, unknown> {
  if (artifact.json_data && typeof artifact.json_data === 'object') {
    return artifact.json_data as Record<string, unknown>
  }
  if (!artifact.text.trim()) {
    return {}
  }
  try {
    const parsed = JSON.parse(artifact.text)
    return record(parsed)
  } catch {
    return {}
  }
}

function responseText(transcript: Record<string, unknown>): string {
  const progress = record(transcript.progress)
  const progressContent = textValue(progress.content)
  if (progressContent) {
    return progressContent
  }
  const result = record(transcript.result)
  const content = textValue(result.content)
  if (content) {
    return content
  }
  const fallbackLines = []
  const reasoning = textValue(result.reasoning_content)
  if (reasoning) {
    fallbackLines.push(reasoning)
  }
  const toolNames = listValue(result.tool_calls)
    .map((toolCall) => textValue(record(toolCall).name).trim())
    .filter(Boolean)
  if (toolNames.length > 0) {
    fallbackLines.push(`准备调用工具 ${toolNames.join(', ')}`)
  }
  return fallbackLines.join('\n')
}

function responseLines(content: string): string[] {
  return content
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trimEnd())
    .filter((line) => line.trim())
}

export function createLlmResponsePreview(artifact: ArtifactContent): LlmResponsePreview {
  const transcript = transcriptFromArtifact(artifact)
  const status = textValue(transcript.status).toLowerCase()
  const content = responseText(transcript)
  const lines = responseLines(content)
  const visibleLines = lines.slice(-3)
  const foldedLines = lines.slice(0, Math.max(0, lines.length - visibleLines.length))
  const isLive = status === 'running'
  return {
    visibleLines,
    foldedText: foldedLines.join('\n'),
    emptyLabel: lines.length === 0 && isLive ? '模型正在生成响应...' : '',
    isLive,
  }
}
