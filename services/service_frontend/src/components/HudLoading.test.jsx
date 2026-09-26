import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import HudLoading from './HudLoading'
import { ThemeProvider } from '../utils/ThemeContext'

const renderLoading = (props = {}) =>
  render(
    <ThemeProvider>
      <HudLoading {...props} />
    </ThemeProvider>,
  )

describe('HudLoading', () => {
  it('announces itself as a live region rather than being a silent spinner', () => {
    renderLoading({ label: 'Loading routines' })
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('Loading routines')
  })

  it('always renders the Gear Dial ring, regardless of caller', () => {
    // The generic loader is one shape now — Gear Dial adds a filled centre dot that
    // Split-Arc (arc rings only) never does.
    const { container } = renderLoading({ label: 'Loading anything' })
    expect(container.querySelectorAll('circle[fill="currentColor"]').length).toBeGreaterThan(0)
  })

  it('keeps the ring out of the accessibility tree so the label is read once', () => {
    const { container } = renderLoading({ label: 'Loading events' })
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getAllByText('Loading events')).toHaveLength(1)
  })
})
