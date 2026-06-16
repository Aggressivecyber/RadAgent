import { describe, expect, it } from 'vitest'
import { createIntroLandingStyle } from './homeIntroGeometry'

describe('home intro geometry', () => {
  it('targets the exact center and scale of the real home sphere', () => {
    expect(
      createIntroLandingStyle(
        980,
        {
          left: 802,
          top: 120,
          width: 540,
          height: 540,
        },
        {
          width: 1440,
          height: 900,
        },
      ),
    ).toEqual({
      '--intro-home-translate-x': '352px',
      '--intro-home-translate-y': '-60px',
      '--intro-home-scale': `${540 / 980}`,
    })
  })

  it('does not emit landing variables when geometry is unavailable', () => {
    expect(createIntroLandingStyle(0, { left: 0, top: 0, width: 540, height: 540 })).toEqual({})
    expect(createIntroLandingStyle(980, null)).toEqual({})
  })
})
