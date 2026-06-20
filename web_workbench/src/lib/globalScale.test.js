import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyles() {
  return readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
}

describe('global visual scale', () => {
  it('provides one desktop scale variable that enlarges the whole interface without crowding the cockpit', () => {
    const css = readStyles()

    expect(css).toContain('--radagent-ui-scale: 1.2')
    expect(css).toContain('zoom: var(--radagent-ui-scale)')
    expect(css).toContain('@supports not (zoom: 1)')
    expect(css).toContain('transform: scale(var(--radagent-ui-scale))')
  })

  it('turns off the global scale before compact workbench viewports crowd', () => {
    const css = readStyles()
    const compactMedia = css.slice(css.indexOf('@media (max-width: 1320px)'))

    expect(compactMedia).toContain('--radagent-ui-scale: 1')
  })
})
