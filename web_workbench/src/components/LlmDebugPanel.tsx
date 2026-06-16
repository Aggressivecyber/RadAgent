import { Bot, Clock, FileJson, TerminalSquare } from 'lucide-react'
import type { LlmResponsePreview } from '../lib/llmTranscriptPreview'
import type { AgentCockpit } from '../lib/workbenchPresentation'

type LlmDebugPanelProps = {
  cockpit: AgentCockpit
  responsePreviews?: Record<string, LlmResponsePreview>
}

function ResponsePreview({ preview }: { preview?: LlmResponsePreview }) {
  if (!preview) {
    return null
  }
  return (
    <div className="llm-response-preview" aria-label="LLM 响应片段">
      <div className="llm-response-preview-heading">
        <strong>{preview.isLive ? '实时片段' : '最近响应'}</strong>
        <span>最新三行</span>
      </div>
      {preview.visibleLines.length > 0 ? (
        <pre className="llm-response-lines">{preview.visibleLines.join('\n')}</pre>
      ) : (
        <p className="llm-response-waiting">{preview.emptyLabel || '等待模型输出...'}</p>
      )}
      {preview.foldedText ? (
        <details className="llm-response-rest">
          <summary>展开较早响应</summary>
          <pre>{preview.foldedText}</pre>
        </details>
      ) : null}
    </div>
  )
}

export default function LlmDebugPanel({ cockpit, responsePreviews = {} }: LlmDebugPanelProps) {
  const calls = cockpit.llmDebugCalls.slice(0, 2)

  return (
    <section className="llm-debug-panel" id="llm-debug-panel" aria-label="LLM 实时 debug 面板">
      <div className="panel-title">
        <Bot size={18} />
        LLM 实时 debug
        <small>Model calls</small>
      </div>

      {calls.length > 0 ? (
        <div className="llm-debug-call-list">
          {calls.map((call) => (
            <article className={`llm-debug-call ${call.status}`} key={call.id}>
              <header>
                <div>
                  <span>{call.phaseLabel}</span>
                  <strong>{call.moduleLabel}</strong>
                </div>
                <small>{call.statusLabel}</small>
              </header>
              <div className="llm-debug-meta">
                <span>
                  <Bot size={13} />
                  {call.modelName}
                </span>
                <span>
                  <Clock size={13} />
                  {call.durationLabel}
                </span>
              </div>
              <dl>
                <div>
                  <dt>Prompt</dt>
                  <dd>
                    <strong>{call.promptCharsLabel}</strong>
                    <span>{call.promptSummary}</span>
                  </dd>
                </div>
                <div>
                  <dt>Output</dt>
                  <dd>
                    {call.outputCharsLabel ? <strong>{call.outputCharsLabel}</strong> : null}
                    <span>{call.outputSummary}</span>
                  </dd>
                </div>
              </dl>
              <ResponsePreview preview={responsePreviews[call.id]} />
              <p className="llm-debug-artifact" title={call.artifactPath}>
                <FileJson size={13} />
                <span>{call.artifactPath}</span>
              </p>
            </article>
          ))}
        </div>
      ) : (
        <div className="llm-debug-empty">
          <TerminalSquare size={17} />
          {cockpit.runtimeActive ? (
            <>
              <strong>等待模型响应片段</strong>
              <p>工作流运行时会在这里显示最近三行响应。</p>
            </>
          ) : (
            <>
              <strong>后台未运行</strong>
              <p>当前作业可继续；恢复后会在这里显示最近三行模型响应。</p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
