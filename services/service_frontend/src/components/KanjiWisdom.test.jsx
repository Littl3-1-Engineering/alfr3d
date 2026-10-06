import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import KanjiWisdom from './KanjiWisdom'
import UiPrefsContext from '../utils/UiPrefsContext'
import { KANJI_SCRAMBLE_STEPS, KANJI_SCRAMBLE_STEP_MS, KANJI_REPLAY_MS } from '../utils/kanjiWisdom'

let mockData = null
vi.mock('../hooks/useApi', () => ({ useKanjiToday: () => ({ data: mockData }) }))

const QUOTE = {
  date: '2026-10-06',
  id: 6,
  kanji: '継続は力なり',
  reading: 'keizoku wa chikara nari',
  meaning: 'continuing is power',
}

const renderOverlay = (kanjiWisdom = true) =>
  render(
    <UiPrefsContext.Provider value={{ nexusNav: 'rings', setNexusNav: () => {}, kanjiWisdom, setKanjiWisdom: () => {} }}>
      <KanjiWisdom />
    </UiPrefsContext.Provider>
  )

const decode = () => act(() => vi.advanceTimersByTime(KANJI_SCRAMBLE_STEPS * KANJI_SCRAMBLE_STEP_MS))

describe('KanjiWisdom', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockData = QUOTE
  })
  afterEach(() => vi.useRealTimers())

  it('shows the kanji with its reading and meaning, and describes them for assistive tech', () => {
    renderOverlay()
    decode()
    expect(screen.getByTestId('kanji-wisdom-kanji')).toHaveTextContent('継続は力なり')
    expect(screen.getByText('keizoku wa chikara nari')).toBeInTheDocument()
    expect(screen.getByText('continuing is power')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      '継続は力なり, keizoku wa chikara nari: continuing is power'
    )
  })

  it('is not interactive', () => {
    renderOverlay()
    expect(screen.getByTestId('kanji-wisdom').className).toContain('pointer-events-none')
  })

  it('scrambles on appear, then resolves to the real text', () => {
    renderOverlay()
    // First frame is noise: same length, none of the real characters revealed yet.
    const first = screen.getByTestId('kanji-wisdom-kanji').textContent
    expect(Array.from(first)).toHaveLength(6)
    expect(first).not.toBe('継続は力なり')
    decode()
    expect(screen.getByTestId('kanji-wisdom-kanji')).toHaveTextContent('継続は力なり')
  })

  it('scrambles again after the replay interval', () => {
    renderOverlay()
    decode()
    expect(screen.getByTestId('kanji-wisdom-kanji')).toHaveTextContent('継続は力なり')
    act(() => vi.advanceTimersByTime(KANJI_REPLAY_MS))
    expect(screen.getByTestId('kanji-wisdom-kanji').textContent).not.toBe('継続は力なり')
    decode()
    expect(screen.getByTestId('kanji-wisdom-kanji')).toHaveTextContent('継続は力なり')
  })

  it('renders nothing when switched off', () => {
    renderOverlay(false)
    expect(screen.queryByTestId('kanji-wisdom')).not.toBeInTheDocument()
  })

  it('renders nothing when the backend has no quote', () => {
    mockData = undefined
    renderOverlay()
    expect(screen.queryByTestId('kanji-wisdom')).not.toBeInTheDocument()
  })
})
