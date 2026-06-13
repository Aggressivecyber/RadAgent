import { describe, expect, it } from 'vitest'
import { createHomeIntroState, reduceHomeIntro } from './homeIntro'

describe('home intro state', () => {
  it('starts with the expanded particle sphere when motion is allowed', () => {
    expect(createHomeIntroState({ reducedMotion: false })).toEqual({ stage: 'expanded' })
  })

  it('skips the opening sphere for reduced motion users', () => {
    expect(createHomeIntroState({ reducedMotion: true })).toEqual({ stage: 'collapsed' })
  })

  it('collapses the opening sphere after click, wheel, or touch intent', () => {
    const state = createHomeIntroState({ reducedMotion: false })

    expect(reduceHomeIntro(state, { type: 'click' })).toEqual({ stage: 'collapsed' })
    expect(reduceHomeIntro(state, { type: 'wheel' })).toEqual({ stage: 'collapsed' })
    expect(reduceHomeIntro(state, { type: 'touch' })).toEqual({ stage: 'collapsed' })
  })
})
