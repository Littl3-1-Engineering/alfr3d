import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import SituationalAwareness from './SituationalAwareness'
import { ThemeProvider } from '../utils/ThemeContext'

// Its own file for the same reason as HudRing.reducedMotion.test.jsx: framer-motion resolves the
// reduced-motion query once, globally, so the hook has to be mocked to exercise the branch.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion')
  return { ...actual, useReducedMotion: () => true }
})
vi.mock('../utils/socket', () => ({ default: { on: vi.fn(), off: vi.fn() } }))

describe('SituationalAwareness under prefers-reduced-motion', () => {
  it('shows a card at once instead of sliding it in, and keeps its controls', async () => {
    const data = [
      { mode: 'weather', rule_id: 'weather', subject_key: '', content: 'sunny', priority: 5 },
    ]
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => data })
    render(
      <ThemeProvider>
        <SituationalAwareness />
      </ThemeProvider>,
    )

    const content = await screen.findByText('sunny')
    // No entrance animation: the card is already fully opaque and in place on first paint.
    const cardEl = content.closest('div.relative')
    expect(cardEl.style.opacity).toBe('1')
    expect(cardEl.style.transform === '' || cardEl.style.transform === 'none').toBe(true)
    expect(screen.getByLabelText('Got it')).toBeTruthy()
    expect(screen.getByLabelText('Not useful')).toBeTruthy()
    expect(screen.getByLabelText('Dismiss card')).toBeTruthy()
  })
})
