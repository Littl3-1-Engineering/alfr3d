import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import App from '../App'

describe('App', () => {
  it('renders the app', () => {
    render(<App />)
    // Basic test - check if something renders
    expect(document.body).toBeTruthy()
  })
})
