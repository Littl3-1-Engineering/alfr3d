// src/components/HudLoading.jsx
//
// The house loader. Every "waiting" moment in Nexus used to be its own thing — a spinning
// lucide icon here, a bare "Loading..." string there — so this exists to make them one.
//
// Always Gear Dial. It used to switch between Split-Arc (fetch) and Gear Dial (compute) per
// the vocabulary in todo/todo_cyber_hud_buttons_frontend.md, but that distinction never
// carried real information here — every call site just wants "something is happening" — so
// as of 2026-09-25 the generic loader is one shape. Split-Arc keeps its handshake/reachability
// meaning everywhere else it's used (device-online rings, the Nexus boot log's network lines,
// the Quick Controls launcher).
//
// The ring is decorative here; the label is what assistive tech reads, so the whole thing
// is a polite live region rather than an unlabelled spinner.

import PropTypes from 'prop-types';
import HudRing from './HudRing';

const HudLoading = ({ label = 'Loading', size = 24, className = '' }) => (
  <div
    role="status"
    aria-live="polite"
    className={`flex items-center justify-center gap-3 ${className}`}
  >
    <HudRing shape="gear" state="working" size={size} />
    <span className="font-mono text-xs uppercase tracking-widest text-fui-text/60">{label}</span>
  </div>
);

HudLoading.propTypes = {
  label: PropTypes.string,
  size: PropTypes.number,
  className: PropTypes.string,
};

export default HudLoading;
