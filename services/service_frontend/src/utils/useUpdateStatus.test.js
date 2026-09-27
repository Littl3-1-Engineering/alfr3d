import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useUpdateStatus } from './useUpdateStatus'
import socket from './socket'

const originalFetch = globalThis.fetch

describe('useUpdateStatus', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('starts null and fills in from the initial fetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ state: 'idle' }),
    })

    const { result } = renderHook(() => useUpdateStatus())

    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).toEqual({ state: 'idle' }))
  })

  it('updates from a pushed "update_status" socket event', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: 'idle' }) })

    const { result } = renderHook(() => useUpdateStatus())
    await waitFor(() => expect(result.current).toEqual({ state: 'idle' }))

    socket.listeners.get('update_status')?.forEach((cb) =>
      cb({ state: 'running', phase: 'build', target_tag: 'v0.4.9' }),
    )

    await waitFor(() => expect(result.current?.state).toBe('running'))
  })
})
