export type IntroLandingStyle = {
  '--intro-home-translate-x'?: string
  '--intro-home-translate-y'?: string
  '--intro-home-scale'?: string
}

type RectLike = {
  left: number
  top: number
  width: number
  height: number
}

type ViewportLike = {
  width: number
  height: number
}

export function createIntroLandingStyle(
  sourceWidth: number,
  target: RectLike | null | undefined,
  viewport: ViewportLike | null | undefined = {
    width: globalThis.window?.innerWidth ?? 0,
    height: globalThis.window?.innerHeight ?? 0,
  },
): IntroLandingStyle {
  if (
    !target ||
    !viewport ||
    sourceWidth <= 0 ||
    target.width <= 0 ||
    target.height <= 0 ||
    viewport.width <= 0 ||
    viewport.height <= 0
  ) {
    return {}
  }

  const targetCenterX = target.left + target.width / 2
  const targetCenterY = target.top + target.height / 2
  const viewportCenterX = viewport.width / 2
  const viewportCenterY = viewport.height / 2

  return {
    '--intro-home-translate-x': `${targetCenterX - viewportCenterX}px`,
    '--intro-home-translate-y': `${targetCenterY - viewportCenterY}px`,
    '--intro-home-scale': `${target.width / sourceWidth}`,
  }
}
