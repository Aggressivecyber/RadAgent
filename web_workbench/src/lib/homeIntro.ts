export type HomeIntroState = {
  stage: 'expanded' | 'transitioning' | 'collapsed'
}

export type HomeIntroVisualState = {
  showIntroOverlay: boolean
  suppressAmbientSphere: boolean
  shieldHomeSurface: boolean
  contentState: 'hidden' | 'unfolding' | 'visible'
}

type CreateHomeIntroInput = {
  reducedMotion: boolean
}

type HomeIntroAction = {
  type: 'click' | 'wheel' | 'touch' | 'transitionEnd'
}

export function createHomeIntroState({ reducedMotion }: CreateHomeIntroInput): HomeIntroState {
  return { stage: reducedMotion ? 'collapsed' : 'expanded' }
}

export function reduceHomeIntro(state: HomeIntroState, action: HomeIntroAction): HomeIntroState {
  if (state.stage === 'transitioning') {
    return action.type === 'transitionEnd' ? { stage: 'collapsed' } : state
  }
  if (state.stage === 'collapsed') {
    return state
  }
  if (action.type === 'click') {
    return { stage: 'transitioning' }
  }
  return state
}

export function getHomeIntroVisualState(state: HomeIntroState): HomeIntroVisualState {
  if (state.stage === 'collapsed') {
    return {
      showIntroOverlay: false,
      suppressAmbientSphere: false,
      shieldHomeSurface: false,
      contentState: 'visible',
    }
  }

  return {
    showIntroOverlay: true,
    suppressAmbientSphere: true,
    shieldHomeSurface: true,
    contentState: state.stage === 'transitioning' ? 'unfolding' : 'hidden',
  }
}
