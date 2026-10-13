import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import ThemeSync from './ThemeSync'

const setCurrentTheme = vi.fn()
let theme = 'dark'
let auth = { user: { id: '7' }, isAuthenticated: true }
const handlers = {}
const apiFetch = vi.fn()

vi.mock('../utils/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../utils/useTheme', () => ({ useTheme: () => ({ currentTheme: theme, setCurrentTheme }) }))
vi.mock('../utils/apiClient', () => ({ apiFetch: (...a) => apiFetch(...a) }))
vi.mock('../utils/socket', () => ({
  default: {
    on: (e, cb) => { handlers[e] = cb },
    off: (e) => { delete handlers[e] },
  },
}))

const reply = (value) => ({ ok: true, json: async () => ({ theme: value }) })

describe('ThemeSync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    theme = 'dark'
    auth = { user: { id: '7' }, isAuthenticated: true }
  })

  it('applies a saved server theme that differs from the local one', async () => {
    apiFetch.mockResolvedValue(reply('amber'))
    render(<ThemeSync />)
    await waitFor(() => expect(setCurrentTheme).toHaveBeenCalledWith('amber'))
  })

  it('seeds the server with the local theme when none is saved', async () => {
    apiFetch.mockResolvedValue(reply(null))
    render(<ThemeSync />)
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2))
    const [, opts] = apiFetch.mock.calls[1]
    expect(opts.method).toBe('PUT')
    expect(JSON.parse(opts.body)).toEqual({ theme: 'dark' })
    expect(setCurrentTheme).not.toHaveBeenCalled()
  })

  it('writes a local change back to the server', async () => {
    apiFetch.mockResolvedValue(reply('dark'))
    const { rerender } = render(<ThemeSync />)
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1))
    theme = 'light'
    rerender(<ThemeSync />)
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2))
    expect(JSON.parse(apiFetch.mock.calls[1][1].body)).toEqual({ theme: 'light' })
  })

  it('applies a broadcast for this user and ignores another user', async () => {
    apiFetch.mockResolvedValue(reply('dark'))
    render(<ThemeSync />)
    await waitFor(() => expect(handlers.theme).toBeDefined())
    act(() => handlers.theme({ user_id: 9, theme: 'matrix' }))
    expect(setCurrentTheme).not.toHaveBeenCalled()
    act(() => handlers.theme({ user_id: 7, theme: 'matrix' }))
    expect(setCurrentTheme).toHaveBeenCalledWith('matrix')
  })

  it('does nothing when signed out', () => {
    auth = { user: null, isAuthenticated: false }
    render(<ThemeSync />)
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
