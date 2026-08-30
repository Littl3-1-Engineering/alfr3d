import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SituationalAwareness from './SituationalAwareness'

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

  it('caps rendered cards at MAX_DISPLAY_CARDS (9) even if the backend sends more', async () => {
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

    expect(screen.queryAllByText(/^card \d+$/).length).toBe(9)
    expect(screen.queryByText('card 9')).toBeFalsy()
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
    expect(body).toEqual({ rule_id: 'weather', subject_key: '', action: 'shown' })
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
})
