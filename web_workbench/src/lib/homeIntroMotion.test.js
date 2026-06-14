import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyles() {
  return readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
}

function cssBetween(css, start, end) {
  const startIndex = css.indexOf(start)
  const endIndex = css.indexOf(end, startIndex + start.length)
  expect(startIndex).toBeGreaterThanOrEqual(0)
  expect(endIndex).toBeGreaterThan(startIndex)
  return css.slice(startIndex, endIndex)
}

describe('home intro motion CSS', () => {
  it('lands the intro sphere with transform-only animation', () => {
    const keyframes = cssBetween(
      readStyles(),
      '@keyframes intro-anchor-land',
      '@keyframes intro-shell-leave',
    )

    expect(keyframes).not.toMatch(/^\s+(left|top):/m)
    expect(keyframes).toContain(
      'translate3d(var(--intro-home-translate-x), var(--intro-home-translate-y), 0)',
    )
  })

  it('unfolds the home content without clip-path repaint work', () => {
    const css = readStyles()
    const desktopKeyframes = cssBetween(
      css,
      '@keyframes home-content-unfold',
      '.home-hero',
    )
    const mobileKeyframes = cssBetween(
      css,
      '@keyframes home-content-unfold-mobile',
      '@media (prefers-reduced-motion: reduce)',
    )

    expect(desktopKeyframes).not.toContain('clip-path')
    expect(mobileKeyframes).not.toContain('clip-path')
  })

  it('settles the sphere visual and releases the orbit labels during the intro transition', () => {
    const css = readStyles()

    expect(css).toContain('.home-intro-transitioning .hero-sphere-intro canvas')
    expect(css).toContain('.home-intro-transitioning .hero-sphere-intro::before')
    expect(css).toContain('animation: intro-sphere-settle')
    expect(css).toContain('.home-intro-transitioning .hero-sphere-intro .sphere-label')
    expect(css).toContain('animation: intro-labels-release')

    const sphereKeyframes = cssBetween(
      css,
      '@keyframes intro-sphere-settle',
      '@keyframes intro-labels-release',
    )
    const labelsKeyframes = cssBetween(
      css,
      '@keyframes intro-labels-release',
      '@keyframes home-content-unfold',
    )

    expect(sphereKeyframes).toContain('opacity: 0.42')
    expect(labelsKeyframes).toContain('opacity: 0')
  })

  it('crossfades the shell and home content instead of revealing the page abruptly', () => {
    const css = readStyles()
    const shellKeyframes = cssBetween(
      css,
      '@keyframes intro-shell-leave',
      '@keyframes intro-copy-fade',
    )
    const contentRule = cssBetween(
      css,
      '.home-intro-transitioning .hero-copy',
      '.home-shell.ambient-suppressed .home-ambient-sphere',
    )

    expect(shellKeyframes).toContain('68%')
    expect(shellKeyframes).toContain('opacity: 0')
    expect(contentRule).toContain('980ms')
    expect(contentRule).toContain('520ms both')
  })
})
