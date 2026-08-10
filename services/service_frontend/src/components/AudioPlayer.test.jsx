import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import AudioPlayer from './AudioPlayer'

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

describe('AudioPlayer', () => {
  beforeEach(() => {
    eventsHandler = null
    vi.useFakeTimers()
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true })
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  function stubMediaElement() {
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'load', {
      configurable: true,
      value: function load() {
        this.dispatchEvent(new Event('canplay'))
      },
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
      configurable: true,
      set: function set(src) {
        this._src = src
      },
      get() {
        return this._src || ''
      },
    })
  }

  const playOne = async () => {
    await vi.advanceTimersByTimeAsync(2000)
  }

  it('renders a hidden audio element and subscribes to socket events', () => {
    stubMediaElement()
    render(<AudioPlayer />)
    const audio = document.querySelector('audio')
    expect(audio).toBeTruthy()
    expect(audio.style.display).toBe('none')
    expect(eventsHandler).toBeTruthy()
  })

  it('queues audio events and plays them after user interaction', async () => {
    stubMediaElement()
    render(<AudioPlayer />)

    fireEvent.click(document.body)
    eventsHandler([{ type: 'audio', audio_url: '/audio/test.mp3' }])

    await playOne()

    const audio = document.querySelector('audio')
    expect(audio.src).toBe('http://localhost:3000/audio/test.mp3')
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/audio/test.mp3'),
      expect.objectContaining({ method: 'HEAD' }),
    )
  })

  it('dedupes identical audio events already in the queue', async () => {
    stubMediaElement()
    render(<AudioPlayer />)
    fireEvent.click(document.body)

    eventsHandler([{ type: 'audio', audio_url: '/audio/dup.mp3' }])
    eventsHandler([{ type: 'audio', audio_url: '/audio/dup.mp3' }])

    await playOne()

    const audio = document.querySelector('audio')
    expect(audio.src).toBe('http://localhost:3000/audio/dup.mp3')
  })

  it('ignores non-audio events', async () => {
    stubMediaElement()
    render(<AudioPlayer />)
    fireEvent.click(document.body)

    eventsHandler([{ type: 'text', message: 'hello' }])
    await playOne()

    const audio = document.querySelector('audio')
    expect(audio.src).toBe('')
  })

  it('does not autoplay before the user has interacted', async () => {
    stubMediaElement()
    render(<AudioPlayer />)

    eventsHandler([{ type: 'audio', audio_url: '/audio/nointeract.mp3' }])
    await playOne()

    const audio = document.querySelector('audio')
    expect(audio.src).toBe('')
  })
})
