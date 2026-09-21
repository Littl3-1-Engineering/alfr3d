import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import HudRing from './HudRing'
import { ThemeProvider } from '../utils/ThemeContext'

// matchMedia (which framer-motion's useReducedMotion needs) is polyfilled in test/setup.js.

const renderRing = (props = {}) =>
  render(
    <ThemeProvider>
      <HudRing {...props} />
    </ThemeProvider>,
  )

describe('HudRing', () => {
  it('renders a real button, not a clickable div, when given onClick', () => {
    const onClick = vi.fn()
    renderRing({ onClick, label: 'Weather' })

    const button = screen.getByRole('button', { name: 'Weather' })
    fireEvent.click(button)

    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('exposes selection state to assistive tech via aria-pressed', () => {
    const { rerender } = renderRing({ onClick: () => {}, label: 'Weather' })
    expect(screen.getByRole('button', { name: 'Weather' })).toHaveAttribute('aria-pressed', 'false')

    rerender(
      <ThemeProvider>
        <HudRing onClick={() => {}} label="Weather" state="active" />
      </ThemeProvider>,
    )
    expect(screen.getByRole('button', { name: 'Weather' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('is an labelled image when used as an indicator', () => {
    renderRing({ label: 'ALFR3D reachable', shape: 'splitArc', state: 'working' })
    expect(screen.getByRole('img', { name: 'ALFR3D reachable' })).toBeInTheDocument()
  })

  it('hides itself from assistive tech when it is purely decorative', () => {
    const { container } = renderRing({ shape: 'gear' })
    expect(screen.queryByRole('img')).toBeNull()
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument()
  })

  it('shows the corner-bracket selection frame only in the active state', () => {
    const { rerender } = renderRing({ shape: 'compass' })
    expect(screen.queryByTestId('hud-ring-brackets')).toBeNull()

    rerender(
      <ThemeProvider>
        <HudRing shape="compass" state="active" />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('hud-ring-brackets')).toBeInTheDocument()
  })

  it('renders every shape in every state without throwing', () => {
    const shapes = ['compass', 'splitArc', 'gear', 'scanner', 'sensor', 'node', 'reticle', 'iris']
    const states = ['idle', 'working', 'resolve', 'active', 'fault']

    shapes.forEach((shape) => {
      states.forEach((state) => {
        const { container, unmount } = renderRing({ shape, state })
        expect(container.querySelector('svg')).toBeInTheDocument()
        unmount()
      })
    })
  })

  // The bug this guards against is the whole reason the drift tier exists: the first
  // version animated only in `working`/`resolve`, so every ring on a settled screen — which
  // is nearly all of them, nearly all of the time — sat frozen and read as a flat icon.
  // The layer carries a plain SVG transform attribute, stated in viewBox units — see
  // HudRing.jsx on why Framer Motion is not allowed to own it.
  const transformOf = (container, key) =>
    container.querySelector(`[data-testid="hud-ring-layer-${key}"]`).getAttribute('transform')

  const drifts = async (state) => {
    const { container, unmount } = renderRing({ shape: 'splitArc', state })
    const before = transformOf(container, 'inner')
    await waitFor(
      () => expect(transformOf(container, 'inner')).not.toBe(before),
      { timeout: 2000 },
    )
    unmount()
  }

  it('keeps turning at rest, so an idle ring never reads as a static icon', async () => {
    await drifts('idle')
  })

  it('keeps turning while selected', async () => {
    await drifts('active')
  })

  it('counter-rotates its two layers at rest, not just one of them', async () => {
    const { container } = renderRing({ shape: 'splitArc', state: 'idle' })

    await waitFor(() => {
      const inner = transformOf(container, 'inner')
      const outer = transformOf(container, 'outer')
      expect(inner).toMatch(/rotate\(-\d/)
      expect(outer).toMatch(/rotate\(\d*\.?\d*[1-9]/)
      expect(inner).not.toBe(outer)
    }, { timeout: 2000 })
  })

  it('freezes only on a fault', async () => {
    const { container } = renderRing({ shape: 'splitArc', state: 'fault' })
    // Past the 350ms park, both layers must be holding a fixed angle.
    await waitFor(
      () => expect(transformOf(container, 'inner')).toMatch(/rotate\(-137\.000\b/),
      { timeout: 2000 },
    )
    const parked = transformOf(container, 'inner')
    await new Promise((resolve) => setTimeout(resolve, 250))
    expect(transformOf(container, 'inner')).toBe(parked)
  })

  it('falls back to the compass shape rather than crashing on an unknown shape', () => {
    const { container } = renderRing({ shape: 'not-a-shape' })
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('scales the artwork to the requested size', () => {
    const { container } = renderRing({ size: 64 })
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '64')
    expect(svg).toHaveAttribute('viewBox', '0 0 100 100')
  })
})
