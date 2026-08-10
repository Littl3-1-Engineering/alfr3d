import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useRoutines,
  useCreateRoutine,
  useUpdateRoutine,
  useDeleteRoutine,
  usePersonality,
  usePersonalityPresets,
  useLlmConfig,
  useUpdatePersonality,
  useQuips,
  useCreateQuip,
  useUpdateQuip,
  useDeleteQuip,
  useIntegrationStatus,
  useIotStatus,
} from './useApi'

const originalFetch = globalThis.fetch

function makeWrapper(client) {
  return function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

function createClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
}

describe('useApi hooks', () => {
  let client
  let wrapper

  beforeEach(() => {
    client = createClient()
    wrapper = makeWrapper(client)
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  const mockFetch = ({ ok = true, json = {}, status = 200 } = {}) => {
    const fn = vi.fn().mockResolvedValue({
      ok,
      status,
      json: async () => json,
    })
    globalThis.fetch = fn
    return fn
  }

  it('useRoutines fetches routines from the API', async () => {
    const fetchMock = mockFetch({ json: [{ id: 1, name: 'morning' }] })
    const { result } = renderHook(() => useRoutines(), { wrapper })

    expect(result.current.isPending).toBe(true)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([{ id: 1, name: 'morning' }])
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/routines'))
  })

  it('useRoutines surfaces API errors', async () => {
    mockFetch({ ok: false, status: 500 })
    const { result } = renderHook(() => useRoutines(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(Error)
  })

  it('usePersonality, usePersonalityPresets and useLlmConfig query their endpoints', async () => {
    mockFetch({ json: { personality: 'formal' } })
    const a = renderHook(() => usePersonality(), { wrapper })
    await waitFor(() => expect(a.result.current.isSuccess).toBe(true))
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/personality'))

    mockFetch({ json: ['formal', 'casual'] })
    const b = renderHook(() => usePersonalityPresets(), { wrapper })
    await waitFor(() => expect(b.result.current.isSuccess).toBe(true))
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/personality/presets'))

    mockFetch({ json: { model: 'claude' } })
    const c = renderHook(() => useLlmConfig(), { wrapper })
    await waitFor(() => expect(c.result.current.isSuccess).toBe(true))
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/personality/llm-config'))
  })

  it('useQuips and useIntegrationStatus/useIotStatus query their endpoints', async () => {
    mockFetch({ json: ['a quip'] })
    const a = renderHook(() => useQuips(), { wrapper })
    await waitFor(() => expect(a.result.current.isSuccess).toBe(true))
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/quips'))

    mockFetch({ json: {} })
    const b = renderHook(() => useIntegrationStatus(), { wrapper })
    await waitFor(() => expect(b.result.current.isSuccess).toBe(true))
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/integrations/status'))

    mockFetch({ json: {} })
    const c = renderHook(() => useIotStatus(), { wrapper })
    await waitFor(() => expect(c.result.current.isSuccess).toBe(true))
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/iot/status'))
  })

  it('useCreateRoutine POSTs and invalidates the routines query', async () => {
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
    mockFetch({ json: { id: 2 } })
    const { result } = renderHook(() => useCreateRoutine(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ name: 'night' })
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/routines'),
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'night' }),
      }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['routines'] })
  })

  it('useUpdateRoutine PUTs with the id in the URL', async () => {
    mockFetch({ json: { id: 1, name: 'updated' } })
    const { result } = renderHook(() => useUpdateRoutine(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, name: 'updated' })
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/routines/1'),
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('useDeleteRoutine DELETEs by id', async () => {
    mockFetch({ ok: true })
    const { result } = renderHook(() => useDeleteRoutine(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(7)
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/routines/7'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('useUpdatePersonality PUTs and invalidates the personality query', async () => {
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
    mockFetch({ json: {} })
    const { result } = renderHook(() => useUpdatePersonality(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ personality: 'casual' })
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/personality'),
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['personality'] })
  })

  it('useCreateQuip/useUpdateQuip/useDeleteQuip hit the quips endpoints', async () => {
    mockFetch({ json: { id: 1 } })
    const create = renderHook(() => useCreateQuip(), { wrapper })
    await act(async () => {
      await create.result.current.mutateAsync({ text: 'hi' })
    })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/quips'),
      expect.objectContaining({ method: 'POST' }),
    )

    mockFetch({ json: {} })
    const update = renderHook(() => useUpdateQuip(), { wrapper })
    await act(async () => {
      await update.result.current.mutateAsync({ id: 1, text: 'bye' })
    })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/quips/1'),
      expect.objectContaining({ method: 'PUT' }),
    )

    mockFetch({ ok: true })
    const del = renderHook(() => useDeleteQuip(), { wrapper })
    await act(async () => {
      await del.result.current.mutateAsync(3)
    })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/quips/3'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('mutations reject when the API returns an error', async () => {
    mockFetch({ ok: false, status: 400 })
    const { result } = renderHook(() => useCreateRoutine(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ name: 'x' })).rejects.toThrow(
        'Failed to create routine',
      )
    })
  })
})
