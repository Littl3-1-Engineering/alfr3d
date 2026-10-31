import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import SituationalAwareness from './SituationalAwareness'
import socket from '../utils/socket'

vi.mock('../utils/socket', () => ({
  default: {
    on: vi.fn(),
    off: vi.fn(),
  },
}))

const mockSaData = (mode) => ([
  { mode, content: `${mode} content`, priority: 1 },
])

describe('SituationalAwareness', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  const renderWithData = async (data) => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => data,
    })
    render(<SituationalAwareness />)
    await screen.findByText(`[${data[0].mode}]`)
  }

  it('renders the mood icon for the mood mode', async () => {
    await renderWithData(mockSaData('mood'))
    expect(document.querySelector('.lucide-face-slightly-smiling')).toBeTruthy()
  })

  it('renders the focus_needed icon with the alert color', async () => {
    await renderWithData(mockSaData('focus_needed'))
    const icon = document.querySelector('.lucide-phone-call')
    expect(icon).toBeTruthy()
    expect(icon).toHaveClass('text-fui-magenta')
  })

  it('renders the weather_advisory icon distinct from the plain weather icon', async () => {
    await renderWithData(mockSaData('weather_advisory'))
    const icon = document.querySelector('.lucide-cloud-rain')
    expect(icon).toBeTruthy()
    expect(icon).toHaveClass('text-fui-magenta')
    expect(document.querySelector('.lucide-thermometer')).toBeFalsy()
  })

  it('renders the travel icon for the travel mode', async () => {
    await renderWithData(mockSaData('travel'))
    expect(document.querySelector('.lucide-car')).toBeTruthy()
  })

  it('falls back to the default icon for an unrecognized mode', async () => {
    await renderWithData(mockSaData('some_future_mode'))
    const icon = document.querySelector('.lucide-thermometer')
    expect(icon).toBeTruthy()
    expect(icon).toHaveClass('text-error')
  })

  it('still renders the existing icons for time/weather/email/event/music', async () => {
    await renderWithData(mockSaData('email'))
    const icon = document.querySelector('.lucide-mail')
    expect(icon).toBeTruthy()
    expect(icon).toHaveClass('text-fui-accent')
  })

  it('renders the weather icon unchanged', async () => {
    await renderWithData(mockSaData('weather'))
    const icon = document.querySelector('.lucide-thermometer')
    expect(icon).toBeTruthy()
    expect(icon).toHaveClass('text-error')
  })

  it('shows the loading placeholder before any data has arrived', () => {
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {})) // never resolves
    render(<SituationalAwareness />)
    expect(screen.getByText('FETCHING DATA...')).toBeTruthy()
  })

  it('renders every card the backend sends -- no fixed frontend cap (backend already sliced)', async () => {
    const manyCards = Array.from({ length: 12 }, (_, i) => ({
      mode: 'weather',
      content: `card ${i}`,
      priority: i,
    }))
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => manyCards,
    })
    render(<SituationalAwareness />)
    await screen.findByText('card 0')

    expect(screen.queryAllByText(/^card \d+$/).length).toBe(12)
    expect(screen.queryByText('card 11')).toBeTruthy()
  })

  it('reports "shown" for every card the backend sends, not just the first N (SA-1)', async () => {
    const manyCards = Array.from({ length: 12 }, (_, i) => ({
      mode: 'weather',
      rule_id: 'weather',
      subject_key: `s${i}`,
      content: `card ${i}`,
      priority: i,
    }))
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => manyCards })
    render(<SituationalAwareness />)
    await screen.findByText('card 0')

    await waitFor(() => expect(interactionCalls().length).toBe(12))
  })

  it('renders distinct icons for the newer card modes', async () => {
    await renderWithData(mockSaData('wind_down_signal'))
    expect(document.querySelector('.lucide-moon')).toBeTruthy()
  })

  it('renders a playlist link for a music card carrying playlist fields', async () => {
    const data = [
      {
        mode: 'music',
        content: 'Play Indie Chill',
        priority: 3,
        playlist_name: 'Indie Chill',
        playlist_url: 'https://open.spotify.com/playlist/abc123',
        playlist_image: 'https://img.example.com/abc123.jpg',
      },
    ]
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => data,
    })
    render(<SituationalAwareness />)

    const link = await screen.findByRole('link', { name: /Indie Chill/ })
    expect(link).toHaveAttribute('href', 'https://open.spotify.com/playlist/abc123')
  })

  it('does not render a playlist link for a music card with no playlist_name', async () => {
    await renderWithData(mockSaData('music'))
    expect(screen.queryByRole('link')).toBeFalsy()
  })

  const interactionCalls = () =>
    globalThis.fetch.mock.calls.filter(([url]) => url.includes('/api/context/card-interaction'))

  it('reports "shown" for each rendered card (SA-1)', async () => {
    const data = [{ mode: 'weather', rule_id: 'weather', subject_key: '', content: 'sunny', priority: 5 }]
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => data })
    render(<SituationalAwareness />)
    await screen.findByText('sunny')

    await waitFor(() => expect(interactionCalls().length).toBe(1))
    const [, options] = interactionCalls()[0]
    const body = JSON.parse(options.body)
    expect(body).toMatchObject({ rule_id: 'weather', subject_key: '', action: 'shown', surface: 'web' })
    expect(body.impression_id).toMatch(/^[A-Za-z0-9-]{1,36}$/) // links this row to its display
  })

  it('falls back to `mode` as rule_id when a card predates SA-1 stamping', async () => {
    await renderWithData(mockSaData('weather'))

    await waitFor(() => expect(interactionCalls().length).toBe(1))
    const body = JSON.parse(interactionCalls()[0][1].body)
    expect(body.rule_id).toBe('weather')
  })

  it('dismissing a card hides it and reports "dismissed" (SA-1)', async () => {
    const data = [
      { mode: 'weather', rule_id: 'weather', subject_key: '', content: 'sunny', priority: 5 },
    ]
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => data })
    render(<SituationalAwareness />)
    await screen.findByText('sunny')

    fireEvent.click(screen.getByLabelText('Dismiss card'))

    expect(screen.queryByText('sunny')).toBeFalsy()
    await waitFor(() => {
      const dismissCall = interactionCalls().find(([, options]) => {
        const body = JSON.parse(options.body)
        return body.action === 'dismissed'
      })
      expect(dismissCall).toBeTruthy()
    })
  })

  it('does not offer a dismiss button for an urgent card', async () => {
    const data = [
      {
        mode: 'household_composition',
        rule_id: 'household_composition',
        subject_key: '',
        content: 'unrecognized device',
        priority: 2.3,
        urgent: true,
      },
    ]
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => data })
    render(<SituationalAwareness />)
    await screen.findByText('unrecognized device')

    expect(screen.queryByLabelText('Dismiss card')).toBeFalsy()
  })
  describe('impressions (how long a card was actually on screen)', () => {
    const card = { mode: 'weather', rule_id: 'weather', subject_key: '', content: 'sunny', priority: 5 }

    const bodies = (action) =>
      interactionCalls()
        .map(([, options]) => JSON.parse(options.body))
        .filter((body) => body.action === action)

    const pushToSocket = (data) => {
      const handler = socket.on.mock.calls.find(([event]) => event === 'situational_awareness')[1]
      act(() => handler(data))
    }

    let now
    beforeEach(() => {
      now = 1_000_000
      vi.spyOn(Date, 'now').mockImplementation(() => now)
    })

    const renderCard = async (data = [card]) => {
      globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => data })
      const view = render(<SituationalAwareness />)
      await screen.findByText(data[0].content)
      await waitFor(() => expect(bodies('shown').length).toBe(1))
      return view
    }

    it('dismissing ends the display: one impression with the visible time and the same id as shown', async () => {
      await renderCard()
      now += 5000

      fireEvent.click(screen.getByLabelText('Dismiss card'))

      await waitFor(() => expect(bodies('impression').length).toBe(1))
      const [impression] = bodies('impression')
      expect(impression).toMatchObject({ rule_id: 'weather', surface: 'web', visible_ms: 5000 })
      expect(impression.impression_id).toBe(bodies('shown')[0].impression_id)
      expect(bodies('dismissed')[0].impression_id).toBe(impression.impression_id)
    })

    it('a card leaving the payload ends its display', async () => {
      await renderCard()
      now += 12_000

      pushToSocket([])

      await waitFor(() => expect(bodies('impression').length).toBe(1))
      expect(bodies('impression')[0].visible_ms).toBe(12_000)
    })

    it('a card that stays in a refreshed payload keeps one display', async () => {
      await renderCard()
      now += 3000
      pushToSocket([{ ...card, content: 'still sunny' }])
      now += 3000

      expect(bodies('impression').length).toBe(0)
      pushToSocket([])
      await waitFor(() => expect(bodies('impression').length).toBe(1))
      expect(bodies('impression')[0].visible_ms).toBe(6000)
    })

    it('unmounting ends the display', async () => {
      const view = await renderCard()
      now += 4000

      view.unmount()

      expect(bodies('impression').length).toBe(1)
      expect(bodies('impression')[0].visible_ms).toBe(4000)
    })

    it('does not count time the tab was hidden', async () => {
      await renderCard()
      const setVisibility = (state) => {
        Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
        document.dispatchEvent(new Event('visibilitychange'))
      }
      now += 2000
      setVisibility('hidden')
      now += 60_000
      setVisibility('visible')
      now += 1000

      fireEvent.click(screen.getByLabelText('Dismiss card'))

      await waitFor(() => expect(bodies('impression').length).toBe(1))
      expect(bodies('impression')[0].visible_ms).toBe(3000)
    })

    it('does not report a display shorter than a second -- it was never really seen', async () => {
      await renderCard()
      now += 400

      fireEvent.click(screen.getByLabelText('Dismiss card'))

      await waitFor(() => expect(bodies('dismissed').length).toBe(1))
      expect(bodies('impression').length).toBe(0)
    })

    it('opening a music playlist is reported as a tap saying what it opened', async () => {
      const music = {
        mode: 'music', rule_id: 'music', subject_key: '', content: 'Play Indie Chill', priority: 3,
        playlist_name: 'Indie Chill', playlist_url: 'https://open.spotify.com/playlist/abc123',
      }
      await renderCard([music])

      fireEvent.click(screen.getByRole('link', { name: /Indie Chill/ }))

      await waitFor(() => expect(bodies('tapped').length).toBe(1))
      expect(bodies('tapped')[0]).toMatchObject({ rule_id: 'music', surface: 'web', detail: 'open playlist' })
      expect(bodies('tapped')[0].impression_id).toBe(bodies('shown')[0].impression_id)
    })
  })
})
