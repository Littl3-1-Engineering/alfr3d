import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Profile from './Profile'
import { AuthProvider } from '../utils/AuthContext'
import * as authStore from '../utils/authStore'

const originalFetch = globalThis.fetch

function fakeJwt(payload) {
  const b64url = (obj) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${b64url({ alg: 'none', typ: 'JWT' })}.${b64url(payload)}.sig`
}

async function loginAsSelf() {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      access_token: fakeJwt({ sub: '2', type: 'resident', exp: Math.floor(Date.now() / 1000) + 3600 }),
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    }),
  })
  await authStore.login({ username: 'alice', password: 'hunter2' }) // pragma: allowlist secret
}

describe('Profile', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it("loads and displays the signed-in user's own fields, not someone else's", async () => {
    await loginAsSelf()
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { id: 1, name: 'Bob', type: 'guest', email: 'bob@example.com', about_me: 'not me' },
        { id: 2, name: 'Alice', type: 'resident', email: 'alice@example.com', about_me: 'hi there', title: 'boss' },
      ],
    })

    render(
      <AuthProvider>
        <Profile />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByDisplayValue('Alice')).toBeInTheDocument())
    expect(screen.getByDisplayValue('alice@example.com')).toBeInTheDocument()
    expect(screen.getByDisplayValue('hi there')).toBeInTheDocument()
    expect(screen.getByDisplayValue('boss')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('Bob')).not.toBeInTheDocument()
  })

  it('saves edits via PUT /api/users/{id} without ever sending `type`', async () => {
    await loginAsSelf()
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: 2, name: 'Alice', type: 'resident', email: '', about_me: '' }],
    })

    render(
      <AuthProvider>
        <Profile />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByDisplayValue('Alice')).toBeInTheDocument())

    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Alice Updated' } })
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))

    await waitFor(() => expect(screen.getByText('Profile updated')).toBeInTheDocument())
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/users/2'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ name: 'Alice Updated', email: '', about_me: '', title: '' }),
      }),
    )
  })
})
