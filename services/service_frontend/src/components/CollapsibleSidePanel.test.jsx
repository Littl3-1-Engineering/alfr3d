import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CollapsibleSidePanel from './CollapsibleSidePanel'

const renderPanel = (props = {}) => render(
  <CollapsibleSidePanel position="left" title="W3ATH3R" isOpen onClose={() => {}} {...props}>
    <p>panel body</p>
  </CollapsibleSidePanel>,
)

describe('CollapsibleSidePanel', () => {
  it('no longer renders a vertical edge tab', () => {
    // The launcher ring around the Core opens these now.
    const { container } = renderPanel()
    expect(container.querySelector('[style*="vertical-rl"]')).toBeNull()
  })

  it('carries its own close control, since removing the tab removed the only way out', () => {
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
})
