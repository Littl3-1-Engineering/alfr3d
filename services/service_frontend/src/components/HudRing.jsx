// src/components/HudRing.jsx
//
// Animated cyber-HUD ring: a button, a loader and a status indicator in one component.
//
// Design source: "cyber btns" by Goran Spasojevic (@gorango) —
// https://codepen.io/gorango/pen/vNXejK. These are from-scratch recreations of the visual
// idea in React/Framer Motion, not a port of his Snap.svg code. Credit travels with any
// surface that ships them (see README design notes).
//
// Three rules that are load-bearing, not stylistic:
//
//   1. A ring is never still. `working` runs the shape at its authored tempo; `idle` and
//      `active` run the SAME motion slowed right down. Only a fault freezes. The first pass
//      had this backwards ("at rest, nothing spins") and shipped a HUD that sat perfectly
//      still whenever nothing was in flight — which is almost always — making the rings
//      indistinguishable from flat icons. Speed carries urgency; stillness means broken.
//   2. Every shape is one STATIC base ring plus one or two layers that animate
//      INDEPENDENTLY — never a single transform on the whole group. The counter-rotation
//      between layers is what sells the effect; gorango's originals are built the same way.
//   3. Angles accumulate, they are never reset. Each layer owns a persistent rotation
//      motion value that the frame loop advances and wraps by a whole turn, so changing
//      state changes the layer's RATE and nothing else. This is what replaced the old rule
//      that every keyframe list had to end on a 360 degree multiple: a declarative loop
//      restarted from wherever it was and snapped visibly. Resolve keyframes are still
//      written as full turns, but applied as an offset from the live angle.
//
// Shape vocabulary (see todo/todo_cyber_hud_buttons_frontend.md — the same table is
// mirrored in alfr3d_deck; if you change one, change both):
//
//   compass   acquire / lock    — presence found, scan resolved, a state changed
//   splitArc  handshake / sync  — request in flight, backend reachability, relay
//   gear      process / compute — rule engine, inference, background work
//
//   scanner / sensor / node / reticle / iris are IDENTITY shapes. They tell one
//   launcher or menu item apart from another and carry no system meaning, so they must
//   not be used for loaders or indicators.

import {
  AnimatePresence,
  animate,
  motion,
  useAnimationFrame,
  useMotionValue,
  useReducedMotion,
} from 'framer-motion';
import PropTypes from 'prop-types';
import { useEffect, useRef, useState } from 'react';
import { useTheme } from '../utils/useTheme';

// --- Shape geometry + per-layer motion -------------------------------------------------
//
// Coordinates are viewBox units (0-100), so stroke widths scale with `size` for free.
// Each layer carries three motion specs:
//   work    — the indeterminate loop, one seamless full turn
//   resolve — the one-shot bounce-settle, recreated from gorango's easing
//   fault   — a static angle, i.e. the layer stalled mid-travel

const ring = (r, strokeWidth, dash) => (
  <circle
    cx="50"
    cy="50"
    r={r}
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeDasharray={dash}
  />
);

const COMPASS_TICKS = (
  <>
    <rect x="46.5" y="4.5" width="7" height="7" fill="currentColor" />
    <rect x="88.5" y="46.5" width="7" height="7" fill="currentColor" />
    <rect x="46.5" y="88.5" width="7" height="7" fill="currentColor" />
    <rect x="4.5" y="46.5" width="7" height="7" fill="currentColor" />
  </>
);

const GEAR_TICKS = (
  <>
    <rect x="46" y="1" width="8" height="10" fill="currentColor" />
    <rect x="89" y="45" width="10" height="8" fill="currentColor" />
    <rect x="46" y="89" width="8" height="10" fill="currentColor" />
    <rect x="1" y="45" width="10" height="8" fill="currentColor" />
  </>
);

const SHAPES = {
  // #b1 — static thin outer ring, plus a 4-tick layer that pulses its radius, spins and
  // bounce-settles. One animated layer with two independent transform channels.
  compass: {
    base: ring(42, 2),
    layers: [
      {
        key: 'ticks',
        content: COMPASS_TICKS,
        work: { rotate: 360, duration: 5 },
        resolve: {
          animate: {
            rotate: [0, 360],
            scale: [0.72, 1.16, 0.95, 1.05, 0.98, 1.015, 1],
            opacity: [0.5, 1],
          },
          transition: {
            rotate: { duration: 0.9, ease: [0.22, 1, 0.36, 1] },
            scale: { duration: 0.9, times: [0, 0.32, 0.52, 0.68, 0.82, 0.92, 1] },
            opacity: { duration: 0.3 },
          },
        },
      },
    ],
  },

  // #b2 — two arc rings counter-rotate: the inner one spins one way while shrinking, the
  // outer fades in spinning the opposite way and faster.
  splitArc: {
    base: ring(46, 1.5),
    layers: [
      {
        key: 'inner',
        content: ring(34, 10, '76 30'),
        work: { rotate: -360, duration: 4 },
        resolve: {
          animate: { rotate: [0, -150, -360], scale: [1, 0.92, 1] },
          transition: {
            rotate: { duration: 0.9, times: [0, 0.4, 1] },
            scale: { duration: 0.9, times: [0, 0.4, 1] },
          },
        },
      },
      {
        key: 'outer',
        content: ring(46, 4, '58 40'),
        work: { rotate: 360, duration: 6.5 },
        resolve: {
          animate: { rotate: [0, 170, 360], opacity: [0, 0.85, 0.85] },
          transition: {
            rotate: { duration: 1.15, times: [0, 0.45, 1], ease: [0.22, 1, 0.36, 1] },
            opacity: { duration: 1.15, times: [0, 0.45, 1] },
          },
        },
      },
    ],
  },

  // #b7 — a dense tick ring makes one smooth turn while 4 cardinal ticks ratchet the
  // opposite way in three uneven steps. Two gears turning against each other, no scaling.
  gear: {
    base: (
      <>
        {ring(30, 1)}
        <circle cx="50" cy="50" r="3" fill="currentColor" />
      </>
    ),
    layers: [
      {
        key: 'dense',
        content: ring(46, 4, '3 6'),
        work: { rotate: -360, duration: 8 },
        resolve: {
          animate: { rotate: [0, -360] },
          transition: { rotate: { duration: 1.5, ease: [0.45, 0.05, 0.55, 0.95] } },
        },
      },
      {
        key: 'ticks',
        content: GEAR_TICKS,
        work: { rotate: 360, duration: 5.5 },
        resolve: {
          animate: { rotate: [0, 150, 230, 360] },
          transition: {
            rotate: { duration: 1.1, times: [0, 0.3, 0.55, 1], ease: [0.5, 0, 0.2, 1] },
          },
        },
      },
    ],
  },

  // #b3 — two dashed tick-arcs opposite each other counter-rotate at different speeds,
  // one of them bounce-settling: a sensor doing an asymmetric sweep.
  scanner: {
    base: ring(44, 1.5),
    layers: [
      {
        key: 'sweepA',
        content: (
          <path
            d="M14 38 A36 36 0 0 1 38 14"
            fill="none"
            stroke="currentColor"
            strokeWidth="7"
            strokeDasharray="4 5"
          />
        ),
        work: { rotate: 360, duration: 5 },
        resolve: {
          animate: { rotate: [0, 360] },
          transition: { rotate: { duration: 1, ease: [0.22, 1, 0.36, 1] } },
        },
      },
      {
        key: 'sweepB',
        content: (
          <>
            <path
              d="M14 62 A36 36 0 0 0 38 86"
              fill="none"
              stroke="currentColor"
              strokeWidth="7"
              strokeDasharray="4 5"
            />
            <circle cx="50" cy="50" r="3" fill="currentColor" />
          </>
        ),
        work: { rotate: -360, duration: 7 },
        resolve: {
          animate: {
            rotate: [0, -190, -300, -360],
            scale: [0.8, 1.08, 0.97, 1],
            opacity: [0.55, 1, 1, 1],
          },
          transition: {
            rotate: { duration: 1.25, times: [0, 0.38, 0.64, 1] },
            scale: { duration: 1.25, times: [0, 0.38, 0.64, 1] },
            opacity: { duration: 1.25, times: [0, 0.38, 0.64, 1] },
          },
        },
      },
    ],
  },

  // #b5 — a full dashed outer ring with a small dashed crosshair at the centre. The outer
  // turns one way, the crosshair spins back and settles like a needle finding its heading.
  sensor: {
    base: ring(46, 1),
    layers: [
      {
        key: 'outer',
        content: ring(44, 5, '6 7'),
        work: { rotate: 360, duration: 6 },
        resolve: {
          animate: { rotate: [0, 360] },
          transition: { rotate: { duration: 1.3, ease: [0.22, 1, 0.36, 1] } },
        },
      },
      {
        key: 'inner',
        content: ring(12, 2, '3 4'),
        work: { rotate: -360, duration: 3.5 },
        resolve: {
          animate: {
            rotate: [0, -150, -270, -360],
            scale: [0.6, 1.22, 0.95, 1],
            opacity: [0.4, 1, 1, 1],
          },
          transition: {
            rotate: { duration: 0.85, times: [0, 0.35, 0.68, 1] },
            scale: { duration: 0.85, times: [0, 0.35, 0.68, 1] },
            opacity: { duration: 0.85, times: [0, 0.35, 0.68, 1] },
          },
        },
      },
    ],
  },

  // #b6 — a faint half-arc ghost ring turning slowly behind three nodes that pulse
  // together: a status heartbeat either side of a hub.
  node: {
    base: ring(44, 1),
    layers: [
      {
        key: 'ghost',
        content: ring(44, 8, '70 60'),
        opacity: 0.4,
        work: { rotate: 360, duration: 9 },
        resolve: {
          animate: { rotate: [0, 360] },
          transition: { rotate: { duration: 1.6, ease: [0.45, 0.05, 0.55, 0.95] } },
        },
      },
      {
        key: 'nodes',
        content: (
          <>
            <circle cx="8" cy="50" r="5" fill="currentColor" />
            <circle cx="92" cy="50" r="5" fill="currentColor" />
            <circle cx="50" cy="50" r="4" fill="currentColor" />
          </>
        ),
        work: { scale: [1, 1.14, 1], duration: 1.8 },
        resolve: {
          animate: {
            scale: [0.7, 1.18, 0.96, 1.04, 1],
            opacity: [0.5, 1, 1, 1, 1],
          },
          transition: {
            scale: { duration: 0.9, times: [0, 0.3, 0.55, 0.78, 1] },
            opacity: { duration: 0.9, times: [0, 0.3, 0.55, 0.78, 1] },
          },
        },
      },
    ],
  },

  // #b8 — a chunky 4-block ring turning smoothly while a centre crosshair ratchets the
  // opposite way in uneven steps, like a targeting reticle locking on.
  reticle: {
    base: ring(28, 1),
    layers: [
      {
        key: 'quad',
        content: ring(44, 12, '17 5.5'),
        work: { rotate: 360, duration: 6 },
        resolve: {
          animate: { rotate: [0, 360] },
          transition: { rotate: { duration: 1.1, ease: [0.22, 1, 0.36, 1] } },
        },
      },
      {
        key: 'cross',
        content: (
          <>
            <rect x="47" y="38" width="6" height="24" fill="currentColor" />
            <rect x="38" y="47" width="24" height="6" fill="currentColor" />
          </>
        ),
        work: { rotate: -360, duration: 4 },
        resolve: {
          animate: { rotate: [0, -100, -160, -360], scale: [0.8, 1.12, 0.97, 1] },
          transition: {
            rotate: { duration: 1, times: [0, 0.4, 0.7, 1], ease: [0.5, 0, 0.2, 1] },
            scale: { duration: 1, times: [0, 0.4, 0.7, 1] },
          },
        },
      },
    ],
  },

  // #b9 — the boldest shape in the pen: a heavy scalloped wedge ring over a thin inner
  // guide, both spinning independently. A camera iris, or a blast door dialling open.
  iris: {
    base: ring(47, 1),
    layers: [
      {
        key: 'wedges',
        content: ring(44, 15, '20 9'),
        work: { rotate: 360, duration: 7 },
        resolve: {
          animate: { rotate: [0, 360] },
          transition: { rotate: { duration: 1.4, ease: [0.22, 1, 0.36, 1] } },
        },
      },
      {
        key: 'inner',
        content: ring(30, 1, '2 5'),
        work: { rotate: -360, duration: 9 },
        resolve: {
          animate: { rotate: [0, -360] },
          transition: { rotate: { duration: 1.7, ease: [0.45, 0.05, 0.55, 0.95] } },
        },
      },
    ],
  },
};

// Kept module-local on purpose: a named export here trips
// react-refresh/only-export-components. Callers that need to enumerate shapes (the
// Matrix gallery, tests) should list the ones they actually want.
const SHAPE_NAMES = Object.keys(SHAPES);

// --- Tone ------------------------------------------------------------------------------
//
// `state` outranks `tone`: active is always the selection colour and fault is always the
// alert colour, whatever the caller asked for. Values are read from the live theme rather
// than hardcoded, so all five themes work without a new token.

const TONE_TOKEN = { cyan: 'primary', magenta: 'magenta', amber: 'env' };

// The state picks a tone unless the caller names one. A fault is amber by default, but a
// caller sometimes needs to outrank that — a container with two errors has to look
// different from one with a single warning, and both are faults.
const effectiveTone = (tone, state) => {
  if (tone) return tone;
  if (state === 'active') return 'magenta';
  if (state === 'fault') return 'amber';
  return 'cyan';
};

// Layers sit at a low opacity when nothing is happening, so a ring at rest reads as a
// quiet silhouette without implying activity. It still turns — see rule 1 — just slowly
// and dimly.
const IDLE_LAYER_OPACITY = 0.45;

// --- Motion tiers ----------------------------------------------------------------------
//
// One multiplier over each shape's own authored cycle time, so the three moving tiers are
// literally the same animation at three speeds. With `work` durations of 4-9s that puts
// idle at roughly 20-45s per turn (a drift you notice only if you watch for it) and active
// at 10-22s (clearly livelier than its neighbours without competing with a real loader).
const DRIFT_FACTOR = { idle: 5, active: 2.4, working: 1 };

const TAU = Math.PI * 2;
const OPACITY_TWEEN = { duration: 0.25, ease: 'easeOut' };
const REST_TWEEN = { duration: 0.25, ease: 'easeOut' };
const FREEZE_TWEEN = { duration: 0.35, ease: 'easeOut' };

// A whole turn is the identity, so folding it away keeps the accumulator small without
// anything moving on screen.
const wrapTurn = (deg) => {
  if (deg >= 360) return deg - 360;
  if (deg <= -360) return deg + 360;
  return deg;
};

const staticAngle = (layer, index) => {
  const direction = (layer.work && layer.work.rotate) || (index % 2 === 0 ? 1 : -1);
  return direction > 0 ? 214 : -137;
};

// --- One layer -------------------------------------------------------------------------
//
// A component per layer rather than hooks in a loop over `spec.layers`: shapes carry one or
// two layers, and a hook count that varies per shape is not a thing. Each instance owns its
// own persistent transform channels, which is what rule 3 depends on.
//
// The transform is written to the SVG `transform` ATTRIBUTE by hand rather than handed to a
// `motion.g`. Framer Motion, when it owns an element's transform, overwrites
// `transform-origin` with a value derived from the element's measured box — which for an arc
// layer (scanner's quarter-arcs, splitArc's dashed bands) is not the ring's centre, so the
// layer would swing around a point off to one side. `translate(50 50) … translate(-50 -50)`
// is stated in viewBox units and cannot be second-guessed.

const centredTransform = (deg, factor) =>
  `translate(50 50) rotate(${deg.toFixed(3)}) scale(${factor.toFixed(4)}) translate(-50 -50)`;

const HudRingLayer = ({ layer, index, state, reducedMotion, restOpacity }) => {
  const groupRef = useRef(null);
  const rotate = useMotionValue(0);
  const scale = useMotionValue(1);
  // Only the resolve keyframes touch this; the layer's resting opacity is a CSS transition
  // on the wrapper below, so the two compose instead of fighting.
  const flash = useMotionValue(1);
  const painted = useRef({ transform: '', opacity: '' });

  // A layer either turns or pulses; `work` says which.
  const spin = layer.work.rotate ?? null;
  const pulsePeak = Array.isArray(layer.work.scale) ? Math.max(...layer.work.scale) : null;
  const phase = useRef(0);

  // The bounce is a one-shot, and the drift has to pick up once it lands — otherwise the
  // "done" leaves the ring parked, which is exactly what rule 1 exists to prevent. Callers
  // hold `resolve` for a beat (EventStream keeps it until something newer arrives), so this
  // cannot wait for the state to change back.
  const [settled, setSettled] = useState(false);

  const factor = DRIFT_FACTOR[state]
    ?? (state === 'resolve' && settled ? DRIFT_FACTOR.idle : null);
  const drifting = !reducedMotion && factor !== null;

  const paint = () => {
    const node = groupRef.current;
    if (!node) return;
    const transform = centredTransform(rotate.get(), scale.get());
    if (transform !== painted.current.transform) {
      painted.current.transform = transform;
      node.setAttribute('transform', transform);
    }
    const opacity = flash.get().toFixed(3);
    if (opacity !== painted.current.opacity) {
      painted.current.opacity = opacity;
      node.setAttribute('opacity', opacity);
    }
  };

  useAnimationFrame((_, delta) => {
    if (drifting) {
      const cycleMs = layer.work.duration * factor * 1000;
      if (spin !== null) {
        rotate.set(wrapTurn(rotate.get() + (spin * delta) / cycleMs));
      } else if (pulsePeak !== null) {
        phase.current = (phase.current + delta / cycleMs) % 1;
        scale.set(1 + (pulsePeak - 1) * ((1 - Math.cos(phase.current * TAU)) / 2));
      }
    }
    paint();
  });

  useEffect(() => {
    // Reduced motion is a hard stop, not a slower loop: no rotation, no scale, with colour
    // and opacity left to carry the state on their own.
    if (reducedMotion) {
      rotate.set(0);
      scale.set(1);
      flash.set(1);
      paint();
      return undefined;
    }

    const running = [];

    if (state === 'resolve') {
      setSettled(false);
      phase.current = 0;
      const frames = layer.resolve.animate;
      const timings = layer.resolve.transition;
      // Offset from the live angle: the bounce starts where the ring actually is. The
      // authored lists still end on a full turn, so it lands back on its own heading and
      // the drift resumes without a step.
      const base = rotate.get();
      let claimed = false;
      const onDone = () => {
        rotate.set(wrapTurn(base));
        setSettled(true);
      };
      if (frames.rotate) {
        claimed = true;
        running.push(animate(rotate, frames.rotate.map((deg) => base + deg), {
          ...timings.rotate,
          onComplete: onDone,
        }));
      }
      if (frames.scale) {
        running.push(animate(scale, frames.scale, claimed
          ? timings.scale
          : { ...timings.scale, onComplete: onDone }));
        claimed = true;
      }
      if (!claimed) setSettled(true);
      if (frames.opacity) running.push(animate(flash, frames.opacity, timings.opacity));
      return () => running.forEach((controls) => controls.stop());
    }

    running.push(animate(flash, 1, OPACITY_TWEEN));

    if (state === 'fault') {
      // The only still state in the machine. Both channels park, out of step with the
      // layer next door, so a stalled ring reads as stalled rather than as slow.
      running.push(animate(rotate, staticAngle(layer, index), FREEZE_TWEEN));
      running.push(animate(scale, 1, FREEZE_TWEEN));
    } else if (spin !== null) {
      // The frame loop owns rotation from here; this only unwinds a leftover bounce scale.
      running.push(animate(scale, 1, REST_TWEEN));
    }

    return () => running.forEach((controls) => controls.stop());
    // `layer` and `index` are fixed for the life of the instance (it is keyed by shape and
    // layer key), and `paint` only reads refs, so state and reduced motion are the real
    // inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, reducedMotion]);

  return (
    <g style={{ opacity: restOpacity, transition: 'opacity 250ms ease-out' }}>
      <g ref={groupRef} data-testid={`hud-ring-layer-${layer.key}`}>
        {layer.content}
      </g>
    </g>
  );
};

HudRingLayer.propTypes = {
  layer: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired,
  state: PropTypes.string.isRequired,
  reducedMotion: PropTypes.bool,
  restOpacity: PropTypes.number.isRequired,
};

const HudRing = ({
  shape = 'compass',
  state = 'idle',
  size = 28,
  tone = null,
  onClick = null,
  label = null,
  pressed = null,
  className = '',
}) => {
  const { themeColors } = useTheme();
  const prefersReducedMotion = useReducedMotion();

  const spec = SHAPES[shape] || SHAPES.compass;
  const color = themeColors[TONE_TOKEN[effectiveTone(tone, state)]];

  const layerAlpha = state === 'idle' ? IDLE_LAYER_OPACITY : 1;
  const glow = Math.max(3, size * (state === 'active' ? 0.3 : 0.18));

  const art = (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      focusable="false"
      aria-hidden="true"
      style={{ display: 'block', overflow: 'visible' }}
    >
      <g style={{ color, filter: `drop-shadow(0 0 ${glow}px ${color})` }}>
        <g opacity={state === 'idle' ? 0.55 : 0.75}>{spec.base}</g>

        {spec.layers.map((layer, index) => (
          <HudRingLayer
            // Keyed by shape too: a shape swap must build new channels rather than inherit
            // the outgoing layer's angle, which would belong to different geometry.
            key={`${shape}-${layer.key}`}
            layer={layer}
            index={index}
            state={state}
            reducedMotion={!!prefersReducedMotion}
            restOpacity={(layer.opacity ?? 1) * layerAlpha}
          />
        ))}

        {/* Selection frame. gorango's originals snap four corner brackets in around the
            ring once it is chosen; it is the clearest "this one is on" signal we have. */}
        <AnimatePresence>
          {state === 'active' && (
            <motion.g
              key="brackets"
              data-testid="hud-ring-brackets"
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: prefersReducedMotion ? 0.15 : 0.35, ease: 'easeOut' }}
              style={{ transformBox: 'view-box', transformOrigin: '50px 50px' }}
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
            >
              <path d="M0 14 L0 0 L14 0" />
              <path d="M86 0 L100 0 L100 14" />
              <path d="M100 86 L100 100 L86 100" />
              <path d="M14 100 L0 100 L0 86" />
            </motion.g>
          )}
        </AnimatePresence>
      </g>
    </svg>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={label || undefined}
        // A toggle stays pressed while it plays its settle, so the caller can say so
        // rather than having the ring infer it from a state that is briefly `resolve`.
        aria-pressed={pressed ?? state === 'active'}
        title={label || undefined}
        className={`inline-flex items-center justify-center bg-transparent border-0 p-0 cursor-pointer ${className}`}
        style={{ width: size, height: size, lineHeight: 0 }}
      >
        {art}
      </button>
    );
  }

  return (
    <span
      className={`inline-flex items-center justify-center ${className}`}
      style={{ width: size, height: size, lineHeight: 0 }}
      role={label ? 'img' : undefined}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : 'true'}
    >
      {art}
    </span>
  );
};

HudRing.propTypes = {
  shape: PropTypes.oneOf(SHAPE_NAMES),
  state: PropTypes.oneOf(['idle', 'working', 'resolve', 'active', 'fault']),
  size: PropTypes.number,
  tone: PropTypes.oneOf(['cyan', 'magenta', 'amber']),
  onClick: PropTypes.func,
  label: PropTypes.string,
  pressed: PropTypes.bool,
  className: PropTypes.string,
};

export default HudRing;
