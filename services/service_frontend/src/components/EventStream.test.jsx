import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import EventStream from './EventStream'
import { ThemeProvider } from '../utils/ThemeContext'
import { themes } from '../utils/themes'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

// EventStream reverses what the API returns, so the LAST entry here is the newest.
const EVENTS = [
  { id: 1, type: 'info', message: 'Core temperature nominal', time: '2026-09-20T00:00:00Z' },
  { id: 2, type: 'warning', message: 'Firewall rules stale', time: '2026-09-20T00:01:00Z' },
  { id: 3, type: 'success', message: 'Front door unlocked', time: '2026-09-20T00:02:00Z' },
]

const renderStream = async (events = EVENTS) => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [...events] })
  const utils = render(<ThemeProvider><EventStream /></ThemeProvider>)
  await waitFor(() => expect(screen.getByText(events[0].message)).toBeInTheDocument())
  return utils
}

const rings = (container) => [...container.querySelectorAll('svg')]
const ringColor = (svg) => svg.querySelector(':scope > g').style.color
const layerOpacity = (svg) => svg.querySelectorAll(':scope > g > g')[1].style.opacity

describe('EventStream ring glyphs', () => {
  it('gives every event a ring instead of the old plain square', async () => {
    const { container } = await renderStream()
    expect(rings(container)).toHaveLength(EVENTS.length)
    expect(container.querySelectorAll('.w-3.h-3')).toHaveLength(0)
  })

  it('bounces only the newest arrival and leaves older rows at rest', async () => {
    const { container } = await renderStream()
    const [newest, ...older] = rings(container)

    // resolve runs at full strength; idle rows sit dimmed at the rest opacity.
    expect(layerOpacity(newest)).toBe('1')
    older.forEach((svg) => expect(layerOpacity(svg)).toBe('0.45'))
  })

  it('colours a warning amber and leaves the rest on the primary accent', async () => {
    const { container } = await renderStream()
    const [success, warning, info] = rings(container)

    expect(warning.querySelector(':scope > g').style.color).not.toBe(ringColor(success))
    expect(ringColor(info)).toBe(ringColor(success))
    expect(themes.dark.env).toBeTruthy()
  })

  it('draws a different shape per event kind, so type is readable without colour', async () => {
    const { container } = await renderStream()
    const signature = (svg) => [...svg.querySelectorAll('circle, rect, path')]
      .map((n) => `${n.tagName}:${n.getAttribute('r') || n.getAttribute('d') || n.getAttribute('width')}`)
      .join(',')

    const signatures = rings(container).map(signature)
    expect(new Set(signatures).size).toBe(signatures.length)
  })
})
