import { describe, expect, it } from 'vitest'
import { buildAskMoreCommand, buildConfirmationCommand, buildRejectCommand } from './confirmationActions'

describe('confirmation action command builders', () => {
  it('builds approval, reject, and ask-more slash commands', () => {
    expect(buildConfirmationCommand()).toBe('/confirm approve')
    expect(buildRejectCommand('  missing detector dimensions  ')).toBe('/reject missing detector dimensions')
    expect(buildAskMoreCommand('  clarify source energy  ')).toBe('/ask-more clarify source energy')
  })

  it('does not create empty reject or ask-more commands', () => {
    expect(buildRejectCommand('')).toBe('')
    expect(buildAskMoreCommand('   ')).toBe('')
  })
})
