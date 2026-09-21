import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSettleOnChange } from './useSettleOnChange'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const render = (initial) => renderHook(
  ({ signatures }) => useSettleOnChange(signatures),
  { initialProps: { signatures: initial } },
)

describe('useSettleOnChange', () => {
  it('reports nothing on the first run, because arriving is not changing', () => {
    const { result } = render({ 'device-1': 'online', 'device-2': 'online' })
    expect([...result.current]).toEqual([])
  })

  it('reports only the entity whose value actually moved', () => {
    const { result, rerender } = render({ 'device-1': 'online', 'device-2': 'online' })
    rerender({ signatures: { 'device-1': 'offline', 'device-2': 'online' } })
    expect([...result.current]).toEqual(['device-1'])
  })

  it('treats a newly appearing key as an event, so coming home registers', () => {
    // The users list is filtered to online members upstream, so an arrival is a new key
    // rather than a changed one.
    const { result, rerender } = render({ 'user-alice': 'resident:online' })
    rerender({ signatures: { 'user-alice': 'resident:online', 'user-bob': 'guest:online' } })
    expect([...result.current]).toEqual(['user-bob'])
  })

  it('stays silent when a whole list lands at once, which is a load and not events', () => {
    const { result, rerender } = render({ 'c-1': '0' })
    rerender({ signatures: { 'c-1': '1', 'c-2': '0', 'c-3': '0', 'c-4': '0', 'c-5': '0' } })
    expect([...result.current]).toEqual([])
  })

  it('does not re-report the same value on a later render', () => {
    const { result, rerender } = render({ 'device-1': 'online' })
    rerender({ signatures: { 'device-1': 'offline' } })
    expect([...result.current]).toEqual(['device-1'])

    rerender({ signatures: { 'device-1': 'offline' } })
    expect([...result.current]).toEqual(['device-1']) // still settling, not re-triggered
  })

  it('stops reporting once the settle has had time to finish', () => {
    const { result, rerender } = render({ 'device-1': 'online' })
    rerender({ signatures: { 'device-1': 'offline' } })
    expect([...result.current]).toEqual(['device-1'])

    act(() => { vi.advanceTimersByTime(1700) })
    expect([...result.current]).toEqual([])
  })
})
