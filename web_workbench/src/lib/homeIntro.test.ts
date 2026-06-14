import { describe, expect, it } from 'vitest'
import { createHomeIntroState, getHomeIntroVisualState, reduceHomeIntro } from './homeIntro'

describe('home intro state', () => {
  it('starts with the expanded particle sphere when motion is allowed', () => {
    expect(createHomeIntroState({ reducedMotion: false })).toEqual({ stage: 'expanded' })
  })

  it('skips the opening sphere for reduced motion users', () => {
    expect(createHomeIntroState({ reducedMotion: true })).toEqual({ stage: 'collapsed' })
  })

  it('moves through a transition before collapsing after click, wheel, or touch intent', () => {
    const state = createHomeIntroState({ reducedMotion: false })

    expect(reduceHomeIntro(state, { type: 'click' })).toEqual({ stage: 'transitioning' })
    expect(reduceHomeIntro(state, { type: 'wheel' })).toEqual({ stage: 'transitioning' })
    expect(reduceHomeIntro(state, { type: 'touch' })).toEqual({ stage: 'transitioning' })
  })

  it('collapses after the transition animation finishes', () => {
    const state = reduceHomeIntro(createHomeIntroState({ reducedMotion: false }), { type: 'click' })

    expect(reduceHomeIntro(state, { type: 'transitionEnd' })).toEqual({ stage: 'collapsed' })
  })

  it('keeps the home background sphere suppressed until the intro fully disappears', () => {
    expect(getHomeIntroVisualState({ stage: 'expanded' })).toMatchObject({
      showIntroOverlay: true,
      suppressAmbientSphere: true,
      shieldHomeSurface: true,
      contentState: 'hidden',
    })
    expect(getHomeIntroVisualState({ stage: 'transitioning' })).toMatchObject({
      showIntroOverlay: true,
      suppressAmbientSphere: true,
      shieldHomeSurface: true,
      contentState: 'unfolding',
    })
    expect(getHomeIntroVisualState({ stage: 'collapsed' })).toMatchObject({
      showIntroOverlay: false,
      suppressAmbientSphere: false,
      shieldHomeSurface: false,
      contentState: 'visible',
    })
  })
})
