import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ErrorBoundary', () => {
  it('renders its children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>all good</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('all good')).toBeInTheDocument()
  })

  it('renders the error fallback when a child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    function Bomb() {
      throw new Error('kapow')
    }
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    )
    expect(screen.getByText('COMPONENT ERROR')).toBeInTheDocument()
    expect(screen.getByText('kapow')).toBeInTheDocument()
    expect(screen.getByText('RETRY')).toBeInTheDocument()
  })

  it('recovers when RETRY is clicked and the child renders successfully', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    let shouldThrow = true
    function Flaky() {
      if (shouldThrow) throw new Error('first render fails')
      return <div>recovered</div>
    }
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    )
    expect(screen.getByText('COMPONENT ERROR')).toBeInTheDocument()

    shouldThrow = false
    fireEvent.click(screen.getByText('RETRY'))
    expect(screen.getByText('recovered')).toBeInTheDocument()
  })
})
