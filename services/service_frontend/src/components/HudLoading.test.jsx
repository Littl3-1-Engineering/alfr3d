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

  it('uses the handshake ring for a fetch and the process ring for local work', () => {
    // The distinction is the whole point of the vocabulary: waiting on the other end
    // looks different from waiting on ourselves.
    const { container: fetching } = renderLoading({ mode: 'fetch' })
    const { container: computing } = renderLoading({ mode: 'compute' })

    // Split-Arc is arc rings only; Gear Dial adds a filled centre dot.
    expect(fetching.querySelectorAll('circle[fill="currentColor"]')).toHaveLength(0)
    expect(computing.querySelectorAll('circle[fill="currentColor"]').length).toBeGreaterThan(0)
  })

  it('keeps the ring out of the accessibility tree so the label is read once', () => {
    const { container } = renderLoading({ label: 'Loading events' })
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getAllByText('Loading events')).toHaveLength(1)
  })
})
