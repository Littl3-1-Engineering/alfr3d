import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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
    expect(document.querySelector('.lucide-smile')).toBeTruthy()
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
})
