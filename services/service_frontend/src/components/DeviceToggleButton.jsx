// src/components/DeviceToggleButton.jsx
//
// A literal on/off cyber HUD button (the toggle role demoed by CyberHudButtons.jsx on the
// Matrix > Customizations gallery) wired to a real device command instead of local demo
// state — the wiring todo/todo_cyber_hud_buttons_frontend.md §8 asked for. Shared by
// FavoriteDeviceTile and ControlBlade for the same reason deviceRings.js is: a toggle
// should look the same on both surfaces.
//
// `resolving` is computed by the caller via useSettleOnChange, keyed off a "confirmed"
// generation counter the caller only bumps once its command actually succeeds — not on the
// click itself. That keeps the bounce a "done", not a "click", per HudRing's own discipline
// rule, even though the visible on/off state here is set optimistically a moment earlier.

import PropTypes from 'prop-types';
import HudRing from './HudRing';

const DeviceToggleButton = ({
  shape,
  active,
  resolving = false,
  loading = false,
  offline = false,
  disabled = false,
  onClick,
  label,
  size = 40,
}) => {
  const state = offline ? 'fault' : loading ? 'working' : resolving ? 'resolve' : (active ? 'active' : 'idle');
  const isDisabled = disabled || loading || offline;

  return (
    <div className={isDisabled ? 'opacity-40' : ''}>
      <HudRing
        shape={shape}
        state={state}
        size={size}
        onClick={isDisabled ? undefined : onClick}
        label={label}
        pressed={active}
      />
    </div>
  );
};

DeviceToggleButton.propTypes = {
  shape: PropTypes.string.isRequired,
  active: PropTypes.bool.isRequired,
  resolving: PropTypes.bool,
  loading: PropTypes.bool,
  offline: PropTypes.bool,
  disabled: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  size: PropTypes.number,
};

export default DeviceToggleButton;
