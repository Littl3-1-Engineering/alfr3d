import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useUpdateCheck } from './useUpdateCheck'

const originalFetch = globalThis.fetch

describe('useUpdateCheck', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('starts null and fills in once the fetch resolves', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ update_available: true, current_version: '0.4.8', latest_tag: 'v0.4.9' }),
    })

    const { result } = renderHook(() => useUpdateCheck())

    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).not.toBeNull())
    expect(result.current.update_available).toBe(true)
    expect(result.current.latest_tag).toBe('v0.4.9')
  })

  it('leaves updateInfo null when the request fails', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network down'))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const { result } = renderHook(() => useUpdateCheck())

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    expect(result.current).toBeNull()
  })
})
