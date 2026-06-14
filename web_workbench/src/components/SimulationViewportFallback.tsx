export default function SimulationViewportFallback() {
  return (
    <section className="simulation-viewport simulation-viewport-fallback" aria-label="3D 模型视图加载中">
      <div className="simulation-viewport-top">
        <div>
          <strong>加载 3D 可视化</strong>
          <span>Geant4 geometry preview</span>
        </div>
        <button type="button" disabled>
          显示轨迹
        </button>
      </div>
      <div className="simulation-viewport-empty">
        <strong>正在准备可视化渲染器</strong>
        <span>仿真几何、轨迹和能量沉积分布会在渲染模块加载后显示。</span>
      </div>
      <div className="simulation-viewport-stats">
        <span>几何 0</span>
        <span>轨迹 0</span>
        <span>能量沉积 0</span>
      </div>
    </section>
  )
}
