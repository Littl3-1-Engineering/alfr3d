import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import HudRing from './HudRing'
import { ThemeProvider } from '../utils/ThemeContext'

// Its own file because framer-motion resolves the reduced-motion media query once, globally,
// on first use — patching `window.matchMedia` inside a test that runs after any other render
// is simply ignored. Mocking the hook is the only way to exercise the branch in isolation.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion')
  return { ...actual, useReducedMotion: () => true }
})

describe('HudRing under prefers-reduced-motion', () => {
  const transformOf = (container, key) =>
    container.querySelector(`[data-testid="hud-ring-layer-${key}"]`).getAttribute('transform')

  // A hard stop, not a slower loop: the drift tier means every other state is in motion, so
  // this branch is the only thing standing between the setting and a screen full of it.
  it('holds every layer still, in the state that moves most', async () => {
    const { container } = render(
      <ThemeProvider>
        <HudRing shape="splitArc" state="working" />
      </ThemeProvider>,
    )

    // The identity transform, and it has to still be the identity a beat later — a drift
    // would have accumulated a visible angle by then.
    const identity = 'translate(50 50) rotate(0.000) scale(1.0000) translate(-50 -50)'
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(['inner', 'outer'].map((key) => transformOf(container, key))).toEqual([identity, identity])

    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(['inner', 'outer'].map((key) => transformOf(container, key))).toEqual([identity, identity])
  })

  it('still carries state through the bracket frame rather than through motion', () => {
    const { container } = render(
      <ThemeProvider>
        <HudRing shape="compass" state="active" />
      </ThemeProvider>,
    )
    expect(container.querySelector('[data-testid="hud-ring-brackets"]')).toBeInTheDocument()
  })
})
