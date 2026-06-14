import type { SimulationPresetSummary } from '../lib/simulationPresets'

type PresetTaskPreviewProps = {
  summary: SimulationPresetSummary
  fullPrompt: string
}

export default function PresetTaskPreview({ summary, fullPrompt }: PresetTaskPreviewProps) {
  return (
    <section className="preset-summary" aria-label="Agent 任务摘要">
      <div className="preset-summary-main">
        <span>Agent 将执行</span>
        <strong>{summary.title}</strong>
        <p>{summary.detail}</p>
      </div>
      <div className="preset-summary-rows">
        {summary.rows.map((row) => (
          <article key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </article>
        ))}
      </div>
      <div className="preset-summary-tags">
        <span>门禁</span>
        {summary.gates.map((gate) => (
          <strong key={gate}>{gate}</strong>
        ))}
        <span>产物</span>
        {summary.deliverables.map((deliverable) => (
          <strong key={deliverable}>{deliverable}</strong>
        ))}
      </div>
      <details className="preset-prompt-preview">
        <summary>
          完整任务描述
          <small>Prompt preview</small>
        </summary>
        <p>{fullPrompt}</p>
      </details>
    </section>
  )
}
