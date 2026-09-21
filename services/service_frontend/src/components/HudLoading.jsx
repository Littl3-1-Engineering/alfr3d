// src/components/HudLoading.jsx
//
// The house loader. Every "waiting" moment in Nexus used to be its own thing — a spinning
// lucide icon here, a bare "Loading..." string there — so this exists to make them one.
//
// Shape carries meaning, per the vocabulary in todo/todo_cyber_hud_buttons_frontend.md:
//   fetch   → Split-Arc, the handshake ring: we are waiting on the other end
//   compute → Gear Dial, the process ring: we are waiting on ourselves
//
// The ring is decorative here; the label is what assistive tech reads, so the whole thing
// is a polite live region rather than an unlabelled spinner.

import PropTypes from 'prop-types';
import HudRing from './HudRing';

const HudLoading = ({ label = 'Loading', mode = 'fetch', size = 24, className = '' }) => (
  <div
    role="status"
    aria-live="polite"
    className={`flex items-center justify-center gap-3 ${className}`}
  >
    <HudRing shape={mode === 'compute' ? 'gear' : 'splitArc'} state="working" size={size} />
    <span className="font-mono text-xs uppercase tracking-widest text-fui-text/60">{label}</span>
  </div>
);

HudLoading.propTypes = {
  label: PropTypes.string,
  mode: PropTypes.oneOf(['fetch', 'compute']),
  size: PropTypes.number,
  className: PropTypes.string,
};

export default HudLoading;
