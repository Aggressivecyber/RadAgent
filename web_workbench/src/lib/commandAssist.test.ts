import { describe, expect, it } from 'vitest'
import { buildRunCommand, buildSimulateCommand, composeCommandTemplate } from './commandAssist'

describe('command assist builders', () => {
  it('builds slash commands for run and simulate controls', () => {
    expect(buildRunCommand('  build a detector  ')).toBe('/run build a detector')
    expect(buildSimulateCommand(250)).toBe('/simulate 250')
    expect(buildSimulateCommand(250, 'job-saved')).toBe('/simulate 250 job-saved')
  })

  it('guards empty run requests and invalid event counts', () => {
    expect(buildRunCommand('')).toBe('')
    expect(buildSimulateCommand(0)).toBe('/simulate 1')
    expect(buildSimulateCommand(Number.NaN)).toBe('/simulate 1')
  })

  it('creates safe composer templates for parameterized commands', () => {
    expect(composeCommandTemplate('/run')).toBe('/run Describe the simulation you want to build')
    expect(composeCommandTemplate('/simulate')).toBe('/simulate 1000')
    expect(composeCommandTemplate('/jobs')).toBe('/jobs')
  })
})
