import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Routines from './Routines'
import { ThemeProvider } from '../utils/ThemeContext'
import { AuthProvider } from '../utils/AuthContext'
import * as authStore from '../utils/authStore'
import { themes } from '../utils/themes'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

const ROUTINE = {
  id: 3, name: 'Good Night', enabled: true, trigger_type: 'time',
  trigger_config: {}, conditions: [], actions: [],
}

// The run button is auth-gated, so a signed-out render can never exercise it. Same fake-JWT
// scaffolding PersonnelRoster.test.jsx uses.
const b64url = (obj) => btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const fakeJwt = (payload) => `${b64url({ alg: 'none', typ: 'JWT' })}.${b64url(payload)}.sig`

const signIn = async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      access_token: fakeJwt({ sub: '1', type: 'owner', exp: Math.floor(Date.now() / 1000) + 3600 }),
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    }),
  })
  await authStore.login({ username: 'someone', password: 'hunter2' }) // pragma: allowlist secret
}

const renderRoutines = async (runResponse = { ok: true }) => {
  await signIn()
  globalThis.fetch = vi.fn().mockImplementation((url) => {
    if (String(url).includes('/run')) {
      return runResponse.ok
        ? Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
        : Promise.resolve({ ok: false, status: 500, json: async () => ({}) })
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => [ROUTINE] })
  })

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <AuthProvider>
          <Routines />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
  await waitFor(() => expect(screen.getByText('Good Night')).toBeInTheDocument())
  return utils
}

const runButton = () => screen.getByRole('button', { name: 'Run Good Night' })
const ringIn = (el) => el.querySelector('svg[viewBox="0 0 100 100"]')
const toneOf = (svg) => svg.querySelector(':scope > g').style.color
const asRendered = (cssColor) => {
  const probe = document.createElement('span')
  probe.style.color = cssColor
  return probe.style.color
}

describe('Routines run feedback', () => {
  it('shows a play affordance until there is something to report', async () => {
    await renderRoutines()
    const button = runButton()
    expect(button.querySelector('svg.lucide')).toBeInTheDocument()
    expect(ringIn(button)).toBeNull()
  })

  it('settles on the accent when the routine actually fires', async () => {
    await renderRoutines()
    fireEvent.click(runButton())
    // The ring takes over the button the moment the request is in flight, then settles.
    await waitFor(() => expect(ringIn(runButton())).toBeInTheDocument())
    await waitFor(() => {
      expect(toneOf(ringIn(runButton()))).toBe(asRendered(themes.dark.primary))
    })
  })

  it('stalls amber when the run fails, instead of swallowing the error', async () => {
    // handleRun used to catch, console.error and show the user nothing at all.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    await renderRoutines({ ok: false })
    fireEvent.click(runButton())
    await waitFor(() => {
      expect(toneOf(ringIn(runButton()))).toBe(asRendered(themes.dark.env))
    })
    errorSpy.mockRestore()
  })
})
