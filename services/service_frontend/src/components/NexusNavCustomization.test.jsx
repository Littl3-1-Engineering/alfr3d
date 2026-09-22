import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import NexusNavCustomization from './NexusNavCustomization'
import UiPrefsContext from '../utils/UiPrefsContext'
import ThemeContext from '../utils/ThemeContext'

// The ring previews are real HudRings, so they need a theme to read colours from.
const renderWithPrefs = (nexusNav, setNexusNav = () => {}) => render(
  <ThemeContext.Provider
    value={{
      currentTheme: 'dark',
      setCurrentTheme: () => {},
      toggleTheme: () => {},
      themeColors: { primary: '#06b6d4', secondary: '#ec4899', warning: '#eab308' },
      themes: {},
    }}
  >
    <UiPrefsContext.Provider value={{ nexusNav, setNexusNav }}>
      <NexusNavCustomization />
    </UiPrefsContext.Provider>
  </ThemeContext.Provider>
)

describe('NexusNavCustomization', () => {
  it('offers both ways of opening the Nexus panels', () => {
    renderWithPrefs('rings')
    expect(screen.getByText('Orbit Rings')).toBeInTheDocument()
    expect(screen.getByText('Edge Tabs')).toBeInTheDocument()
  })

  it('marks the saved mode as selected', () => {
    renderWithPrefs('tabs')
    expect(screen.getByText('Edge Tabs').closest('button')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Orbit Rings').closest('button')).toHaveAttribute('aria-pressed', 'false')
  })

  it('switches mode when a card is clicked', () => {
    const setNexusNav = vi.fn()
    renderWithPrefs('rings', setNexusNav)
    fireEvent.click(screen.getByText('Edge Tabs').closest('button'))
    expect(setNexusNav).toHaveBeenCalledWith('tabs')
  })
})
