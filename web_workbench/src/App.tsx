import { ArrowRight, Boxes, CheckCircle2, ClipboardCheck, Play, TerminalSquare } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import HeroSphere from './components/HeroSphere'
import WorkflowMiniDemo from './components/WorkflowMiniDemo'
import WorkbenchShell from './components/WorkbenchShell'
import { fetchHomeSummary, type HomeSummary } from './lib/api'
import { createIntroLandingStyle } from './lib/homeIntroGeometry'
import {
  createHomeIntroState,
  getHomeIntroVisualState,
  reduceHomeIntro,
  type HomeIntroState,
} from './lib/homeIntro'
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
  const introAnchorRef = useRef<HTMLDivElement | null>(null)
  const ambientSphereRef = useRef<HTMLDivElement | null>(null)

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
    const targetBox = ambientSphereRef.current?.getBoundingClientRect()
    const sourceWidth = introAnchorRef.current?.offsetWidth || 0
    if (sourceWidth && targetBox) {
      const landing = createIntroLandingStyle(sourceWidth, targetBox)
      const shell = document.querySelector<HTMLElement>('.home-shell')
      if (shell) {
        Object.entries(landing).forEach(([key, value]) => {
          if (value) {
            shell.style.setProperty(key, value)
          }
        })
      }
    }
    setIntro((current) => reduceHomeIntro(current, { type }))
  }

  function finishIntroTransition() {
    setIntro((current) => reduceHomeIntro(current, { type: 'transitionEnd' }))
  }

  const introVisual = getHomeIntroVisualState(intro)

  return (
    <main
      className={`home-shell home-intro-${intro.stage} home-content-${introVisual.contentState}${
        introVisual.suppressAmbientSphere ? ' ambient-suppressed' : ''
      }${introVisual.shieldHomeSurface ? ' intro-surface-shielded' : ''
      }`}
    >
      {introVisual.showIntroOverlay ? (
        <button
          className="intro-sphere-stage"
          type="button"
          aria-label="进入 RadAgent 首页"
          onClick={() => collapseIntro('click')}
          onWheel={() => collapseIntro('wheel')}
          onTouchStart={() => collapseIntro('touch')}
          onAnimationEnd={(event) => {
            if (event.animationName === 'intro-shell-leave') {
              finishIntroTransition()
            }
          }}
        >
          <div className="intro-anchor" ref={introAnchorRef}>
            <HeroSphere variant="intro" />
            <span className="intro-title">
              <strong>Radagent</strong>
              <small>空天辐照防护仿真工作台</small>
            </span>
          </div>
          <span className="intro-hint">点击或滑动进入</span>
        </button>
      ) : null}
      <section className="home-hero">
        <div className="home-ambient-sphere" ref={ambientSphereRef}>
          <HeroSphere />
        </div>
        <div className="hero-copy">
          <div className="hero-promise">
            <span>空天辐照防护</span>
            <span>Geant4 仿真</span>
            <span>本地运行结果</span>
          </div>
          <div className="eyebrow">
            RadAgent 网页工作台
            <small>Web Workbench</small>
          </div>
          <h1>Radagent</h1>
          <p className="hero-product-line">空天辐照防护仿真工作台</p>
          <p className="hero-subtitle">基于 Geant4 物理算法的高可信 Agent 建模、构建与结果交付</p>
          <p>
            面向航天器屏蔽、器件辐照和空间粒子环境，把防护目标转成可运行的 Geant4 工程。
            通过物理模型证据链提升结果准确性；接入本地环境后，可以直接构建、模拟、产出剂量和屏蔽效果结果。
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
          <ul className="active-on" aria-label="RadAgent 支持的工作流能力">
            <li className="active-on-label">WORKS ON</li>
            {['Geant4', 'AP8/AE8', '屏蔽材料', '本地构建', '物理门禁', '结果报告'].map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="manifesto-section">
        <div className="manifesto-block">
          <div className="eyebrow">
            工具立意
            <small>Why RadAgent</small>
          </div>
          <h2>把辐照防护从手写脚本推进到可验证工程。</h2>
          <p>
            传统 Geant4 工作流依赖专家手动建模、手动补材料、手动查日志。RadAgent 把任务规划、
            模型证据、代码生成、本地运行、验证门禁和产物归档连成一条可审查链路。
          </p>
          <div className="home-metric-strip" aria-label="工作流指标 Workflow metrics">
            {home.metricTiles.map((tile) => (
              <div className="home-metric" key={tile.label}>
                <strong>{tile.value}</strong>
                <span>
                  {tile.label}
                  <small>{tile.labelEn}</small>
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="workflow-band" aria-labelledby="workflow-heading">
        <div className="workflow-intro">
          <div className="eyebrow">
            六个优势
            <small>Six advantages</small>
          </div>
          <h2 id="workflow-heading">相比传统仿真流程，优势在可运行、可验证、可复查。</h2>
        </div>
        <div className="advantage-showcase">
          {home.advantageItems.map((item) => (
            <article className="advantage-panel" key={item.index}>
              <div className="advantage-media">
                <WorkflowMiniDemo index={item.demoIndex} />
              </div>
              <div className="advantage-copy">
                <em>{item.index}</em>
                <h3>
                  <CheckCircle2 size={16} />
                  {item.title}
                </h3>
                <small>{item.titleEn}</small>
                <p>{item.body}</p>
                <span>{item.proof}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="project-section" id="showcase">
        <div className="project-intro">
          <div className="eyebrow">
            成功示例
            <small>Showcase</small>
          </div>
          <h2>从复杂一点的任务开始，直接交给 Agent 工作流验证。</h2>
        </div>
        <div className="project-grid">
          {home.showcaseCards.map((example, index) => {
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
                <span className="project-index">{String(index + 1).padStart(2, '0')}</span>
                <div className="project-card-topline">
                  <span>
                    <Boxes size={18} />
                    {example.difficulty}
                  </span>
                  <ArrowRight size={16} />
                </div>
                <h3>{example.title}</h3>
                <p>{example.subtitle}</p>
                <div className="project-proof">
                  <span>验证重点</span>
                  <strong>{example.validationFocus.slice(0, 2).join(' / ')}</strong>
                </div>
                <div className="project-deliverables" aria-label={`${example.title} 交付物`}>
                  {example.deliverables.slice(0, 3).map((item) => (
                    <span key={item}>
                      <ClipboardCheck size={13} />
                      {item}
                    </span>
                  ))}
                </div>
                <div className="project-tags" aria-label={`${example.title} 标签`}>
                  {example.tags.slice(0, 3).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
                <div className="project-launch">
                  启动示例
                  <Play size={14} />
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
