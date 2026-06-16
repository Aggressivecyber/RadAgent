import { describe, expect, it } from 'vitest'
import {
  buildModelUpdate,
  createModelSaveState,
  createModelSettingsDraft,
  reduceModelSaveFailure,
  reduceModelSaveStart,
  reduceModelSaveSuccess,
  reduceModelViewRefresh,
} from './modelSettings'

describe('model settings helpers', () => {
  it('creates an editable draft from a frontend-safe model view', () => {
    const draft = createModelSettingsDraft({
      default_api_key_env: 'RADAGENT_API_KEY',
      tiers: {
        lite: { model_name: 'lite-1', base_url: 'https://api.example/v1' },
        pro: {
          model_name: 'pro-1',
          base_url: 'https://api.example/v1',
          max_tokens: 8192,
          context_window_tokens: 128000,
        },
        max: {
          model_name: 'max-1',
          base_url: 'https://api.example/v1',
          max_tokens: 16000,
          context_window_tokens: 200000,
        },
      },
      agentic_repair_max_turns: 18,
      agentic_repair_history_chars: 36000,
    })

    expect(draft).toEqual({
      base_url: 'https://api.example/v1',
      api_key: '',
      api_key_env: 'RADAGENT_API_KEY',
      lite_model: 'lite-1',
      pro_model: 'pro-1',
      max_model: 'max-1',
      pro_max_tokens: '8192',
      pro_context_window_tokens: '128000',
      max_max_tokens: '16000',
      max_context_window_tokens: '200000',
      agentic_repair_max_turns: '18',
      agentic_repair_history_chars: '36000',
    })
  })

  it('builds an update payload without empty write-only fields', () => {
    const update = buildModelUpdate({
      base_url: ' https://api.example/v1 ',
      api_key: '   ',
      api_key_env: ' RADAGENT_API_KEY ',
      lite_model: 'lite-2',
      pro_model: 'pro-2',
      max_model: '',
      pro_max_tokens: ' 8192 ',
      pro_context_window_tokens: ' 128000 ',
      max_max_tokens: '',
      max_context_window_tokens: ' 200000 ',
      agentic_repair_max_turns: ' 12 ',
      agentic_repair_history_chars: ' 36000 ',
    })

    expect(update).toEqual({
      base_url: 'https://api.example/v1',
      api_key_env: 'RADAGENT_API_KEY',
      lite_model: 'lite-2',
      pro_model: 'pro-2',
      pro_max_tokens: 8192,
      pro_context_window_tokens: 128000,
      max_context_window_tokens: 200000,
      agentic_repair_max_turns: 12,
      agentic_repair_history_chars: 36000,
    })
  })

  it('tracks model save success and clears only the write-only api key', () => {
    const draft = createModelSettingsDraft({
      default_api_key_env: 'RADAGENT_API_KEY',
      tiers: { pro: { model_name: 'pro-1', base_url: 'https://api.example/v1' } },
    })
    const started = reduceModelSaveStart(createModelSaveState())
    const saved = reduceModelSaveSuccess(started, { ...draft, api_key: 'secret' })

    expect(started).toEqual({ status: 'saving', message: '正在保存模型设置...' })
    expect(saved.status).toBe('saved')
    expect(saved.message).toBe('模型设置已保存。')
    const savedDraft = saved.draft
    expect(savedDraft).toBeDefined()
    expect(savedDraft?.api_key).toBe('')
    expect(savedDraft?.pro_model).toBe('pro-1')
    expect(draft.pro_context_window_tokens).toBe('1000000')
    expect(draft.max_context_window_tokens).toBe('1000000')
    expect(draft.agentic_repair_history_chars).toBe('0')
  })

  it('keeps the current draft visible when model save fails', () => {
    const current = {
      base_url: 'https://api.example/v1',
      api_key: 'secret',
      api_key_env: 'RADAGENT_API_KEY',
      lite_model: 'lite-1',
      pro_model: 'pro-1',
      max_model: 'max-1',
      pro_max_tokens: '8192',
      pro_context_window_tokens: '128000',
      max_max_tokens: '16000',
      max_context_window_tokens: '200000',
      agentic_repair_max_turns: '24',
      agentic_repair_history_chars: '48000',
    }

    const failed = reduceModelSaveFailure(reduceModelSaveStart(createModelSaveState()), current, 'Network failed')

    expect(failed).toEqual({
      status: 'error',
      message: 'Network failed',
      draft: current,
    })
  })

  it('does not erase a visible save message when the refreshed model view arrives', () => {
    const saved = reduceModelSaveSuccess(createModelSaveState(), {
      base_url: 'https://api.example/v1',
      api_key: 'secret',
      api_key_env: 'RADAGENT_API_KEY',
      lite_model: 'lite-1',
      pro_model: 'pro-1',
      max_model: 'max-1',
      pro_max_tokens: '8192',
      pro_context_window_tokens: '128000',
      max_max_tokens: '16000',
      max_context_window_tokens: '200000',
      agentic_repair_max_turns: '24',
      agentic_repair_history_chars: '48000',
    })

    expect(reduceModelViewRefresh(saved).message).toBe('模型设置已保存。')
    expect(reduceModelViewRefresh(createModelSaveState()).status).toBe('idle')
  })
})
