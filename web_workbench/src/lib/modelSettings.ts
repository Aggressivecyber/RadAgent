export type ModelSettingsDraft = {
  base_url: string
  api_key: string
  api_key_env: string
  lite_model: string
  pro_model: string
  max_model: string
}

export type ModelUpdatePayload = Partial<ModelSettingsDraft>

export type ModelSaveState = {
  status: 'idle' | 'saving' | 'saved' | 'error'
  message: string
  draft?: ModelSettingsDraft
}

type ModelTierView = {
  model_name?: string
  base_url?: string
}

type ModelConfigView = {
  default_api_key_env?: string
  tiers?: Record<string, ModelTierView>
}

export function createModelSettingsDraft(view: unknown): ModelSettingsDraft {
  const config = (view && typeof view === 'object' ? view : {}) as ModelConfigView
  const tiers = config.tiers ?? {}
  return {
    base_url: tiers.pro?.base_url || tiers.lite?.base_url || tiers.max?.base_url || '',
    api_key: '',
    api_key_env: config.default_api_key_env || 'RADAGENT_API_KEY',
    lite_model: tiers.lite?.model_name || '',
    pro_model: tiers.pro?.model_name || '',
    max_model: tiers.max?.model_name || '',
  }
}

export function buildModelUpdate(draft: ModelSettingsDraft): ModelUpdatePayload {
  const update: ModelUpdatePayload = {}
  for (const key of Object.keys(draft) as Array<keyof ModelSettingsDraft>) {
    const value = draft[key].trim()
    if (value) {
      update[key] = value
    }
  }
  return update
}

export function createModelSaveState(): ModelSaveState {
  return { status: 'idle', message: '' }
}

export function reduceModelSaveStart(_state: ModelSaveState): ModelSaveState {
  return { status: 'saving', message: 'Saving model settings...' }
}

export function reduceModelSaveSuccess(
  _state: ModelSaveState,
  draft: ModelSettingsDraft,
): ModelSaveState {
  return {
    status: 'saved',
    message: 'Model settings saved.',
    draft: { ...draft, api_key: '' },
  }
}

export function reduceModelSaveFailure(
  _state: ModelSaveState,
  draft: ModelSettingsDraft,
  message: string,
): ModelSaveState {
  return {
    status: 'error',
    message,
    draft,
  }
}

export function reduceModelViewRefresh(state: ModelSaveState): ModelSaveState {
  if (state.status === 'saved' || state.status === 'error') {
    return state
  }
  return createModelSaveState()
}
