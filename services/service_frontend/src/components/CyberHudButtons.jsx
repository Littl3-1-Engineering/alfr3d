// src/components/CyberHudButtons.jsx
//
// Live, clickable recreation of the design canvas's two "Component" boards
// (https://claude.ai/artifact/KAg7YLESJGQuxR2Du3aVNs — "Component · 3 Recreations & Bounce" and
// "Component · 5 New Recreations"), built on the `HudRing` shapes that already exist rather than
// re-deriving the geometry. Each ring is a real toggle button: click it, it bounce-settles and
// flips active/inactive, exactly like the canvas demo.
//
// Demo state only for now — see the TODO in todo/todo_cyber_hud_buttons_frontend.md: these are
// meant to become the on/off control for real IoT devices (lights, switches, covers) once a
// surface needs a literal button rather than the role-based status rings FavoriteDeviceTile
// already wears.
//
// Design source: "cyber btns" by Goran Spasojevic (@gorango) — codepen.io/gorango/pen/vNXejK.

import PropTypes from 'prop-types';
import { useCallback, useEffect, useRef, useState } from 'react';
import HudRing from './HudRing';

// Matches each shape's own authored resolve duration (see HudRing.jsx's SHAPES table), so the
// button releases back to idle/active right as its own bounce-settle finishes.
const RESOLVE_MS = {
  compass: 950,
  splitArc: 1200,
  gear: 1550,
  scanner: 1250,
  sensor: 1300,
  node: 1600,
  reticle: 1100,
  iris: 1700,
};

const CyberButton = ({ shape, label, origin }) => {
  const [on, setOn] = useState(false);
  const [bouncing, setBouncing] = useState(false);
  const timeoutRef = useRef(null);

  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const handleClick = useCallback(() => {
    setOn((v) => !v);
    setBouncing(true);
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setBouncing(false), RESOLVE_MS[shape] ?? 1000);
  }, [shape]);

  const state = bouncing ? 'resolve' : (on ? 'active' : 'idle');

  return (
    <div className="flex flex-col items-center gap-2 w-28">
      <HudRing shape={shape} state={state} size={64} onClick={handleClick} label={label} pressed={on} />
      <div className="font-mono text-[11px] uppercase tracking-widest text-fui-text text-center">
        {label}
      </div>
      <div className="font-mono text-[9px] text-fui-text/50 text-center">
        recreated from {origin}
      </div>
    </div>
  );
};

CyberButton.propTypes = {
  shape: PropTypes.string.isRequired,
  label: PropTypes.string.isRequired,
  origin: PropTypes.string.isRequired,
};

// "Component · 3 Recreations & Bounce" — the three primaries that carry the bounce-settle.
const SET_ONE = [
  { shape: 'compass', label: 'Compass Ring', origin: '#b1' },
  { shape: 'splitArc', label: 'Split-Arc Ring', origin: '#b2' },
  { shape: 'gear', label: 'Gear Dial', origin: '#b7' },
];

// "Component · 5 New Recreations" — the five identity shapes (#b4 was never built by gorango
// himself, so it's skipped here too, matching the canvas).
const SET_TWO = [
  { shape: 'scanner', label: 'Scanner Arc', origin: '#b3' },
  { shape: 'sensor', label: 'Sensor Ring', origin: '#b5' },
  { shape: 'node', label: 'Node Ring', origin: '#b6' },
  { shape: 'reticle', label: 'Quad Reticle', origin: '#b8' },
  { shape: 'iris', label: 'Iris Ring', origin: '#b9' },
];

const CyberHudButtons = () => (
  <div>
    <h3 className="font-tech font-bold text-lg uppercase tracking-widest text-fui-accent mb-2">
      Cyber HUD Buttons
    </h3>
    <p className="text-fui-text text-sm mb-4 max-w-3xl">
      The design canvas&apos;s two component boards, live: click any ring to toggle it and watch
      its own bounce-settle play. Demo state only — these aren&apos;t wired to anything yet.
    </p>
    <div className="mb-8">
      <div className="font-mono text-xs uppercase tracking-widest text-fui-accent/80 mb-3">
        Component &middot; 3 Recreations &amp; Bounce
      </div>
      <div className="flex flex-wrap gap-8">
        {SET_ONE.map((btn) => <CyberButton key={btn.shape} {...btn} />)}
      </div>
    </div>
    <div>
      <div className="font-mono text-xs uppercase tracking-widest text-fui-accent/80 mb-3">
        Component &middot; 5 New Recreations
      </div>
      <div className="flex flex-wrap gap-8">
        {SET_TWO.map((btn) => <CyberButton key={btn.shape} {...btn} />)}
      </div>
    </div>
  </div>
);

export default CyberHudButtons;
