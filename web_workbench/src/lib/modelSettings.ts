export type ModelSettingsDraft = {
  base_url: string
  api_key: string
  api_key_env: string
  lite_model: string
  pro_model: string
  max_model: string
  pro_max_tokens: string
  pro_context_window_tokens: string
  max_max_tokens: string
  max_context_window_tokens: string
  agentic_repair_max_turns: string
  agentic_repair_history_chars: string
}

export type ModelUpdatePayload = Partial<
  Omit<
    ModelSettingsDraft,
    | 'agentic_repair_max_turns'
    | 'agentic_repair_history_chars'
    | 'pro_max_tokens'
    | 'pro_context_window_tokens'
    | 'max_max_tokens'
    | 'max_context_window_tokens'
  >
> & {
  agentic_repair_max_turns?: number
  agentic_repair_history_chars?: number
  pro_max_tokens?: number
  pro_context_window_tokens?: number
  max_max_tokens?: number
  max_context_window_tokens?: number
}

export type ModelSaveState = {
  status: 'idle' | 'saving' | 'saved' | 'error'
  message: string
  draft?: ModelSettingsDraft
}

type ModelTierView = {
  model_name?: string
  base_url?: string
  max_tokens?: number
  context_window_tokens?: number
}

type ModelConfigView = {
  default_api_key_env?: string
  agentic_repair_max_turns?: number
  agentic_repair_history_chars?: number
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
    pro_max_tokens: String(tiers.pro?.max_tokens ?? 8192),
    pro_context_window_tokens: String(tiers.pro?.context_window_tokens ?? 1000000),
    max_max_tokens: String(tiers.max?.max_tokens ?? 12000),
    max_context_window_tokens: String(tiers.max?.context_window_tokens ?? 1000000),
    agentic_repair_max_turns: String(config.agentic_repair_max_turns ?? 24),
    agentic_repair_history_chars: String(config.agentic_repair_history_chars ?? 0),
  }
}

export function buildModelUpdate(draft: ModelSettingsDraft): ModelUpdatePayload {
  const update: ModelUpdatePayload = {}
  for (const key of Object.keys(draft) as Array<keyof ModelSettingsDraft>) {
    const value = draft[key].trim()
    if (!value) {
      continue
    }
    switch (key) {
      case 'agentic_repair_max_turns':
        update.agentic_repair_max_turns = Number(value)
        break
      case 'agentic_repair_history_chars':
        update.agentic_repair_history_chars = Number(value)
        break
      case 'pro_max_tokens':
        update.pro_max_tokens = Number(value)
        break
      case 'pro_context_window_tokens':
        update.pro_context_window_tokens = Number(value)
        break
      case 'max_max_tokens':
        update.max_max_tokens = Number(value)
        break
      case 'max_context_window_tokens':
        update.max_context_window_tokens = Number(value)
        break
      case 'base_url':
        update.base_url = value
        break
      case 'api_key':
        update.api_key = value
        break
      case 'api_key_env':
        update.api_key_env = value
        break
      case 'lite_model':
        update.lite_model = value
        break
      case 'pro_model':
        update.pro_model = value
        break
      case 'max_model':
        update.max_model = value
        break
    }
  }
  return update
}

export function createModelSaveState(): ModelSaveState {
  return { status: 'idle', message: '' }
}

export function reduceModelSaveStart(_state: ModelSaveState): ModelSaveState {
  return { status: 'saving', message: '正在保存模型设置...' }
}

export function reduceModelSaveSuccess(
  _state: ModelSaveState,
  draft: ModelSettingsDraft,
): ModelSaveState {
  return {
    status: 'saved',
    message: '模型设置已保存。',
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
