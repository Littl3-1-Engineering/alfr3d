import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UiPrefsProvider } from './UiPrefsContext'
import { useUiPrefs } from './useUiPrefs'

const Probe = () => {
  const { nexusNav, setNexusNav } = useUiPrefs()
  return (
    <button type="button" onClick={() => setNexusNav('tabs')}>{nexusNav}</button>
  )
}

const renderProbe = () => render(<UiPrefsProvider><Probe /></UiPrefsProvider>)

describe('UiPrefsProvider', () => {
  beforeEach(() => localStorage.clear())

  it('defaults to the launcher rings', () => {
    renderProbe()
    expect(screen.getByRole('button')).toHaveTextContent('rings')
  })

  it('restores a saved mode', () => {
    localStorage.setItem('alfr3d-nexus-nav', 'tabs')
    renderProbe()
    expect(screen.getByRole('button')).toHaveTextContent('tabs')
  })

  it('falls back to the default for a value it does not recognise', () => {
    localStorage.setItem('alfr3d-nexus-nav', 'buttons')
    renderProbe()
    expect(screen.getByRole('button')).toHaveTextContent('rings')
  })

  it('persists a change', () => {
    renderProbe()
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveTextContent('tabs')
    expect(localStorage.getItem('alfr3d-nexus-nav')).toBe('tabs')
  })

  describe('kanji wisdom switch', () => {
    const KanjiProbe = () => {
      const { kanjiWisdom, setKanjiWisdom } = useUiPrefs()
      return (
        <button type="button" onClick={() => setKanjiWisdom(!kanjiWisdom)}>{String(kanjiWisdom)}</button>
      )
    }
    const renderKanji = () => render(<UiPrefsProvider><KanjiProbe /></UiPrefsProvider>)

    it('is on by default', () => {
      renderKanji()
      expect(screen.getByRole('button')).toHaveTextContent('true')
    })

    it('restores a saved off state', () => {
      localStorage.setItem('alfr3d-kanji-wisdom', 'false')
      renderKanji()
      expect(screen.getByRole('button')).toHaveTextContent('false')
    })

    it('persists a change', () => {
      renderKanji()
      fireEvent.click(screen.getByRole('button'))
      expect(localStorage.getItem('alfr3d-kanji-wisdom')).toBe('false')
    })
  })
})
