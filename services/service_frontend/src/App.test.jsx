import { describe, it, expect, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'
import { ThemeProvider } from './utils/ThemeContext'
import { AuthProvider } from './utils/AuthContext'

const renderApp = () =>
  render(
    <ThemeProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ThemeProvider>
  )

describe('App', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/')
  })

  it('renders the app', () => {
    renderApp()
    // Basic test - check if something renders
    expect(document.body).toBeTruthy()
  })

  it('gates the Domain page behind sign-in when unauthenticated', () => {
    window.history.pushState({}, '', '/domain')
    renderApp()
    expect(screen.getByText('Sign In Required')).toBeInTheDocument()
  })

  it('gates the Matrix page behind sign-in when unauthenticated', () => {
    window.history.pushState({}, '', '/matrix')
    renderApp()
    expect(screen.getByText('Sign In Required')).toBeInTheDocument()
  })
})
