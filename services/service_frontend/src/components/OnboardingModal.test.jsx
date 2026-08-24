import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import OnboardingModal from './OnboardingModal'
import { AuthProvider } from '../utils/AuthContext'

const originalFetch = globalThis.fetch

const unclaimedStatus = {
  state: 'unclaimed',
  claimable_users: [
    { id: 1, username: 'athos', type: 'technoking' },
    { id: 2, username: 'guestroom', type: 'resident' },
  ],
}

const emptyStatus = { state: 'empty', claimable_users: [] }

describe('OnboardingModal', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults to claim mode with a dropdown of claimable users when unclaimed', () => {
    render(
      <AuthProvider>
        <OnboardingModal isOpen={true} onClose={() => {}} setupStatus={unclaimedStatus} />
      </AuthProvider>,
    )

    expect(screen.getByLabelText(/account/i)).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /athos/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /claim account/i })).toBeInTheDocument()
  })

  it('goes straight to create mode when the system is empty', () => {
    render(
      <AuthProvider>
        <OnboardingModal isOpen={true} onClose={() => {}} setupStatus={emptyStatus} />
      </AuthProvider>,
    )

    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/account/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument()
  })

  it('claims the selected account and closes on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }),
    })
    const onClose = vi.fn()
    const onSetupComplete = vi.fn()

    render(
      <AuthProvider>
        <OnboardingModal
          isOpen={true}
          onClose={onClose}
          setupStatus={unclaimedStatus}
          onSetupComplete={onSetupComplete}
        />
      </AuthProvider>,
    )

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'newpassword123' } }) // pragma: allowlist secret
    fireEvent.click(screen.getByRole('button', { name: /claim account/i }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(onSetupComplete).toHaveBeenCalled()
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/claim'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'athos', password: 'newpassword123' }), // pragma: allowlist secret
      }),
    )
  })

  it('bootstraps a new account when switched to create mode', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }),
    })
    const onClose = vi.fn()

    render(
      <AuthProvider>
        <OnboardingModal isOpen={true} onClose={onClose} setupStatus={unclaimedStatus} />
      </AuthProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /create new/i }))
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'newadmin' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'newpassword123' } }) // pragma: allowlist secret
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/bootstrap'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'newadmin', password: 'newpassword123' }), // pragma: allowlist secret
      }),
    )
  })

  it('shows the backend error message on failure', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Unable to claim this account' }),
    })

    render(
      <AuthProvider>
        <OnboardingModal isOpen={true} onClose={() => {}} setupStatus={unclaimedStatus} />
      </AuthProvider>,
    )

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'newpassword123' } })
    fireEvent.click(screen.getByRole('button', { name: /claim account/i }))

    await waitFor(() =>
      expect(screen.getByText('Unable to claim this account')).toBeInTheDocument(),
    )
  })
})
