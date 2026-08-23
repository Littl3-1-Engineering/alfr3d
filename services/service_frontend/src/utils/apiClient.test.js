import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const originalFetch = globalThis.fetch

describe('apiClient', () => {
  let apiFetch
  let authStore

  beforeEach(async () => {
    sessionStorage.clear()
    vi.resetModules()
    authStore = await import('./authStore')
    ;({ apiFetch } = await import('./apiClient'))
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('does not add an Authorization header when there is no access token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    globalThis.fetch = fetchMock

    await apiFetch('http://api.test/api/devices', { method: 'GET' })

    const [, options] = fetchMock.mock.calls[0]
    expect(options.headers.Authorization).toBeUndefined()
  })

  it('injects the bearer access token when present', async () => {
    const loginFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }),
    })
    globalThis.fetch = loginFetch
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    globalThis.fetch = fetchMock

    await apiFetch('http://api.test/api/devices/1', { method: 'PUT' })

    const [, options] = fetchMock.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer access-1')
  })

  it('on a 401, refreshes once and retries the original request', async () => {
    const loginFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }),
    })
    globalThis.fetch = loginFetch
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    const responses = [
      { ok: false, status: 401 },
      { ok: true, status: 200, json: async () => ({ access_token: 'access-2', refresh_token: 'refresh-2', token_type: 'bearer' }) },
      { ok: true, status: 200 },
    ]
    const fetchMock = vi.fn(() => Promise.resolve(responses.shift()))
    globalThis.fetch = fetchMock

    const response = await apiFetch('http://api.test/api/devices/1', { method: 'PUT' })

    expect(response.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(3) // original 401, refresh call, retried request
    expect(authStore.getAccessToken()).toBe('access-2')

    const retryCall = fetchMock.mock.calls[2]
    expect(retryCall[0]).toBe('http://api.test/api/devices/1')
    expect(retryCall[1].headers.Authorization).toBe('Bearer access-2')
  })

  it('on a 401 with a failed refresh, returns the original 401 without an infinite retry loop', async () => {
    const loginFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }),
    })
    globalThis.fetch = loginFetch
    await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret

    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    globalThis.fetch = fetchMock

    const response = await apiFetch('http://api.test/api/devices/1', { method: 'PUT' })

    expect(response.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(2) // original 401, failed refresh attempt -- no retry
    expect(authStore.getAccessToken()).toBeNull()
  })

  it('a 401 with no refresh token available just returns the 401', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    globalThis.fetch = fetchMock

    const response = await apiFetch('http://api.test/api/devices/1', { method: 'PUT' })

    expect(response.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
