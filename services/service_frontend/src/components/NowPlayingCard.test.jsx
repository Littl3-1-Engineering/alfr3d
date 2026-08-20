import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'
import NowPlayingCard from './NowPlayingCard'

let eventsHandler = null

vi.mock('../utils/socket', () => ({
  default: {
    on: vi.fn((event, cb) => {
      eventsHandler = cb
      return () => {}
    }),
    off: vi.fn(),
  },
}))

const playingEvent = {
  type: 'audio',
  message: 'playing song: Song One by Artist A',
  track: {
    id: 't1',
    name: 'Song One',
    artists: ['Artist A'],
    album: 'Album One',
    album_art: 'http://img/art.jpg',
    duration_ms: 180000,
    uri: 'spotify:track:t1',
    progress_ms: 5000,
  },
  is_playing: true,
}

describe('NowPlayingCard', () => {
  beforeEach(() => {
    eventsHandler = null
    vi.useFakeTimers()
    globalThis.fetch = vi.fn()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  const fetchStatus = (body) => {
    globalThis.fetch.mockResolvedValue({ ok: true, json: async () => body })
  }

  it('renders nothing when Spotify is not playing', async () => {
    fetchStatus({ is_playing: false, item: null, progress_ms: 0 })
    const { container } = render(<NowPlayingCard />)
    await act(async () => {})
    expect(container.firstChild).toBeNull()
  })

  it('renders the track once a music event arrives', async () => {
    fetchStatus({ is_playing: false, item: null, progress_ms: 0 })
    const { getByText } = render(<NowPlayingCard />)

    act(() => {
      eventsHandler([playingEvent])
    })

    expect(getByText('Song One')).toBeTruthy()
    expect(getByText('Artist A')).toBeTruthy()
    expect(getByText('Album One')).toBeTruthy()
  })

  it('initializes from the mount fetch when a track is already playing', async () => {
    fetchStatus({
      is_playing: true,
      progress_ms: 1000,
      item: playingEvent.track,
    })
    const { getByText } = render(<NowPlayingCard />)
    await act(async () => {})

    expect(getByText('Song One')).toBeTruthy()
  })

  it('hides the card when playback stops', async () => {
    fetchStatus({ is_playing: false, item: null, progress_ms: 0 })
    const { getByText, container } = render(<NowPlayingCard />)

    act(() => {
      eventsHandler([playingEvent])
    })
    expect(getByText('Song One')).toBeTruthy()

    act(() => {
      eventsHandler([{ type: 'audio', message: 'playback stopped', track: null, is_playing: false }])
    })
    expect(container.firstChild).toBeNull()
  })

  it('ignores non-music events', async () => {
    fetchStatus({ is_playing: false, item: null, progress_ms: 0 })
    const { container } = render(<NowPlayingCard />)

    eventsHandler([{ type: 'info', message: 'hello', time: 'now' }])

    expect(container.firstChild).toBeNull()
  })
})
