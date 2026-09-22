import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Matrix from './Matrix'
import { ThemeProvider } from '../utils/ThemeContext'
import { UiPrefsProvider } from '../utils/UiPrefsContext'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

const openCustomizations = async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
  const utils = render(<ThemeProvider><UiPrefsProvider><Matrix /></UiPrefsProvider></ThemeProvider>)
  fireEvent.click(screen.getByRole('button', { name: /customizations/i }))
  await waitFor(() => expect(screen.getByText('HUD Rings')).toBeInTheDocument())
  return utils
}

describe('Matrix ring gallery', () => {
  it('documents the whole vocabulary, so the shapes are discoverable', async () => {
    await openCustomizations()
    const names = ['Compass', 'Split-Arc', 'Gear Dial', 'Scanner Arc', 'Sensor Ring', 'Node Ring', 'Quad Reticle', 'Iris Ring']
    names.forEach((name) => expect(screen.getByText(name)).toBeInTheDocument())
  })

  it('spells out which shapes carry a meaning and which only tell choices apart', async () => {
    await openCustomizations()
    expect(screen.getByText('Acquire / lock')).toBeInTheDocument()
    expect(screen.getByText('Handshake / sync')).toBeInTheDocument()
    expect(screen.getByText('Process / compute')).toBeInTheDocument()
    expect(screen.getAllByText('Identity')).toHaveLength(5)
  })

  it('shows every state the ring can be in', async () => {
    await openCustomizations()
    ;['idle', 'working', 'resolve', 'active', 'fault'].forEach((state) => {
      expect(screen.getByText(state)).toBeInTheDocument()
    })
  })

  it('credits the original design where a reader will actually see it', async () => {
    await openCustomizations()
    expect(screen.getByText(/Goran Spasojevic/)).toBeInTheDocument()
    expect(screen.getByText(/codepen\.io\/gorango/)).toBeInTheDocument()
  })
})
