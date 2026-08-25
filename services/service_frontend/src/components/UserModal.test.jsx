import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import UserModal from './UserModal'

const baseUser = { id: 2, name: 'Bob', type: 'resident', email: 'bob@example.com', about_me: '', state: 'offline', last_online: null }

function renderModal(props = {}) {
  return render(
    <UserModal
      isOpen={true}
      onClose={() => {}}
      user={baseUser}
      devices={[]}
      onDeviceClick={() => {}}
      onSave={() => {}}
      onDelete={() => {}}
      isAdmin={false}
      onResetPassword={() => Promise.resolve(true)}
      {...props}
    />,
  )
}

describe('UserModal admin controls', () => {
  it('hides Edit/Reset Password/Delete for a non-admin viewer', () => {
    renderModal({ isAdmin: false })

    expect(screen.queryByTitle('Edit User')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Reset Password')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Delete User')).not.toBeInTheDocument()
  })

  it('shows Edit/Reset Password/Delete for an admin viewer', () => {
    renderModal({ isAdmin: true })

    expect(screen.getByTitle('Edit User')).toBeInTheDocument()
    expect(screen.getByTitle('Reset Password')).toBeInTheDocument()
    expect(screen.getByTitle('Delete User')).toBeInTheDocument()
  })

  it('generates a password, calls onResetPassword, and displays it once on success', async () => {
    const onResetPassword = vi.fn().mockResolvedValue(true)
    renderModal({ isAdmin: true, onResetPassword })

    fireEvent.click(screen.getByTitle('Reset Password'))
    expect(screen.getByText(/generate a new password for/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /generate & reset/i }))

    await waitFor(() => expect(onResetPassword).toHaveBeenCalledTimes(1))
    const [userId, generatedPassword] = onResetPassword.mock.calls[0]
    expect(userId).toBe(2)
    expect(generatedPassword.length).toBeGreaterThanOrEqual(8)

    await waitFor(() => expect(screen.getByText(generatedPassword)).toBeInTheDocument())
    expect(screen.getByText(/can't be emailed yet/i)).toBeInTheDocument()
  })

  it('shows an inline error and keeps the confirm panel open when the reset fails', async () => {
    const onResetPassword = vi.fn().mockResolvedValue(false)
    renderModal({ isAdmin: true, onResetPassword })

    fireEvent.click(screen.getByTitle('Reset Password'))
    fireEvent.click(screen.getByRole('button', { name: /generate & reset/i }))

    await waitFor(() => expect(screen.getByText(/reset failed/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /generate & reset/i })).toBeInTheDocument()
  })

  it('cancelling the confirm panel does not call onResetPassword', () => {
    const onResetPassword = vi.fn()
    renderModal({ isAdmin: true, onResetPassword })

    fireEvent.click(screen.getByTitle('Reset Password'))
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onResetPassword).not.toHaveBeenCalled()
    expect(screen.queryByText(/generate a new password for/i)).not.toBeInTheDocument()
  })
})
