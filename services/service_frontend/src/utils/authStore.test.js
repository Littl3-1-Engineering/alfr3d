import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const originalFetch = globalThis.fetch

function b64url(obj) {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fakeJwt(payload) {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.signature`
}

const mockFetch = ({ ok = true, json = {}, status = 200 } = {}) => {
  const fn = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => json,
  })
  globalThis.fetch = fn
  return fn
}

describe('authStore', () => {
  let authStore

  beforeEach(async () => {
    sessionStorage.clear()
    localStorage.clear()
    vi.resetModules()
    authStore = await import('./authStore')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('starts with no tokens', () => {
    expect(authStore.getAccessToken()).toBeNull()
    expect(authStore.getRefreshToken()).toBeNull()
  })

  it('login stores both tokens and persists the refresh token to localStorage', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })

    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    expect(authStore.getAccessToken()).toBe('access-1')
    expect(authStore.getRefreshToken()).toBe('refresh-1')
    expect(localStorage.getItem('alfr3d-refresh-token')).toBe('refresh-1')
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'alice', password: 'hunter2' }),
      }),
    )
  })

  it('login throws with the backend detail message on failure', async () => {
    mockFetch({ ok: false, status: 401, json: { detail: 'Invalid username or password' } })

    await expect(authStore.login({ username: 'alice', password: 'wrong' })).rejects.toThrow( // pragma: allowlist secret
      'Invalid username or password',
    )
    expect(authStore.getAccessToken()).toBeNull()
  })

  it('refresh rotates the token pair on success', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    mockFetch({ json: { access_token: 'access-2', refresh_token: 'refresh-2', token_type: 'bearer' } })
    const result = await authStore.refresh()

    expect(result.access_token).toBe('access-2')
    expect(authStore.getAccessToken()).toBe('access-2')
    expect(authStore.getRefreshToken()).toBe('refresh-2')
  })

  it('refresh clears stored tokens and returns null when the server rejects the token', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    mockFetch({ ok: false, status: 401, json: { detail: 'Invalid or expired refresh token' } })
    const result = await authStore.refresh()

    expect(result).toBeNull()
    expect(authStore.getAccessToken()).toBeNull()
    expect(authStore.getRefreshToken()).toBeNull()
    expect(localStorage.getItem('alfr3d-refresh-token')).toBeNull()
  })

  it('refresh keeps tokens on a network error or 5xx so a blip does not log you out', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    expect(await authStore.refresh()).toBeNull()
    expect(authStore.getRefreshToken()).toBe('refresh-1')
    expect(localStorage.getItem('alfr3d-refresh-token')).toBe('refresh-1')

    mockFetch({ ok: false, status: 503, json: {} })
    expect(await authStore.refresh()).toBeNull()
    expect(authStore.getRefreshToken()).toBe('refresh-1')
  })

  it('migrates a legacy sessionStorage refresh token to localStorage', async () => {
    sessionStorage.setItem('alfr3d-refresh-token', 'legacy-1')
    vi.resetModules()
    authStore = await import('./authStore')
    expect(authStore.getRefreshToken()).toBe('legacy-1')
    expect(localStorage.getItem('alfr3d-refresh-token')).toBe('legacy-1')
    expect(sessionStorage.getItem('alfr3d-refresh-token')).toBeNull()
  })

  it('proactively refreshes shortly before the access token expires', async () => {
    vi.useFakeTimers()
    try {
      const exp = Math.floor(Date.now() / 1000) + 15 * 60
      mockFetch({ json: { access_token: fakeJwt({ sub: '1', type: 'owner', exp }), refresh_token: 'refresh-1' } })
      await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

      const fetchMock = mockFetch({ json: { access_token: 'access-2', refresh_token: 'refresh-2' } })
      await vi.advanceTimersByTimeAsync(14 * 60 * 1000 + 1000)

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(authStore.getAccessToken()).toBe('access-2')
    } finally {
      vi.useRealTimers()
    }
  })

  it('refresh is a no-op when there is no refresh token', async () => {
    const fetchMock = mockFetch()
    const result = await authStore.refresh()
    expect(result).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('concurrent refresh calls share one in-flight request instead of racing', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    const fetchMock = mockFetch({
      json: { access_token: 'access-2', refresh_token: 'refresh-2', token_type: 'bearer' },
    })

    // Two callers racing after the access token expired (e.g. two apiFetch calls both hit a
    // 401 around the same time) must not send two /refresh requests with the same single-use
    // refresh token -- that would have the loser's 401 wipe out the winner's fresh tokens.
    const [first, second] = await Promise.all([authStore.refresh(), authStore.refresh()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(first).toBe(second)
    expect(authStore.getAccessToken()).toBe('access-2')
    expect(authStore.getRefreshToken()).toBe('refresh-2')
  })

  it('logout clears tokens and best-effort notifies the backend', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    mockFetch({ json: { success: true } })
    await authStore.logout()

    expect(authStore.getAccessToken()).toBeNull()
    expect(authStore.getRefreshToken()).toBeNull()
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/logout'),
      expect.objectContaining({ body: JSON.stringify({ refresh_token: 'refresh-1' }) }),
    )
  })

  it('logout clears local state even if the server call fails', async () => {
    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network down'))
    await authStore.logout()

    expect(authStore.getAccessToken()).toBeNull()
    expect(authStore.getRefreshToken()).toBeNull()
  })

  it('notifies subscribers on every token change', async () => {
    const listener = vi.fn()
    const unsubscribe = authStore.subscribe(listener)

    mockFetch({ json: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } })
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret
    expect(listener).toHaveBeenCalledTimes(1)

    await authStore.logout()
    expect(listener).toHaveBeenCalledTimes(2)

    unsubscribe()
  })

  it('decodeJwtPayload reads the payload without verifying the signature', () => {
    const token = fakeJwt({ sub: '1', type: 'technoking', exp: 12345 })
    expect(authStore.decodeJwtPayload(token)).toEqual({ sub: '1', type: 'technoking', exp: 12345 })
  })

  it('decodeJwtPayload returns null for garbage input', () => {
    expect(authStore.decodeJwtPayload('not-a-jwt')).toBeNull()
    expect(authStore.decodeJwtPayload(null)).toBeNull()
  })
})
