import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyles() {
  return readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
}

function readSimulationViewport() {
  return readFileSync(resolve(process.cwd(), 'src/components/SimulationViewport.tsx'), 'utf8')
}

describe('workbench cockpit styling', () => {
  it('uses the promotional visual system for the agent cockpit shell', () => {
    const css = readStyles()
    const simulationViewport = readSimulationViewport()

    expect(css).toMatch(/\.workbench-shell\s*{[^}]*grid-template-columns:\s*minmax\(250px,\s*0\.8fr\)\s*minmax\(0,\s*1\.75fr\)\s*minmax\(330px,\s*0\.95fr\);/s)
    expect(css).toMatch(/\.workbench-shell\s*{[^}]*background:[^}]*radial-gradient/s)
    expect(css).toMatch(/\.agent-status-rail\s*{[^}]*background:[^}]*rgba\(255,\s*255,\s*255,\s*0\.72\)/s)
    expect(css).toMatch(/\.agent-briefing strong\s*{[^}]*font-family:\s*var\(--radagent-promo-font\);/s)
    expect(css).toMatch(/\.artifact-workspace\s*{[^}]*background:\s*rgba\(255,\s*255,\s*255,\s*0\.78\);/s)
    expect(css).toMatch(/\.artifact-file-list button\.selected\s*{[^}]*border-color:\s*rgba\(185,\s*65,\s*56,\s*0\.42\);/s)
    expect(css).toMatch(/\.simulation-viewport\s*{[^}]*background:[^}]*rgba\(255,\s*255,\s*255,\s*0\.66\)/s)
    expect(css).not.toMatch(/\.simulation-viewport\s*{[^}]*background:\s*#11151a/s)
    expect(simulationViewport).toContain('preserveDrawingBuffer: true')
    expect(css).toMatch(/\.status-pill\s*{[^}]*max-width:\s*min\(100%,\s*360px\);/s)
    expect(css).toMatch(/\.status-pill\s*{[^}]*overflow-wrap:\s*anywhere;/s)
    expect(css).toMatch(/\.workflow-console\s*{[^}]*min-width:\s*0;/s)
    expect(css).toMatch(/\.workflow-console\s*{[^}]*overflow:\s*hidden;/s)
    expect(css).toMatch(/\.preset-summary\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.1fr\)\s*minmax\(0,\s*0\.72fr\)\s*minmax\(0,\s*0\.9fr\)\s*minmax\(0,\s*0\.58fr\);/s)
  })
})
