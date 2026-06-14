import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyles() {
  return readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
}

function readApp() {
  return readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8')
}

describe('home typography', () => {
  it('uses the promotional serif font for home English typography without leaking into the workbench', () => {
    const css = readStyles()

    expect(css).toContain('--radagent-font:')
    expect(css).toContain('--radagent-promo-font: Georgia, "Times New Roman", serif;')
    expect(css).toContain(
      '--radagent-code-font: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;',
    )
    expect(css).toMatch(/\.home-shell\s*{[^}]*font-family:\s*var\(--radagent-promo-font\);/s)
    expect(css).toMatch(/\.workbench-shell\s*{[^}]*font-family:\s*var\(--radagent-font\);/s)

    const homeDisplaySelectors = [
      '.hero-copy h1',
      '.manifesto-block h2',
      '.workflow-intro h2',
      '.project-intro h2',
      '.project-index',
    ]

    for (const selector of homeDisplaySelectors) {
      const escapedSelector = selector.replaceAll('.', '\\.')
      expect(css).toMatch(
        new RegExp(`${escapedSelector}\\s*\\{[^}]*font-family:\\s*var\\(--radagent-promo-font\\);`, 's'),
      )
    }

    const codeSelectors = [
      '.timeline-details pre',
      '.json-preview',
      '.artifact-preview',
    ]

    for (const selector of codeSelectors) {
      const escapedSelector = selector.replaceAll('.', '\\.')
      expect(css).toMatch(
        new RegExp(`${escapedSelector}\\s*\\{[^}]*font-family:\\s*var\\(--radagent-code-font\\);`, 's'),
      )
    }
  })

  it('styles the Showcase section header as a large centered module intro', () => {
    const css = readStyles()
    const app = readApp()

    expect(app).toContain('className="project-intro"')
    expect(css).toMatch(/\.project-section\s*{[^}]*grid-template-columns:\s*1fr;/s)
    expect(css).toMatch(/\.project-intro\s*{[^}]*justify-items:\s*center;[^}]*text-align:\s*center;/s)
    expect(css).toMatch(/\.project-intro h2\s*{[^}]*font-size:\s*clamp\(40px,\s*5\.2vw,\s*72px\);/s)
  })
})
