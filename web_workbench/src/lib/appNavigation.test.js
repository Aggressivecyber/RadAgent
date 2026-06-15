import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readApp() {
  return readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8')
}

describe('app navigation viewport behavior', () => {
  it('resets scroll position when switching between home and workbench', () => {
    const app = readApp()

    expect(app).toContain('function resetViewportScroll')
    expect(app).toContain('window.scrollTo({ top: 0, left: 0')
    expect(app).toMatch(/function openWorkbench[\s\S]*resetViewportScroll\(\)/)
    expect(app).toMatch(/function openHome[\s\S]*resetViewportScroll\(\)/)
  })
})
