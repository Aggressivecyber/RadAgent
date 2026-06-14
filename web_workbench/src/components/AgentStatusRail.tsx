import { Activity, CircleDot, Home, Sparkles } from 'lucide-react'
import type { AgentCockpit } from '../lib/workbenchPresentation'

export type AgentQuickAction = {
  label: string
  labelEn: string
  active: boolean
  onSelect: () => void
}

type AgentStatusRailProps = {
  cockpit: AgentCockpit
  quickActions: AgentQuickAction[]
  onHome: () => void
}

export default function AgentStatusRail({
  cockpit,
  quickActions,
  onHome,
}: AgentStatusRailProps) {
  return (
    <aside className="agent-status-rail">
      <button className="agent-home-button" type="button" onClick={onHome} aria-label="返回首页">
        <Home size={17} />
      </button>

      <section className="agent-briefing">
        <div className="agent-briefing-kicker">
          <Sparkles size={15} />
          <span>Agent Cockpit</span>
        </div>
        <strong>{cockpit.agent.stateLabel}</strong>
        <p>{cockpit.agent.phaseLabel}</p>
      </section>

      <section className="agent-focus-card">
        <span>当前动作</span>
        <strong>{cockpit.agent.currentAction}</strong>
      </section>

      <div className="agent-rail-metrics" aria-label="Agent workspace metrics">
        <article>
          <span>文件变更</span>
          <strong>{cockpit.agent.changedFiles}</strong>
        </article>
        <article>
          <span>工作区</span>
          <strong>{cockpit.agent.workspace}</strong>
        </article>
      </div>

      <nav className="agent-quick-actions" aria-label="Agent quick actions">
        {quickActions.map((action) => (
          <button
            className={action.active ? 'active' : ''}
            type="button"
            key={`${action.label}-${action.labelEn}`}
            onClick={action.onSelect}
          >
            <Activity size={15} />
            <span>
              <strong>{action.label}</strong>
              <small>{action.labelEn}</small>
            </span>
          </button>
        ))}
      </nav>

      <section className="agent-activity-list">
        <div className="agent-section-title">
          <span>最近活动</span>
          <small>Activity</small>
        </div>
        {cockpit.recentActivity.length > 0 ? (
          cockpit.recentActivity.map((item, index) => (
            <article key={`${item.title}-${item.phaseLabel}-${index}`}>
              <CircleDot size={13} />
              <div>
                <strong>{item.title}</strong>
                <span>
                  {item.statusLabel} · {item.phaseLabel}
                </span>
              </div>
            </article>
          ))
        ) : (
          <p>等待 Agent 运行记录。</p>
        )}
      </section>
    </aside>
  )
}
