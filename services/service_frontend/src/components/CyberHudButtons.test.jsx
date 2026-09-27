import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CyberHudButtons from './CyberHudButtons'
import { ThemeProvider } from '../utils/ThemeContext'

const renderButtons = () =>
  render(
    <ThemeProvider>
      <CyberHudButtons />
    </ThemeProvider>,
  )

describe('CyberHudButtons', () => {
  it('renders both component boards, all 8 shapes, as real buttons', () => {
    renderButtons()
    expect(screen.getByText('Component · 3 Recreations & Bounce')).toBeInTheDocument()
    expect(screen.getByText('Component · 5 New Recreations')).toBeInTheDocument()

    const labels = ['Compass Ring', 'Split-Arc Ring', 'Gear Dial', 'Scanner Arc', 'Sensor Ring', 'Node Ring', 'Quad Reticle', 'Iris Ring']
    labels.forEach((label) => expect(screen.getByRole('button', { name: label })).toBeInTheDocument())
  })

  it('toggles a button to active on click, and back on a second click', () => {
    renderButtons()
    const button = screen.getByRole('button', { name: 'Compass Ring' })

    expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'false')
  })

  it('names each button\'s gorango origin', () => {
    renderButtons()
    expect(screen.getByText('recreated from #b1')).toBeInTheDocument()
    expect(screen.getByText('recreated from #b9')).toBeInTheDocument()
  })
})
