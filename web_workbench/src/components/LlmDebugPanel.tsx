import { Bot, Clock, FileJson, TerminalSquare } from 'lucide-react'
import type { AgentCockpit } from '../lib/workbenchPresentation'

type LlmDebugPanelProps = {
  cockpit: AgentCockpit
}

export default function LlmDebugPanel({ cockpit }: LlmDebugPanelProps) {
  const calls = cockpit.llmDebugCalls

  return (
    <section className="llm-debug-panel" aria-label="LLM 实时 debug 面板">
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
          <strong>暂无 LLM 调用事件</strong>
          <p>等待工作流上报 model_call_start 或 model_call。</p>
        </div>
      )}
    </section>
  )
}
