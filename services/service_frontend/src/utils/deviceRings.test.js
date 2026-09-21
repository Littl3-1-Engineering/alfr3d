import { describe, it, expect } from 'vitest'
import { DEVICE_RING_SHAPES, ringShapeForDevice } from './deviceRings'

// The eight kinds FavoriteDeviceTile's TYPE_ICONS knows about. If a device type gains an
// icon there, it needs a ring here too, or the compact tile and the full ControlBlade will
// disagree about what that device looks like.
const DEVICE_TYPES_WITH_ICONS = [
  'light', 'switch', 'climate', 'thermostat', 'fan', 'cover', 'lock', 'media_player',
]

describe('deviceRings', () => {
  it('covers every device kind the control surfaces can render', () => {
    DEVICE_TYPES_WITH_ICONS.forEach((type) => {
      expect(DEVICE_RING_SHAPES[type]).toBeTruthy()
    })
  })

  it('falls back to the handshake ring for a kind nobody has mapped yet', () => {
    expect(ringShapeForDevice('doorbell')).toBe('splitArc')
    expect(ringShapeForDevice(undefined)).toBe('splitArc')
  })

  it('gives kinds that share an icon the same ring, and others their own', () => {
    // climate and thermostat both render a Thermometer, so they should read alike.
    expect(ringShapeForDevice('climate')).toBe(ringShapeForDevice('thermostat'))
    // Everything else has to be distinguishable at a glance.
    const distinct = ['light', 'switch', 'climate', 'fan', 'cover', 'lock', 'media_player']
      .map(ringShapeForDevice)
    expect(new Set(distinct).size).toBe(distinct.length)
  })
})
