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
})
