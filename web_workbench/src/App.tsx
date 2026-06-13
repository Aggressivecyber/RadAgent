import { ArrowRight, Boxes, CheckCircle2, TerminalSquare } from 'lucide-react'
import { useEffect, useState } from 'react'
import HeroSphere from './components/HeroSphere'
import WorkbenchShell from './components/WorkbenchShell'
import { fetchHomeSummary, type HomeSummary } from './lib/api'
import { createHomeIntroState, reduceHomeIntro, type HomeIntroState } from './lib/homeIntro'
import { createShowcaseLaunchTarget, type HomeLaunchTarget } from './lib/homeNavigation'
import { normalizeHomeSummary, type NormalizedHomeSummary } from './lib/homeSummary'

type ViewMode = 'home' | 'workbench'

const emptyHomeSummary: HomeSummary = {
  metrics: {
    projects: 0,
    jobs: 0,
    completed_jobs: 0,
    active_jobs: 0,
    artifacts: 0,
  },
  workflow_capabilities: [],
  projects: [],
  showcase_examples: [],
}

function HomeView({
  onEnter,
  onLaunchExample,
}: {
  onEnter: () => void
  onLaunchExample: (target: HomeLaunchTarget) => void
}) {
  const [home, setHome] = useState<NormalizedHomeSummary>(() =>
    normalizeHomeSummary(emptyHomeSummary),
  )
  const [intro, setIntro] = useState<HomeIntroState>(() => ({ stage: 'collapsed' }))

  useEffect(() => {
    let active = true

    fetchHomeSummary()
      .then((summary) => {
        if (active) {
          setHome(normalizeHomeSummary(summary))
        }
      })
      .catch(() => {
        if (active) {
          setHome(normalizeHomeSummary(emptyHomeSummary))
        }
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    setIntro(createHomeIntroState({ reducedMotion }))
  }, [])

  function collapseIntro(type: 'click' | 'wheel' | 'touch') {
    setIntro((current) => reduceHomeIntro(current, { type }))
  }

  return (
    <main className={`home-shell home-intro-${intro.stage}`}>
      {intro.stage === 'expanded' ? (
        <button
          className="intro-sphere-stage"
          type="button"
          aria-label="进入 RadAgent 首页"
          onClick={() => collapseIntro('click')}
          onWheel={() => collapseIntro('wheel')}
          onTouchStart={() => collapseIntro('touch')}
        >
          <HeroSphere variant="intro" />
          <span className="intro-hint">
            <strong>RadAgent 工作流</strong>
            <small>Click or scroll to enter Home</small>
          </span>
        </button>
      ) : null}
      <section className="home-hero">
        <div className="hero-copy">
          <div className="eyebrow">RadAgent 网页工作台 / Web Workbench</div>
          <h1>从仿真需求到可信产物的工作流控制台。</h1>
          <p>
            面向 RadAgent 的网页客户端，保留 TUI 级工作流能力：事件时间线、作业、门禁、模型设置、
            构建、模拟、产物和修订。English auxiliary labels stay available for scanning.
          </p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={onEnter}>
              <TerminalSquare size={18} />
              打开工作台
              <small>Workbench</small>
            </button>
            <a className="secondary-link" href="#showcase">
              查看成功示例
              <ArrowRight size={16} />
            </a>
          </div>
          <div className="home-metric-strip" aria-label="工作流指标 Workflow metrics">
            {home.metricTiles.map((tile) => (
              <div className="home-metric" key={tile.label}>
                <strong>{tile.value}</strong>
                <span>{tile.label}</span>
              </div>
            ))}
          </div>
        </div>
        <HeroSphere />
      </section>

      <section className="workflow-band">
        {home.workflowCapabilities.map((capability) => (
          <article className="workflow-step" key={capability.name} title={capability.description}>
            <CheckCircle2 size={18} />
            <span>
              <strong>{capability.name}</strong>
              <small>{capability.command}</small>
            </span>
          </article>
        ))}
      </section>

      <section className="project-section" id="showcase">
        <div>
          <div className="eyebrow">成功示例 / Showcase</div>
          <h2>从复杂一点的任务开始，直接交给 Agent 工作流验证。</h2>
        </div>
        <div className="project-grid">
          {home.showcaseCards.map((example) => {
            const target = createShowcaseLaunchTarget(example)
            return (
              <button
                className="project-card"
                key={example.id}
                type="button"
                disabled={!target}
                onClick={() => {
                  if (target) {
                    onLaunchExample(target)
                  }
                }}
              >
                <Boxes size={20} />
                <h3>{example.title}</h3>
                <p>{example.subtitle}</p>
                <div className="project-tags">
                  {[example.difficulty, ...example.tags].slice(0, 4).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </button>
            )
          })}
        </div>
      </section>
    </main>
  )
}

export default function App() {
  const [view, setView] = useState<ViewMode>('home')
  const [launchTarget, setLaunchTarget] = useState<HomeLaunchTarget | null>(null)

  function openWorkbench(target: HomeLaunchTarget | null = null) {
    setLaunchTarget(target)
    setView('workbench')
  }

  return view === 'home' ? (
    <HomeView
      onEnter={() => openWorkbench(null)}
      onLaunchExample={(target) => openWorkbench(target)}
    />
  ) : (
    <WorkbenchShell launchTarget={launchTarget} onHome={() => setView('home')} />
  )
}
