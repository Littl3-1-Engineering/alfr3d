import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import UpdateConfirmModal from './UpdateConfirmModal'

const originalFetch = globalThis.fetch

const updateInfo = {
  latest_tag: 'v0.4.9',
  latest_title: 'v0.4.9: Test Release',
  release_body: 'Some release notes',
}

describe('UpdateConfirmModal', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('renders the release notes and a password field when open', () => {
    render(
      <UpdateConfirmModal isOpen={true} onClose={() => {}} updateInfo={updateInfo} />,
    )

    expect(screen.getByText(/v0.4.9: test release/i)).toBeInTheDocument()
    expect(screen.getByText(/some release notes/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/confirm your password/i)).toBeInTheDocument()
  })

  it('submits the target tag and password, then closes on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ message: 'Update started', target_tag: 'v0.4.9' }),
    })
    const onClose = vi.fn()
    const onStarted = vi.fn()

    render(
      <UpdateConfirmModal isOpen={true} onClose={onClose} updateInfo={updateInfo} onStarted={onStarted} />,
    )

    fireEvent.change(screen.getByLabelText(/confirm your password/i), { target: { value: 'hunter2' } }) // pragma: allowlist secret
    fireEvent.click(screen.getByRole('button', { name: /update now/i }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(onStarted).toHaveBeenCalled()
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/system/update/start'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ target_tag: 'v0.4.9', current_password: 'hunter2' }), // pragma: allowlist secret
      }),
    )
  })

  it('shows the backend error inline and stays open on a wrong password', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Current password is incorrect' }),
    })
    const onClose = vi.fn()

    render(<UpdateConfirmModal isOpen={true} onClose={onClose} updateInfo={updateInfo} />)

    fireEvent.change(screen.getByLabelText(/confirm your password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /update now/i }))

    await waitFor(() => expect(screen.getByText('Current password is incorrect')).toBeInTheDocument())
    expect(onClose).not.toHaveBeenCalled()
  })
})
