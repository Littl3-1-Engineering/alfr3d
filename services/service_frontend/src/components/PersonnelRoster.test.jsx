import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PersonnelRoster from './PersonnelRoster'
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

const usersResponse = {
  users: [
    { id: 1, name: 'Alice', type: 'owner', email: 'alice@example.com', about_me: '', devices: [] },
    { id: 2, name: 'Bob', type: 'resident', email: 'bob@example.com', about_me: '', devices: [] },
  ],
}

function renderRoster() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <PersonnelRoster />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('PersonnelRoster role gating', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('hides Add User from a resident but still shows the read-only roster', async () => {
    await loginAs('resident')
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => usersResponse })

    renderRoster()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add user/i })).not.toBeInTheDocument()
  })

  it('hides Add User from a signed-out visitor', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => usersResponse })

    renderRoster()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /add user/i })).not.toBeInTheDocument()
  })

  it('shows Add User to an owner', async () => {
    await loginAs('owner')
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => usersResponse })

    renderRoster()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /add user/i })).toBeInTheDocument()
  })

  it('shows Add User to the technoking backdoor role', async () => {
    await loginAs('technoking')
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => usersResponse })

    renderRoster()

    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /add user/i })).toBeInTheDocument()
  })
})
