import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import FavoriteDeviceTile from './FavoriteDeviceTile'
import { ThemeProvider } from '../utils/ThemeContext'
import { themes } from '../utils/themes'

const device = (over = {}) => ({
  id: 7,
  name: 'Kitchen Ceiling',
  device_type: 'light',
  online: true,
  last_state: { state: 'off', attributes: {} },
  ...over,
})

const renderTile = (over) => render(
  <ThemeProvider>
    <FavoriteDeviceTile device={device(over)} canControl />
  </ThemeProvider>,
)

const toneOf = (el) => el.querySelector('svg > g').style.color
const asRendered = (cssColor) => {
  const probe = document.createElement('span')
  probe.style.color = cssColor
  return probe.style.color
}

describe('FavoriteDeviceTile state ring', () => {
  it('keeps the type icon and adds a ring, so kind and condition are both readable', () => {
    const { container } = renderTile()
    // lucide renders an svg with a lucide-* class; the ring is the labelled one.
    expect(container.querySelector('svg.lucide')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Kitchen Ceiling/ })).toBeInTheDocument()
  })

  it('reads an offline device as stalled, in the alert tone', () => {
    renderTile({ online: false })
    const ring = screen.getByRole('img', { name: 'Kitchen Ceiling: offline' })
    expect(toneOf(ring)).toBe(asRendered(themes.dark.env))
  })

  it('holds the selected frame while the device is on', () => {
    renderTile({ last_state: { state: 'on', attributes: {} } })
    const ring = screen.getByRole('img', { name: 'Kitchen Ceiling: active' })
    expect(toneOf(ring)).toBe(asRendered(themes.dark.magenta))
    expect(ring.querySelector('[data-testid="hud-ring-brackets"]')).toBeInTheDocument()
  })

  it('sits idle on the accent when the device is reachable but off', () => {
    renderTile()
    const ring = screen.getByRole('img', { name: 'Kitchen Ceiling: idle' })
    expect(toneOf(ring)).toBe(asRendered(themes.dark.primary))
    expect(ring.querySelector('[data-testid="hud-ring-brackets"]')).toBeNull()
  })

  it('gives a lock its own silhouette, distinct from a light', () => {
    const { container: lightTile } = renderTile()
    const { container: lockTile } = render(
      <ThemeProvider>
        <FavoriteDeviceTile device={device({ device_type: 'lock', last_state: { state: 'unlocked', attributes: {} } })} canControl />
      </ThemeProvider>,
    )
    const signature = (root) => [...root.querySelectorAll('[role="img"] circle, [role="img"] rect')]
      .map((n) => `${n.tagName}:${n.getAttribute('r') || n.getAttribute('width')}`)
      .join(',')
    expect(signature(lightTile)).not.toBe(signature(lockTile))
  })
})
