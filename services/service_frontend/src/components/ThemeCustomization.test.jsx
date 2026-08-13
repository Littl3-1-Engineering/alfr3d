import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ThemeCustomization from './ThemeCustomization'
import ThemeContext from '../utils/ThemeContext'

const renderWithTheme = (currentTheme, setCurrentTheme) => {
  return render(
    <ThemeContext.Provider
      value={{
        currentTheme,
        setCurrentTheme,
        toggleTheme: () => {},
        themeColors: {},
        themes: {},
      }}
    >
      <ThemeCustomization />
    </ThemeContext.Provider>
  )
}

describe('ThemeCustomization', () => {
  it('renders all three theme options', () => {
    renderWithTheme('dark', () => {})
    expect(screen.getByText('Cyan / Navy')).toBeInTheDocument()
    expect(screen.getByText('Amber / Charcoal')).toBeInTheDocument()
    expect(screen.getByText('Light / Teal')).toBeInTheDocument()
  })

  it('marks the active theme as selected', () => {
    renderWithTheme('amber', () => {})
    const amber = screen.getByText('Amber / Charcoal').closest('button')
    expect(amber).toHaveAttribute('aria-pressed', 'true')
  })

  it('switches theme when a card is clicked', () => {
    const setCurrentTheme = vi.fn()
    renderWithTheme('dark', setCurrentTheme)
    fireEvent.click(screen.getByText('Light / Teal').closest('button'))
    expect(setCurrentTheme).toHaveBeenCalledWith('light')
  })
})
