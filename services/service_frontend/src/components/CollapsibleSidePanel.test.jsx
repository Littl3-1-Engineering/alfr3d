import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CollapsibleSidePanel from './CollapsibleSidePanel'

const renderPanel = (props = {}) => render(
  <CollapsibleSidePanel position="left" title="W3ATH3R" isOpen onClose={() => {}} {...props}>
    <p>panel body</p>
  </CollapsibleSidePanel>,
)

const renderWithTab = (props = {}) => renderPanel({ showTab: true, onToggle: () => {}, ...props })

describe('CollapsibleSidePanel', () => {
  it('renders no vertical edge tab by default', () => {
    // The launcher ring around the Core is the default way in.
    const { container } = renderPanel()
    expect(container.querySelector('[style*="vertical-rl"]')).toBeNull()
  })

  it('carries its own close control, since the launcher ring leaves no other way out', () => {
    const onClose = vi.fn()
    renderPanel({ onClose })
    fireEvent.click(screen.getByRole('button', { name: 'Close W3ATH3R' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape, for when a wide panel covers the launcher that opened it', () => {
    const onClose = vi.fn()
    renderPanel({ onClose })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not listen for Escape while closed', () => {
    const onClose = vi.fn()
    renderPanel({ onClose, isOpen: false })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('stacks by slot, the offset the old tabIndex prop used to carry', () => {
    const { container } = renderPanel({ slot: 2 })
    expect(container.querySelector('.absolute')).toHaveStyle({ top: '440px' })
  })

  describe('tabs mode', () => {
    it('renders the vertical edge tab, labelled with the panel title', () => {
      const { container } = renderWithTab()
      expect(container.querySelector('[style*="vertical-rl"]')).toHaveTextContent('W3ATH3R')
    })

    it('ignores showTab with no onToggle, since a tab that opens nothing is a trap', () => {
      const { container } = renderPanel({ showTab: true })
      expect(container.querySelector('[style*="vertical-rl"]')).toBeNull()
    })

    it('toggles from the tab rather than only closing', () => {
      const onToggle = vi.fn()
      renderWithTab({ isOpen: false, onToggle })
      fireEvent.click(screen.getByRole('button', { name: 'W3ATH3R' }))
      expect(onToggle).toHaveBeenCalledTimes(1)
    })

    it('reports its open state on the tab rather than renaming it', () => {
      // Two buttons both called "Close W3ATH3R" would be ambiguous, so the tab keeps the
      // bare title and leaves that name to the corner close control.
      renderWithTab()
      expect(screen.getByRole('button', { name: 'W3ATH3R' })).toHaveAttribute('aria-expanded', 'true')
      expect(screen.getByRole('button', { name: 'Close W3ATH3R' })).toBeInTheDocument()
    })

    it('stacks tabs on a tighter pitch than the panels they open', () => {
      renderWithTab({ slot: 2 })
      expect(screen.getByRole('button', { name: 'W3ATH3R' })).toHaveStyle({ top: '400px' })
    })
  })
})
