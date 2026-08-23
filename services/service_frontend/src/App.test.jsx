import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import App from './App'
import { ThemeProvider } from './utils/ThemeContext'
import { AuthProvider } from './utils/AuthContext'

describe('App', () => {
  it('renders the app', () => {
    render(
      <ThemeProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ThemeProvider>
    )
    // Basic test - check if something renders
    expect(document.body).toBeTruthy()
  })
})
