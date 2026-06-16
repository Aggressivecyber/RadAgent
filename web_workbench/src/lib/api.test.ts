import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchCommandCatalog,
  fetchStatus,
  testModelHealth,
  updateModelConfig,
  type ModelUpdatePayload,
} from './api'

describe('api helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts numeric model budget and repair settings without stripping them', async () => {
    const update = {
      pro_max_tokens: 8192,
      pro_context_window_tokens: 128000,
      max_max_tokens: 16000,
      max_context_window_tokens: 200000,
      agentic_repair_max_turns: 12,
      agentic_repair_history_chars: 36000,
    } satisfies ModelUpdatePayload
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ model: { saved: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateModelConfig(update)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/model',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      }),
    )
  })

  it('reports a friendly local-service message when the Vite API proxy has no body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 502, statusText: 'Bad Gateway' })),
    )

    await expect(fetchStatus()).rejects.toThrow('本地 RadAgent 服务未连接')
  })

  it('posts model health test requests to the dedicated endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ health: { tiers: { pro: { status: 'ok', latency_ms: 35 } } } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const health = await testModelHealth()

    expect(health.tiers.pro.latency_ms).toBe(35)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/model/health',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  it('reports a friendly message for non-JSON API responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>not found</html>', { status: 200, statusText: 'OK' })),
    )

    await expect(fetchCommandCatalog()).rejects.toThrow('工作台服务返回了不可解析的数据')
  })

  it('keeps backend JSON error details when available', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ error: '模型配置缺少 API key' }), {
          status: 400,
          statusText: 'Bad Request',
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(fetchStatus()).rejects.toThrow('模型配置缺少 API key')
  })
})
