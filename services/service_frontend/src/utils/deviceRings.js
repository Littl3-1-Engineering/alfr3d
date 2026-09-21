// src/utils/deviceRings.js
//
// One ring shape per device kind, shared by the two surfaces that control devices:
// FavoriteDeviceTile (the compact quick-control tile) and ControlBlade (its full-size
// anchored counterpart). Keeping the mapping here means a lock looks like a lock in both.
//
// Shapes follow the vocabulary in todo/todo_cyber_hud_buttons_frontend.md: these are the
// identity shapes, plus Compass and Gear where the meaning genuinely fits.

export const DEVICE_RING_SHAPES = {
  light: 'compass',
  switch: 'reticle',
  climate: 'sensor',
  thermostat: 'sensor',
  fan: 'scanner',
  cover: 'iris',
  lock: 'gear',
  media_player: 'node',
};

export const ringShapeForDevice = (deviceType) => DEVICE_RING_SHAPES[deviceType] || 'splitArc';
