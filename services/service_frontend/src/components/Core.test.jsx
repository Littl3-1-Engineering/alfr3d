import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import Core from './Core'
import { ThemeProvider } from '../utils/ThemeContext'
import { themes } from '../utils/themes'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

const USERS = [
  { name: 'Alice', type: 'resident', state: 'online' },
  { name: 'Bob', type: 'guest', state: 'online' },
]
const DEVICES = [
  { id: 1, name: 'hallway-pi', type: 'sensor', user: 'alfr3d', state: 'online' },
  { id: 2, name: 'garage-pi', type: 'sensor', user: 'alfr3d', state: 'offline' },
]
const CONTAINERS = [
  { name: 'service_api', state: 'running', health: 'healthy', restarts: 0 },
  { name: 'service_daemon', state: 'running', health: 'starting', restarts: 0 },
  { name: 'service_device', state: 'exited', health: 'none', restarts: 4 },
]

const LAUNCHERS = [
  { id: 'favorites', label: 'Quick Controls', shape: 'splitArc', isOpen: false, onToggle: () => {} },
  { id: 'weather', label: 'Weather', shape: 'scanner', isOpen: false, onToggle: () => {} },
  { id: 'camera', label: 'Camera', shape: 'iris', isOpen: true, onToggle: () => {} },
]

const renderCore = async (launchers = []) => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
  const utils = render(
    <ThemeProvider>
      <Core
        initialUsers={USERS}
        initialDevices={DEVICES}
        initialContainers={CONTAINERS}
        launchers={launchers}
      />
    </ThemeProvider>,
  )
  // Orbit satellites are plain dots with no accessible role of their own (see below), so
  // readiness is a DOM query rather than an accessible one: wait for the user orbit to have
  // placed its dots.
  await waitFor(() => expect(orbitDots(utils.container).users).toHaveLength(USERS.length))
  return utils
}

// Orbit satellites went back to being bare coloured dots (see Core.jsx) after the animated
// HudRing per-satellite treatment they briefly had turned out to look wrong for a field of
// many small orbiting things -- the ring's per-shape silhouette is worth it for the handful
// of launcher buttons, but not for every user/device/container dot circling the Core.
//
// The three orbits are indistinguishable by class name (each is a `motion.div` with the
// same `absolute top-0 left-0 w-full h-full`/`z-index: 10` styling) and sit alongside two
// more z-index-10 orbits (Sun, Moon) plus a z-index-20 launcher ring, so dots are found by
// walking to the Nth such wrapper in DOM order -- fixed by the source's own JSX order
// (users, then devices, then containers, then the launcher ring, then Sun, then Moon) --
// rather than by a selector that would also match those other rings.
const orbitDots = (container) => {
  const rings = [...container.querySelectorAll('div')]
    .filter((el) => (el.getAttribute('style') || '').includes('z-index: 10'))
  const dotsIn = (ring) => (ring ? [...ring.querySelectorAll(':scope > div')] : [])
  return { users: dotsIn(rings[0]), devices: dotsIn(rings[1]), containers: dotsIn(rings[2]) }
}

// jsdom normalises whatever colour it is given (the theme mixes hsl() and hex), so push the
// expected token through the same CSSOM rather than string-matching the raw token.
const asRendered = (cssColor) => {
  const probe = document.createElement('span')
  probe.style.color = cssColor
  return probe.style.color
}
const colorOf = (dot) => asRendered(dot.style.backgroundColor)

describe('Core orbit rings', () => {
  it('renders one dot per orbiting user, device and container', async () => {
    const { container } = await renderCore()
    const dots = orbitDots(container)
    expect(dots.users).toHaveLength(USERS.length)
    expect(dots.devices).toHaveLength(DEVICES.length)
    expect(dots.containers).toHaveLength(CONTAINERS.length)
  })

  it('marks a guest apart from a resident by colour alone', async () => {
    const { container } = await renderCore()
    const [alice, bob] = orbitDots(container).users // USERS[0] is Alice (resident), [1] Bob (guest)
    expect(colorOf(alice)).toBe(asRendered(themes.dark.success))
    expect(colorOf(bob)).toBe(asRendered(themes.dark.warning))
    expect(colorOf(alice)).not.toBe(colorOf(bob))
  })

  it('shows an unreachable device amber and a reachable one green', async () => {
    const { container } = await renderCore()
    const [hallwayPi, garagePi] = orbitDots(container).devices // online, then offline
    expect(colorOf(hallwayPi)).toBe(asRendered(themes.dark.success))
    expect(colorOf(garagePi)).toBe(asRendered(themes.dark.warning))
  })

  it('separates a warning container from a critical one by both colour and size', async () => {
    const { container } = await renderCore()
    const [healthy, warning, critical] = orbitDots(container).containers

    expect(colorOf(healthy)).toBe(asRendered(themes.dark.success))
    expect(colorOf(warning)).toBe(asRendered(themes.dark.warning))
    expect(colorOf(critical)).toBe(asRendered(themes.dark.error))
    // Size climbs with severity too, so a single critical container's dot reads as
    // "worse" even before its colour is parsed.
    expect(parseFloat(warning.style.width)).toBeGreaterThan(parseFloat(healthy.style.width))
    expect(parseFloat(critical.style.width)).toBeGreaterThan(parseFloat(warning.style.width))
  })
})

describe('Core launcher ring', () => {
  it('offers every panel as a real button, not a vertical strip of text', async () => {
    await renderCore(LAUNCHERS)
    expect(screen.getByRole('button', { name: 'Open Quick Controls' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Weather' })).toBeInTheDocument()
    // An open panel's launcher offers to close it, so the label tracks what the click does.
    expect(screen.getByRole('button', { name: 'Close Camera' })).toBeInTheDocument()
  })

  it('toggles the panel it belongs to', async () => {
    const onToggle = vi.fn()
    await renderCore([{ ...LAUNCHERS[0], onToggle }])
    fireEvent.click(screen.getByRole('button', { name: 'Open Quick Controls' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('doubles as a taskbar: an open panel keeps its node selected', async () => {
    await renderCore(LAUNCHERS)
    const open = screen.getByRole('button', { name: 'Close Camera' })
    const shut = screen.getByRole('button', { name: 'Open Weather' })

    expect(open).toHaveAttribute('aria-pressed', 'true')
    expect(shut).toHaveAttribute('aria-pressed', 'false')
    // The corner-bracket frame is the visual half of the same signal.
    expect(within(open).queryByTestId('hud-ring-brackets')).toBeInTheDocument()
    expect(within(shut).queryByTestId('hud-ring-brackets')).toBeNull()
  })

  it('gives each launcher its own silhouette, so the ring is learnable without labels', async () => {
    const { container } = await renderCore(LAUNCHERS)
    const shapes = LAUNCHERS.map(({ label, isOpen }) => {
      const button = screen.getByRole('button', { name: `${isOpen ? 'Close' : 'Open'} ${label}` })
      return [...button.querySelectorAll('circle, rect, path')]
        .map((n) => `${n.tagName}:${n.getAttribute('r') || n.getAttribute('d') || n.getAttribute('width')}`)
        .join(',')
    })
    expect(new Set(shapes).size).toBe(shapes.length)
    expect(container).toBeTruthy()
  })
})
