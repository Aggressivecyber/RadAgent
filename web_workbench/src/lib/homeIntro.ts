export type HomeIntroState = {
  stage: 'expanded' | 'collapsed'
}

type CreateHomeIntroInput = {
  reducedMotion: boolean
}

type HomeIntroAction = {
  type: 'click' | 'wheel' | 'touch'
}

export function createHomeIntroState({ reducedMotion }: CreateHomeIntroInput): HomeIntroState {
  return { stage: reducedMotion ? 'collapsed' : 'expanded' }
}

export function reduceHomeIntro(state: HomeIntroState, action: HomeIntroAction): HomeIntroState {
  if (state.stage === 'collapsed') {
    return state
  }
  if (action.type === 'click' || action.type === 'wheel' || action.type === 'touch') {
    return { stage: 'collapsed' }
  }
  return state
}
