import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import UpdateBanner from './UpdateBanner'
import { AuthProvider } from '../utils/AuthContext'
import * as authStore from '../utils/authStore'

const originalFetch = globalThis.fetch

function fakeJwt(payload) {
  const b64url = (obj) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${b64url({ alg: 'none', typ: 'JWT' })}.${b64url(payload)}.sig`
}

async function loginAs(role) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      access_token: fakeJwt({ sub: '1', type: role, exp: Math.floor(Date.now() / 1000) + 3600 }),
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    }),
  })
  await authStore.login({ username: 'someone', password: 'hunter2' }) // pragma: allowlist secret
}

const availableResponse = {
  update_available: true,
  current_version: '0.4.8',
  latest_tag: 'v0.4.9',
  latest_title: 'v0.4.9: Test Release',
  release_notes_url: 'https://github.com/Littl3-1-Engineering/alfr3d/releases/tag/v0.4.9',
  release_body: '',
  published_at: '2026-09-27T00:00:00Z',
}

const upToDateResponse = { ...availableResponse, update_available: false }
const idleStatus = { state: 'idle' }

function renderBanner() {
  return render(
    <AuthProvider>
      <UpdateBanner />
    </AuthProvider>,
  )
}

function mockFetchByUrl({ updateCheck = upToDateResponse, updateStatus = idleStatus } = {}) {
  return vi.fn((url) => {
    const body = String(url).includes('/update/status') ? updateStatus : updateCheck
    return Promise.resolve({ ok: true, json: async () => body })
  })
}

describe('UpdateBanner role gating', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('stays hidden for a signed-out visitor even when an update is available', async () => {
    globalThis.fetch = mockFetchByUrl({ updateCheck: availableResponse })

    renderBanner()

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
  })

  it('stays hidden for a resident even when an update is available', async () => {
    await loginAs('resident')
    globalThis.fetch = mockFetchByUrl({ updateCheck: availableResponse })

    renderBanner()

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
  })

  it('shows for an owner when an update is available', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({ updateCheck: availableResponse })

    renderBanner()

    await waitFor(() => expect(screen.getByText(/is available/)).toBeInTheDocument())
  })

  it('stays hidden for an owner when already up to date', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({ updateCheck: upToDateResponse })

    renderBanner()

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
  })

  it('dismisses for the tab when "Later" is clicked and stays dismissed on remount for the same tag', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({ updateCheck: availableResponse })

    const { unmount } = renderBanner()
    await waitFor(() => expect(screen.getByText(/is available/)).toBeInTheDocument())

    fireEvent.click(screen.getByTitle('Later'))
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument()

    unmount()
    renderBanner()
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
  })

  it('opens the confirm modal when Update Now is clicked', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({ updateCheck: availableResponse })

    renderBanner()
    await waitFor(() => expect(screen.getByText(/is available/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /update now/i }))

    expect(screen.getByText(/confirm your password to proceed/i)).toBeInTheDocument()
  })

  it('shows a non-dismissible progress message while an update is running', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({
      updateCheck: upToDateResponse,
      updateStatus: { state: 'running', phase: 'build', target_tag: 'v0.4.9', message: 'Building images for v0.4.9' },
    })

    renderBanner()

    await waitFor(() => expect(screen.getByText(/updating to v0.4.9/i)).toBeInTheDocument())
    expect(screen.queryByTitle('Dismiss')).not.toBeInTheDocument()
  })

  it('shows a dismissible success message once an update completes', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({
      updateCheck: upToDateResponse,
      updateStatus: { state: 'success', phase: 'done', target_tag: 'v0.4.9', updated_at: '2026-09-27T12:00:00Z' },
    })

    renderBanner()

    await waitFor(() => expect(screen.getByText(/updated to v0.4.9/i)).toBeInTheDocument())
    fireEvent.click(screen.getByTitle('Dismiss'))
    expect(screen.queryByText(/updated to v0.4.9/i)).not.toBeInTheDocument()
  })

  it('shows a dismissible failure message with detail when a rollback occurs', async () => {
    await loginAs('owner')
    globalThis.fetch = mockFetchByUrl({
      updateCheck: upToDateResponse,
      updateStatus: {
        state: 'rolled_back',
        phase: 'rollback',
        target_tag: 'v0.4.9',
        message: 'Rolled back to the previous version. Schema is still at the new migration head.',
        updated_at: '2026-09-27T12:05:00Z',
      },
    })

    renderBanner()

    await waitFor(() => expect(screen.getByText(/rolled back to the previous version/i)).toBeInTheDocument())
  })
})
