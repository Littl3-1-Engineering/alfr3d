import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LoginModal from './LoginModal'
import { AuthProvider } from '../utils/AuthContext'

const originalFetch = globalThis.fetch

describe('LoginModal', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders the sign-in form when open', () => {
    render(
      <AuthProvider>
        <LoginModal isOpen={true} onClose={() => {}} />
      </AuthProvider>,
    )

    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('submits credentials and closes on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }),
    })
    const onClose = vi.fn()

    render(
      <AuthProvider>
        <LoginModal isOpen={true} onClose={onClose} />
      </AuthProvider>,
    )

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'hunter2' } }) // pragma: allowlist secret
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'alice', password: 'hunter2' }), // pragma: allowlist secret
      }),
    )
  })

  it('shows the backend error message on failed login', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid username or password' }),
    })

    render(
      <AuthProvider>
        <LoginModal isOpen={true} onClose={() => {}} />
      </AuthProvider>,
    )

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText('Invalid username or password')).toBeInTheDocument())
  })
})
