import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import SimulationViewport from './SimulationViewport'

describe('SimulationViewport', () => {
  it('uses Chinese-first workbench copy for visual simulation controls', () => {
    const markup = renderToStaticMarkup(<SimulationViewport payload={null} onRefresh={() => {}} />)

    expect(markup).toContain('等待可视化产物')
    expect(markup).toContain('参考网格')
    expect(markup).toContain('显示轨迹')
    expect(markup).toContain('刷新数据')
    expect(markup).toContain('几何 0')
    expect(markup).toContain('轨迹 0')
    expect(markup).toContain('能量沉积 0')
    expect(markup).toContain('仿真事件 100')
    expect(markup).toContain('运行模拟后生成几何、轨迹和能量沉积分布。')
  })
})
