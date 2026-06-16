type WorkflowMiniDemoProps = {
  index: string
}

const labels: Record<string, string> = {
  '01': '空天辐照防护任务拆解',
  '02': 'Geant4 模型证据链',
  '03': '空间辐射源与屏蔽材料检查',
  '04': '本地 Geant4 构建运行',
  '05': '验证门禁与结果产物',
  '06': '可复查产物与人工确认',
}

export default function WorkflowMiniDemo({ index }: WorkflowMiniDemoProps) {
  const label = labels[index] ?? 'RadAgent 工作流阶段演示'

  return (
    <div className={`mini-demo mini-demo-${index}`} aria-label={label} role="img">
      <svg
        className="mini-scene"
        viewBox="0 0 520 320"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id={`sceneGlow-${index}`} cx="50%" cy="45%" r="68%">
            <stop offset="0%" stopColor="#fffdf8" />
            <stop offset="58%" stopColor="#f8f4ed" />
            <stop offset="100%" stopColor="#efe8dc" />
          </radialGradient>
          <linearGradient id={`accentBeam-${index}`} x1="0%" x2="100%" y1="0%" y2="0%">
            <stop offset="0%" stopColor="#b94138" stopOpacity="0" />
            <stop offset="44%" stopColor="#b94138" stopOpacity="0.86" />
            <stop offset="100%" stopColor="#23785a" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={`greenFill-${index}`} x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#d8ece4" />
            <stop offset="100%" stopColor="#6ca88f" />
          </linearGradient>
          <filter id={`softShadow-${index}`} x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="14" floodColor="#282218" floodOpacity="0.12" stdDeviation="18" />
          </filter>
        </defs>
        <rect width="520" height="320" rx="28" fill={`url(#sceneGlow-${index})`} />
        <g className="scene-grid" opacity="0.26">
          {Array.from({ length: 9 }, (_, column) => (
            <path key={`v-${column}`} d={`M ${50 + column * 52} 34 V 286`} />
          ))}
          {Array.from({ length: 5 }, (_, row) => (
            <path key={`h-${row}`} d={`M 42 ${64 + row * 44} H 478`} />
          ))}
        </g>
        {renderScene(index)}
      </svg>
    </div>
  )
}

function renderScene(index: string) {
  switch (index) {
    case '01':
      return <SpacecraftShieldingScene />
    case '02':
      return <Geant4ModelScene />
    case '03':
      return <RadiationBeltScene />
    case '04':
      return <LocalRunScene />
    case '05':
      return <ValidationGateScene />
    case '06':
      return <ArtifactReportScene />
    default:
      return <SpacecraftShieldingScene />
  }
}

function SpacecraftShieldingScene() {
  return (
    <g className="scene-spacecraft-shielding">
      <g className="particle-stream">
        <path className="particle-beam beam-a" d="M 24 96 C 112 96 166 112 230 136" />
        <path className="particle-beam beam-b" d="M 28 164 C 118 154 170 158 228 164" />
        <path className="particle-beam beam-c" d="M 26 226 C 110 214 168 204 230 184" />
        <circle className="particle particle-a" cx="62" cy="96" r="5" />
        <circle className="particle particle-b" cx="82" cy="164" r="4" />
        <circle className="particle particle-c" cx="66" cy="226" r="4" />
      </g>
      <g className="shield-stack" filter="url(#softShadow-01)">
        <rect className="shield-layer layer-a" x="230" y="76" width="26" height="168" rx="8" />
        <rect className="shield-layer layer-b" x="264" y="66" width="34" height="188" rx="9" />
        <rect className="shield-layer layer-c" x="306" y="84" width="24" height="152" rx="8" />
      </g>
      <g className="spacecraft-body" filter="url(#softShadow-01)">
        <path d="M 356 120 L 432 96 L 474 160 L 432 224 L 356 200 Z" />
        <path className="spacecraft-core" d="M 374 136 H 426 L 448 160 L 426 184 H 374 L 392 160 Z" />
        <path className="solar-wing wing-left" d="M 344 142 L 304 128 L 286 192 L 344 178 Z" />
        <path className="solar-wing wing-right" d="M 444 112 L 494 88 L 504 146 L 464 154 Z" />
      </g>
      <path className="dose-readout" d="M 384 254 H 468" />
      <text className="scene-label" x="58" y="48">Shielding dose</text>
    </g>
  )
}

function Geant4ModelScene() {
  return (
    <g className="scene-geant4-model">
      <g className="world-volume" filter="url(#softShadow-02)">
        <path d="M 134 86 L 318 52 L 410 112 L 226 150 Z" />
        <path d="M 134 86 V 204 L 226 268 V 150 Z" />
        <path d="M 226 150 L 410 112 V 226 L 226 268 Z" />
      </g>
      <g className="detector-volume">
        <path d="M 226 126 L 304 112 L 344 138 L 266 154 Z" />
        <path d="M 226 126 V 190 L 266 218 V 154 Z" />
        <path d="M 266 154 L 344 138 V 200 L 266 218 Z" />
      </g>
      <g className="model-ir-lines">
        <path className="ir-line line-a" d="M 58 84 H 146" />
        <path className="ir-line line-b" d="M 58 112 H 124" />
        <path className="ir-line line-c" d="M 58 140 H 158" />
        <path className="ir-line line-d" d="M 364 248 H 462" />
      </g>
      <g className="evidence-nodes">
        <circle cx="188" cy="88" r="7" />
        <circle cx="318" cy="114" r="7" />
        <circle cx="266" cy="218" r="7" />
      </g>
      <path className="schema-scan" d="M 170 58 V 252" />
      <text className="scene-label" x="58" y="48">Geant4 Model IR</text>
    </g>
  )
}

function RadiationBeltScene() {
  return (
    <g className="scene-radiation-belt">
      <g className="earth-orbit">
        <circle className="earth" cx="260" cy="166" r="52" />
        <path className="continent continent-a" d="M 246 132 C 270 126 288 140 282 158 C 266 154 248 158 240 148 Z" />
        <path className="continent continent-b" d="M 272 180 C 292 184 298 202 282 212 C 264 208 256 196 262 184 Z" />
        <ellipse className="belt belt-inner" cx="260" cy="166" rx="128" ry="72" />
        <ellipse className="belt belt-outer" cx="260" cy="166" rx="188" ry="108" />
        <path className="orbit-track" d="M 98 166 C 160 90 362 90 424 166 C 362 242 160 242 98 166 Z" />
        <circle className="satellite-dot" cx="400" cy="130" r="6" />
      </g>
      <g className="ap8ae8-panel" filter="url(#softShadow-03)">
        <rect x="46" y="226" width="126" height="48" rx="12" />
        <path d="M 64 244 H 116" />
        <path d="M 64 258 H 146" />
        <text x="64" y="238">AP8 / AE8</text>
      </g>
      <g className="radiation-samples">
        <circle className="sample sample-a" cx="142" cy="110" r="4" />
        <circle className="sample sample-b" cx="384" cy="212" r="4" />
        <circle className="sample sample-c" cx="404" cy="96" r="3" />
      </g>
      <text className="scene-label" x="58" y="48">Trapped radiation source</text>
    </g>
  )
}

function LocalRunScene() {
  return (
    <g className="scene-local-run">
      <g className="terminal-window" filter="url(#softShadow-04)">
        <rect x="54" y="58" width="312" height="210" rx="18" />
        <path className="terminal-bar" d="M 54 96 H 366" />
        <circle cx="78" cy="78" r="6" />
        <circle cx="98" cy="78" r="6" />
        <circle cx="118" cy="78" r="6" />
        <path className="terminal-line line-a" d="M 82 126 H 236" />
        <path className="terminal-line line-b" d="M 82 156 H 288" />
        <path className="terminal-line line-c" d="M 82 186 H 210" />
        <path className="terminal-line line-d" d="M 82 216 H 272" />
        <path className="build-progress" d="M 82 246 H 320" />
      </g>
      <g className="local-run-output">
        <path className="output-link" d="M 366 156 C 404 156 420 184 444 206" />
        <rect x="418" y="196" width="58" height="54" rx="12" />
        <path d="M 432 214 H 462" />
        <path d="M 432 230 H 452" />
      </g>
      <circle className="run-cursor" cx="82" cy="126" r="5" />
      <text className="scene-label" x="58" y="48">Local Geant4 build/run</text>
    </g>
  )
}

function ValidationGateScene() {
  return (
    <g className="scene-validation-gates">
      <g className="gate-stack" filter="url(#softShadow-05)">
        {[0, 1, 2, 3].map((row) => (
          <g className={`gate-row gate-row-${row + 1}`} key={row}>
            <rect x="96" y={78 + row * 48} width="328" height="34" rx="12" />
            <path d={`M 126 ${95 + row * 48} H ${254 + row * 24}`} />
            <circle cx="394" cy={95 + row * 48} r="9" />
            <path d={`M 389 ${94 + row * 48} l4 5 l8 -11`} />
          </g>
        ))}
      </g>
      <path className="gate-scan" d="M 78 62 V 272" />
      <g className="physics-badge">
        <circle cx="76" cy="256" r="24" />
        <path d="M 64 256 H 88" />
        <path d="M 76 244 V 268" />
      </g>
      <text className="scene-label" x="58" y="48">Physics validation gates</text>
    </g>
  )
}

function ArtifactReportScene() {
  return (
    <g className="scene-artifact-report">
      <g className="report-sheet" filter="url(#softShadow-06)">
        <path d="M 114 58 H 330 L 386 114 V 270 H 114 Z" />
        <path className="report-fold" d="M 330 58 V 114 H 386" />
        <path className="report-line line-a" d="M 148 132 H 298" />
        <path className="report-line line-b" d="M 148 160 H 342" />
        <path className="report-line line-c" d="M 148 188 H 274" />
        <path className="spectrum-line" d="M 150 232 C 174 226 184 204 206 210 C 228 218 232 174 252 178 C 272 184 284 222 316 214" />
      </g>
      <g className="artifact-chips">
        <rect x="338" y="142" width="92" height="34" rx="17" />
        <rect x="346" y="188" width="78" height="34" rx="17" />
        <path d="M 358 159 H 412" />
        <path d="M 366 205 H 404" />
      </g>
      <circle className="archive-pulse" cx="352" cy="232" r="20" />
      <text className="scene-label" x="58" y="48">Reports, CSV, logs</text>
    </g>
  )
}
