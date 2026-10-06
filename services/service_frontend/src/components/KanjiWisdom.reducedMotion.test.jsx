import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import KanjiWisdom from './KanjiWisdom'
import UiPrefsContext from '../utils/UiPrefsContext'

// Own file for the same reason as HudRing.reducedMotion.test.jsx: framer-motion resolves the
// media query once, globally, so the hook has to be mocked to exercise this branch alone.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion')
  return { ...actual, useReducedMotion: () => true }
})
vi.mock('../hooks/useApi', () => ({
  useKanjiToday: () => ({
    data: { date: '2026-10-06', id: 1, kanji: '七転八起', reading: 'nanakorobi yaoki', meaning: 'rise' },
  }),
}))

describe('KanjiWisdom under prefers-reduced-motion', () => {
  it('shows the plain text from the first frame, with no scramble', () => {
    render(
      <UiPrefsContext.Provider value={{ nexusNav: 'rings', setNexusNav: () => {}, kanjiWisdom: true, setKanjiWisdom: () => {} }}>
        <KanjiWisdom />
      </UiPrefsContext.Provider>
    )
    expect(screen.getByTestId('kanji-wisdom-kanji')).toHaveTextContent('七転八起')
  })
})
