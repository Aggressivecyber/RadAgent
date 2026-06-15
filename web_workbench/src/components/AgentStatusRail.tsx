import { FormEvent, useState } from 'react'
import { Home, Send, Sparkles } from 'lucide-react'
import type { SubmissionFeedback } from '../lib/submissionFeedback'
import type { AgentCockpit } from '../lib/workbenchPresentation'
import type { TimelineRow } from '../lib/workbenchState'

export type AgentQuickAction = {
  label: string
  labelEn: string
  active: boolean
  onSelect: () => void
}

type AgentStatusRailProps = {
  cockpit: AgentCockpit
  timeline: TimelineRow[]
  submissionFeedback?: SubmissionFeedback
  copilotDisabled?: boolean
  onAskCopilot?: (message: string) => void
  onHome: () => void
}

export default function AgentStatusRail({
  cockpit,
  timeline,
  submissionFeedback,
  copilotDisabled = false,
  onAskCopilot,
  onHome,
}: AgentStatusRailProps) {
  const [copilotText, setCopilotText] = useState('')

  function submitCopilotQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const question = copilotText.trim()
    if (!question || copilotDisabled || !onAskCopilot) {
      return
    }
    onAskCopilot(question)
    setCopilotText('')
  }

  const historyRows = timeline.filter((row) => row.kind === 'command' && row.meta === 'chat').slice(-18)

  return (
    <aside className="agent-status-rail">
      <header className="copilot-rail-header">
        <button className="agent-home-button" type="button" onClick={onHome} aria-label="返回首页">
          <Home size={17} />
        </button>
        <div>
          <div className="agent-briefing-kicker">
            <Sparkles size={15} />
            <span>Copilot</span>
          </div>
          <strong>RadAgent Copilot</strong>
          <p>仿真协作助手</p>
        </div>
      </header>

      {submissionFeedback ? (
        <section className={`agent-workflow-status ${submissionFeedback.tone}`} aria-live="polite">
          <span>仿真工作流</span>
          <strong>{submissionFeedback.title}</strong>
          <p>{submissionFeedback.detail}</p>
        </section>
      ) : null}

      <section className="copilot-history-window" aria-label="Copilot conversation history">
        <div className="agent-section-title">
          <span>对话历史</span>
          <small>History</small>
        </div>
        {historyRows.length > 0 ? (
          historyRows.map((row) => (
            <article className={`copilot-history-message ${row.status}`} key={row.id}>
              <span>Copilot</span>
              <strong>{row.title}</strong>
              {row.body ? <p>{row.body}</p> : null}
            </article>
          ))
        ) : (
          <p className="copilot-empty-state">暂无 Copilot 对话。输入问题后，历史会固定保留在这里。</p>
        )}
      </section>

      {onAskCopilot ? (
        <form className="agent-copilot-card" onSubmit={submitCopilotQuestion}>
          <label>
            <span>询问 Copilot</span>
            <input
              value={copilotText}
              onChange={(event) => setCopilotText(event.target.value)}
              placeholder="询问当前工作流、产物或下一步"
            />
          </label>
          <button type="submit" disabled={copilotDisabled || !copilotText.trim()}>
            <Send size={14} />
            问 Copilot
          </button>
        </form>
      ) : null}
    </aside>
  )
}
