import { describe, it, expect } from 'vitest'
import { sortByOnlineState } from './sortUtils'

describe('sortByOnlineState', () => {
  const items = [
    { name: 'old-offline', state: 'offline', last_online: '2026-01-01T10:00:00Z' },
    { name: 'never', state: 'offline', last_online: null },
    { name: 'new-offline', state: 'offline', last_online: '2026-03-01T10:00:00Z' },
    { name: 'online', state: 'online', last_online: '2026-02-01T10:00:00Z' },
    { name: 'offline-missing', state: 'offline' },
  ]

  it('puts online items first', () => {
    const sorted = sortByOnlineState(items)
    expect(sorted[0].name).toBe('online')
    expect(sorted.slice(1).every((i) => i.state !== 'online')).toBe(true)
  })

  it('sorts offline items by most-recently online', () => {
    const sorted = sortByOnlineState(items)
    const offline = sorted.filter((i) => i.state !== 'online')
    expect(offline.map((i) => i.name).slice(0, 2)).toEqual(['new-offline', 'old-offline'])
  })

  it('keeps items with no last-online time at the end', () => {
    const sorted = sortByOnlineState(items)
    const offline = sorted.filter((i) => i.state !== 'online')
    const tails = offline.slice(2).map((i) => i.name)
    expect(tails).toEqual(expect.arrayContaining(['offline-missing', 'never']))
  })

  it('does not mutate the input array', () => {
    const original = items.map((i) => ({ ...i }))
    sortByOnlineState(items)
    expect(items).toEqual(original)
  })

  it('supports custom online/last-online accessors', () => {
    const iot = [
      { name: 'down-2', online: false },
      { name: 'up', online: true },
      { name: 'down-1', online: false },
    ]
    const sorted = sortByOnlineState(
      iot,
      (device) => device.online,
      () => null,
    )
    expect(sorted.map((i) => i.name)).toEqual(['up', 'down-2', 'down-1'])
  })
})
