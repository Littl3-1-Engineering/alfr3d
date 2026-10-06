import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import KanjiWisdomCustomization from './KanjiWisdomCustomization'
import UiPrefsContext from '../utils/UiPrefsContext'

const renderWith = (kanjiWisdom, setKanjiWisdom = () => {}) =>
  render(
    <UiPrefsContext.Provider value={{ nexusNav: 'rings', setNexusNav: () => {}, kanjiWisdom, setKanjiWisdom }}>
      <KanjiWisdomCustomization />
    </UiPrefsContext.Provider>
  )

describe('KanjiWisdomCustomization', () => {
  it('reflects the current state on the switch', () => {
    renderWith(true)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('Shown')).toBeInTheDocument()
  })

  it('shows hidden when off', () => {
    renderWith(false)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Hidden')).toBeInTheDocument()
  })

  it('toggles the preference on click', () => {
    const setKanjiWisdom = vi.fn()
    renderWith(true, setKanjiWisdom)
    fireEvent.click(screen.getByRole('switch'))
    expect(setKanjiWisdom).toHaveBeenCalledWith(false)
  })
})
