# Animated Cyber HUD Rings — Web Frontend (Nexus)

## Status: §1-§6 shipped (2026-09-20) — rings, the house loader, the boot checklist, the
event-stream glyphs, the launcher ring, the quick-control state rings, routine-run feedback and
the Matrix gallery are all in. §6 cleanup is done too.

**§3's Core-orbit piece (users/devices/containers) was reverted the same day — see the note
under §3 below — so it is no longer part of what shipped;** every other planned section stands.
§7 stays out of scope.

**Amended 2026-09-25:** `HudLoading`'s `fetch`/`compute` mode is gone — the generic house
loader always renders Gear Dial now, and the `mode` prop was removed as dead weight. The
distinction never carried information at any of its call sites (`CalendarPanel`, `CameraStream`,
`Profile`, `Routines`, `FavoritesPanel`, `Matrix`'s `LoadingFallback`, `ProjectTreeViz`) — every
one of them just meant "something is happening." **Split-Arc keeps its handshake/reachability
meaning everywhere else it's used** — device-online rings (`Core.jsx`, `deviceRings.js`), the
Nexus boot log's network lines, the Quick Controls launcher (`Nexus.jsx`), `EventStream`, and the
Matrix gallery's own vocabulary table — none of that changed. This narrows the shape vocabulary
table below to describe identity/state usage only; it no longer describes what the house loader
picks, because the house loader no longer picks.

**Amended 2026-09-22:** the vertical-text edge tabs are no longer *gone*, they are no longer the
default. "Nobody wants tabs" turned out to be an assumption, so the removal became a preference:
Matrix → Customizations → **Nexus Navigation** picks Orbit Rings (default, unchanged) or Edge
Tabs, stored under `alfr3d-nexus-nav` by `utils/UiPrefsContext.jsx`. In tabs mode `Nexus.jsx`
hands `Core` an empty `launchers` array and each `CollapsibleSidePanel` a `showTab`/`onToggle`
pair; the corner close control and Escape that §6 added stay on in both modes. Nothing about the
ring vocabulary, the state machine or the discipline rules changes — the ring is still the
design ALFR3D leads with.

**§7.5 shipped (2026-09-20), same day, as a correction:** `idle` and `active` had been wired
as still frames — correctly per rule 1 as written, but rule 1 was wrong. Both states are on
almost all of the time (`Core.jsx`'s orbit satellites rest at `idle`, `EventStream` rows go
`idle` a beat after arriving, the launcher ring is `idle` on a screen with no cursor), so a
"motion means something is happening" reading made the HUD read as static icons with a
decorative animation capability nobody ever saw. Rule 1 below is rewritten: every ring always
turns, at one of three tempos (idle slowest, active faster, working fastest); only `fault`
freezes. See `HudRing.jsx`'s header comment for the mechanism (a persistent per-layer angle
driven every animation frame, offset rather than reset by the bounce).

Companion doc: `alfr3d_deck/todo/todo_cyber_hud_widgets.md` (the Compose port). The
**Shape vocabulary**, **state machine** and **correctness rules** sections below are duplicated
verbatim in that file on purpose — if you change one, change both, or the two surfaces drift.

## Mockup — validated design, ready to implement against

Full interactive mockup (HTML/CSS, not React — a design reference, not a code source):
https://claude.ai/artifact/KAg7YLESJGQuxR2Du3aVNs — six boards: live clickable recreations of
all 8 button designs gorango built (`#b4` was never built in his own source, so it's skipped
here too) across two component boards, plus "Web · Nexus Quick Controls", "Web · Matrix Action
Bar", "Deck · Socket Radial Menu" and a 100-candidate selection catalog. Every tile/action on
the context boards has its own unique ring.

The board to build from first is **`button-states.dc.html` — "Component · 3 Recreations &
Bounce"**: Compass Ring (`#b1`), Split-Arc Ring (`#b2`), Gear Dial (`#b7`). Those three carry
the bounce-settle, which is the part worth preserving.

> **Correction, verified 2026-09-19:** the canvas's own `credit-note` claims "the real Compose
> port in alfr3d_deck shipped a generative version of this same idea." It did not — there is no
> HUD/dial/ring file in `alfr3d_deck` on any branch. Both repos are at zero code. Fix that note
> next time the canvas is edited.

Read gorango's actual Snap.svg source for `#b1`/`#b2`/`#b7` (not just the rendered look) —
corrects the original assumption that each button was a single rotating unit:

- **Every button is 2-3 independently-animated layers over one static base ring.** `#b1`
  ("Compass Ring") pulses+spins+bounces a 4-tick layer over a still outer ring. `#b2`
  ("Split-Arc Ring") **counter-rotates** two arc rings — inner one way while shrinking, outer
  the opposite way and faster while fading in. `#b7` ("Gear Dial") has a dense tick ring doing
  one smooth 360° turn against 4 cardinal ticks ratcheting the opposite way in 3 uneven steps
  (135°→225°→90°, each its own duration/easing). No design is a single transformed group —
  that was the first (wrong) pass here.
- **For Framer Motion**: this maps naturally to nested `motion.g`/`motion.circle` elements each
  with their own `animate`/`transition` (different `duration`, `ease`, and rotation direction
  per layer) inside one SVG, rather than one `motion.svg` wrapper transform — consistent with
  how `Core.jsx` already nests multiple `motion.*` elements for its own ring dial.
- **Colors confirmed against `themes.js`** (not approximated): dark theme — cyan `#06b6d4`,
  magenta `#ec4899`, amber/env `#eab308`, background `#0d1117`.

---

## Shape vocabulary — the animation *is* the semantics

Each shape already encodes a different system behaviour. They are **not interchangeable skins**.
Assign the meaning, then pick the shape:

| Shape | Its real motion | Meaning it carries |
|---|---|---|
| **Compass Ring** (`#b1`) | tick layer pulses radius outward, spins, bounce-settles | **acquire / lock** — presence found, scan resolved, a state changed |
| **Split-Arc Ring** (`#b2`) | two arcs counter-rotate, outer fades in faster | **handshake / sync** — request in flight, backend reachability, relay |
| **Gear Dial** (`#b7`) | dense ring one smooth turn vs. 4 ticks ratcheting in 3 uneven steps | **process / compute** — rule engine, inference, background work |

The remaining five (Scanner Arc `#b3`, Sensor Ring `#b5`, Node Ring `#b6`, Quad Reticle `#b8`,
Iris Ring `#b9`) are **identity shapes** — they distinguish one launcher/menu item from another.
They do not carry a system meaning and should not be used for loaders or indicators.

## The shared state machine

One state machine makes the same component usable as a button, a loader *and* an indicator:

```
idle      → base ring low opacity, layers drifting at ~5x the shape's own tempo
working   → anim layers loop at the shape's authored tempo (indeterminate, seamless)
resolve   → one-shot bounce-settle, then back into the idle-speed drift
active    → magenta + corner brackets held, layers drifting at ~2.4x tempo
fault     → amber, ticks frozen mid-travel — the ONLY state with no motion
```

**The bounce is a "done", not a "click".** The settle reads as a thing landing, so its home is
the end of a loader or the moment real state changes — not a tap acknowledgement. Every use
below fires the bounce off real data.

## Three discipline rules (non-negotiable)

1. **A ring is never still.** `idle` and `active` run the same motion as `working`, just
   slowed down (idle ~5x slower, active ~2.4x); `fault` is the only frozen state. Reversed
   2026-09-20 from "at rest, nothing spins" — see the §7.5 status note above for why that
   was wrong in practice, not just in principle.
2. **At most one ring animating at its *working* tempo per region.** The idle/active drift is
   ambient and deliberately easy to miss; a screen where several rings are all spinning at
   full `working` speed at once reads as a screensaver, not a HUD.
3. **No two rings in the same *set of choices* share a shape.** Launchers, menu items and
   tiles must each be distinct — being learnable by silhouette is the point. Sharpened
   2026-09-20 from "in the same view", which was too strict: a type-coded list or orbit
   repeats a shape on purpose (every online device is a Split-Arc), and a launcher may
   deliberately echo the shape of what it opens (Container Health wears the Gear Dial its
   own container satellites wear). What is forbidden is two *different choices* that a
   person has to tell apart looking the same.

## Two correctness rules (both surfaces)

- **Independently animated layers**, never one wrapper transform on the group. The
  counter-rotation is what sells the effect.
- **Angles accumulate, they are never reset.** Each layer owns one persistent rotation value
  across every state change; a state change changes its RATE, never its position. A whole
  turn is folded away as it completes (subtracting/adding 360° is invisible) to keep the
  accumulator small. This replaced an earlier rule ("every keyframe ends on a 360° multiple")
  that only worked because every state was either off or a fixed-length one-shot — once
  `idle`/`active` became continuous loops, a keyframe list restarted from 0 on every state
  change would snap visibly. The bounce-settle keyframes are still authored as whole turns,
  but applied as an offset from the live angle rather than from a hardcoded 0.

---

## Attribution (carries into any implementation, PR, or commit)

Source design is **Goran Spasojevic**'s "cyber btns" CodePen (`@gorango`,
https://codepen.io/gorango/pen/vNXejK) — 8 circular HUD icon buttons (radar/reticle/gear-tick/
sensor styles), click/muted states, animated corner-bracket "selection" frame. Explored
2026-09-16 alongside two companion pens (Cyber Dial https://codepen.io/gorango/pen/bVBWmr,
SVG Glitch https://codepen.io/gorango/pen/GpYBqY) as design references for ALFR3D's
tactical/HUD aesthetic — **not literal code to copy**; everything here is a from-scratch
recreation of the visual idea.

Credit is **required**:
- A header comment atop `src/components/HudRing.jsx` naming him and linking the pen.
- A design-notes line in this repo's `README.md`.

His older Vue prototype for this project already used his corner-bracket SVG assets:
`/home/athos/Projects/Alfr3d/gorango_alfr3d_webapp/src/assets/box/` (`c1-0.svg` … `c4-2.svg`).

---

## Why this is worth building here

`service_frontend` (React) already has a concentric-ring dial in `Core.jsx` and a boot-glitch
effect in `Nexus.jsx` that independently cover most of the "cyber HUD" ground the other two
gorango pens explored. The animated rings are the piece with no existing equivalent — and the
survey below found four genuine slots, not one.

Survey findings (2026-09-19), all confirmed against the live source:

- **The Core's orbit machinery already exists and is already data-driven.** `Satellite`
  (`Core.jsx:14-38`) does polar→cartesian placement; three `motion.div` rings rotate at
  30s/60s/60s (`Core.jsx:602-695`) carrying **plain coloured dots** for online users, ALFR3D
  devices and containers. `Satellite` already accepts `children`.
- **There is no loader component of any kind.** The whole app has
  `Loader2 … animate-spin` (`Matrix.jsx:21-26`), Tailwind `animate-spin` on lucide icons, and
  plain `"Loading..."` strings (`FavoritesPanel.jsx:124`, `CalendarPanel.jsx:95`,
  `Routines.jsx:237`, `ProjectTreeViz.jsx:428`, `Profile.jsx:92`).
- **`EventStream.jsx:36-42`'s `getIcon(type)` returns bare 3×3 `div` squares.**
- **`Nexus.jsx:138-145` enumerates exactly six collapsible panels** (`timeDate, weather,
  calendar, containerHealth, projectTree, camera`) plus `favoritesOpen` — seven slots for eight
  shapes. Their only affordance today is six vertical-text edge tabs pinned to the screen edges
  (`CollapsibleSidePanel.jsx:15-57`).
- **`Matrix.jsx:104-178`** already showcases all 8 `TacticalPanel` variants side-by-side — a
  ready-made gallery slot.
- **Reduced motion has zero support.** No `prefers-reduced-motion` / `useReducedMotion` anywhere
  in `src/`.
- **`index.css:251-266`** defines `@keyframes rotate-slow` + `.ring-1/.ring-2/.ring-3` that
  **nothing references** — a second, competing ring system sitting unused in the stylesheet.

---

## Scope

### 1. The component — `src/components/HudRing.jsx`

`Core.jsx:53-313` already holds `SVGReticle`, a `motion.svg viewBox="0 0 100 100"` with six
*static* variants. `HudRing` is its animated sibling and gets its own file (the
`TacticalPanelVariant*` family is the precedent for "a set of variants as files").

```jsx
<HudRing shape="compass|splitArc|gear|scanner|sensor|node|reticle|iris"
         state="idle|working|resolve|active|fault"
         size={28} tone="cyan|magenta|amber"
         onClick={…} label="Weather" />
```

- [x] Build the three bounce shapes first: `compass`, `splitArc`, `gear`.
- [x] Each = one static base `<circle>` + **2 independently animated `motion.g` layers**.
- [x] Every rotation keyframe ends on a 360° multiple (see correctness rules).
- [x] Colors from `useTheme().themeColors` as inline values, the way `Core.jsx:340` does it —
      `primary` cyan idle, `secondary`/`magenta` active, `warning`/`env` amber fault. **No new
      theme tokens**; `themes.js` already has everything.
- [x] `onClick` renders a real `<button>`; icon-only buttons get `aria-label`. Never
      `role`/`onClick` on a `div` — Tab skips it.
- [x] `useReducedMotion()` from framer-motion → base ring + colour/opacity states only, no
      rotation, no scale.
- [x] Attribution header comment.
- [x] Add the other five identity shapes.

**Done 2026-09-20.** `src/components/HudRing.jsx` + `src/components/HudRing.test.jsx`
(8 tests). Verified in Chrome against a throwaway `/hudring` harness (since reverted) by
reading the live DOM, not by eye:

| state | what the layers actually do |
|---|---|
| idle | no transform at all, layer opacity 0.45 |
| working | rotating, and **counter-rotating** — splitArc read `-11.16deg` / `+6.87deg`, gear `-5.58deg` / `+8.12deg` |
| resolve | mid-bounce with the scale channel live (`scale(0.987) rotate(187.21deg)`), settling to exactly ±360° on **all eight** shapes |
| active | static, magenta, corner brackets present |
| fault | frozen at a fixed off-axis angle, amber |

Reduced motion was forced via a temporary `matchMedia` patch: every transform stayed `none`
and was byte-identical 1.2s apart, while colour and the bracket frame still carried the
state. `npm test` 106/106, `npm run lint` adds no new warnings, `npm run build` clean.

### Two traps found while building §1 — both apply to the Compose port too

1. **Animating a scalar `opacity` on an SVG `<g>` warns** — *"trying to animate opacity from
   undefined to 1"* — because framer writes SVG opacity as an attribute and cannot read a start
   value off it (the usual `style` fallback does not apply to `<g>`). Keyframe *arrays* carry
   their own start value, so the resolve specs never warn; only the scalar branches did. The
   shipped fix is a plain `<g style={{ opacity, transition }}>` wrapper around each `motion.g`,
   so the animated element only ever carries transform channels. An `initial` prop also
   silences it, but it puts a value on the animated element that has to stay in sync with every
   state branch — the wrapper keeps the two concerns apart.
2. **A backgrounded Chrome tab stops `requestAnimationFrame`, so every animation reads as
   `none`.** This cost real time and produced a confident but wrong mid-session conclusion —
   that `initial` had suppressed the resolve keyframes — which the awake-tab readings later
   disproved. Take a screenshot to wake the tab immediately before reading animated state from
   the DOM, and treat an all-`none` reading as a measurement failure until `rAF` is confirmed
   firing.

`prefers-reduced-motion` cannot be emulated from the Claude-in-Chrome tools, so verifying it
needs either DevTools by hand or a temporary module-scope `matchMedia` patch as used here.
A jsdom test cannot stand in: jsdom applies no transforms at all, so such a test passes
whether or not reduced motion is honoured.

### 2. Loaders and the boot sequence (build second — lowest risk, widest coverage)

- [x] **Boot sequence.** `NexusLoader` (`Nexus.jsx:43`) walks `BOOT_MESSAGES` on timers over a
      Lottie logo. Give each line a `HudRing`: `working` while it is the current line, `resolve`
      as it completes, `fault` amber for `[WARN]` lines. The fake boot log becomes a HUD
      checklist — the single most visually impressive change on the page.
- [x] **Replace every generic spinner**: `Matrix.jsx:21-26`'s `LoadingFallback`, and the plain
      `"Loading..."` strings listed in the survey above. ~~Split-Arc for anything waiting on a
      fetch, Gear Dial for anything computing.~~ **Superseded 2026-09-25 — see the amendment at
      the top of this doc: the fetch/compute split was retired, the house loader is Gear Dial
      only now.** One house loader, everywhere.
- [x] **Event stream glyphs.** Swap `EventStream.jsx:36-42`'s 3×3 `div` squares for 16px
      `HudRing`s, shape by event type. **Only the newest arrival plays `resolve`** — the stream
      is socket-driven (`socket.on('events')`), so this is live and restrained.

**Done 2026-09-20.**

- **New: `src/components/HudLoading.jsx`** — the house loader (`label`, `mode`, `size`). It is a
  `role="status" aria-live="polite"` region with the ring `aria-hidden`, so the label is read
  once instead of an unlabelled spinner being read as nothing. `fetch` → Split-Arc, `compute` →
  Gear Dial. Now used by `Matrix.jsx` (`LoadingFallback`, replacing `Loader2 animate-spin`),
  `FavoritesPanel.jsx`, `CalendarPanel.jsx`, `Routines.jsx`, `ProjectTreeViz.jsx` (compute) and
  `Profile.jsx`. The `lucide-react` `Loader2` import is gone from `Matrix.jsx`.
- **Boot checklist** — `BOOT_MESSAGES` entries gained a `shape` field, so the log is data-driven
  rather than string-sniffed. The `>` prompt (and its now-unused `promptColor`) is replaced by
  the ring. Verified live in Chrome: every completed line had settled to exactly ±360° and the
  `[WARN]` line sat frozen at the fault angles (214° / -137°) in amber, with only the current
  step in motion — rule 2 ("at most one ring animating per region") holds for free here.
- **Event stream** — `getIcon` became a `RING` map. Deliberately uses only **identity** shapes
  (success → reticle, warning → scanner + amber, audio → node, info → sensor, unknown → iris):
  every line in a log is something that already happened, so compass/splitArc/gear would misread.
  Type values confirmed against the producers (`service_device/app.py`, `service_user/app.py`,
  `service_daemon/utils/now_playing_monitor.py`), not guessed. Colour now carries severity alone
  — `audio`'s off-palette `blue-500` is gone, since shape tells it apart instead.
- **Tests**: `HudLoading.test.jsx` (3) and `EventStream.test.jsx` (4) added. The
  "only the newest bounces" test was checked against a deliberately broken component to confirm
  it actually fails — not a repeat of §1's vacuous-test mistake. Suite 113/113, lint adds no new
  warnings, build clean.
- **README** updated: boot-sequence and event-stream feature lines, a "Cyber HUD rings" bullet
  under Visual Design, and the **design credit** to Goran Spasojevic with all three pen links.

### Two things §2 changed outside its own scope

1. **`src/test/setup.js` gained a `matchMedia` polyfill.** jsdom has none, and framer-motion's
   `useReducedMotion` needs it — without it, any test that transitively renders a ring throws.
   It sits with the existing `scrollIntoView` / canvas / `WebSocket` polyfills for the same
   reason, and `HudRing.test.jsx`'s local copy was removed in favour of it.
2. **`pages/Profile.test.jsx` now renders inside `ThemeProvider`.** `HudRing` reads
   `useTheme()`, which throws by design when the provider is missing, and that test rendered
   `Profile` bare. `main.jsx` wraps the whole app in `ThemeProvider`, so the test was simply
   less faithful than the app — this makes it match. **Any component that adopts a ring must be
   rendered inside `ThemeProvider` in its tests.**

### Not done, and why

- ~~The `animate-spin` lucide icons in `ControlBlade.jsx`, `FavoriteDeviceTile.jsx`,
  `CameraStream.jsx`, `System.jsx` and `Integrations.jsx` were left alone. They are *refresh /
  power affordances* that spin while acting, not page loaders.~~
  **Wrong, corrected in §6 (2026-09-20).** That was true of three of them and false of the
  rest: `ControlBlade.jsx` had **seven** `{loading && <RefreshCw animate-spin/>}` command-in-
  flight spinners and `CameraStream.jsx` had a plain "connecting" overlay — all loaders, all
  since converted. Only the icons that spin *themselves* to show their own action is running
  (`ControlBlade`'s Fan, `System`'s Power, `Integrations`' Radar and RefreshCw) were genuinely
  affordances and still stand. The claim was made from a grep summary rather than from reading
  each call site.
- The six loader sites show `working` but never `resolve`, because each unmounts the moment its
  data lands. Giving them the settle means keeping them mounted through the transition — a
  real refactor of each call site, and worth doing only if the boot/event-stream bounces prove
  they earn it.

### 3. Live state indicators (build third)

- [x] **Upgrade the Core's orbit dots to rings.** Pass a `HudRing` as `Satellite`'s `children`.
      Users → Compass Ring (presence), ALFR3D devices → Split-Arc (reachability), containers →
      Gear Dial (compute). Tone already maps: `success`/`warning`/`error` are computed per
      satellite today (`Core.jsx:620-621`, `641`, `671-683`).
- [x] **Bounce on state change, not on render.** Keep a previous-value ref per satellite; when a
      user's presence flips, a device goes online/offline, or a container's `errors` count
      changes, that one ring plays `resolve` once. No new endpoint needed — `utils/socket.js`
      already pushes `users`, `devices`, `containers`, `iot_devices`,
      `situational_awareness`.

**Done 2026-09-20.**

- **New: `src/hooks/useSettleOnChange.js`** — answers "which of these just changed?" The socket
  re-broadcasts the *whole* list on any change, so a render proves nothing; this compares values
  per entity key. Two rules that are not incidental:
  - **An appearing key counts as an event.** `Core.jsx`'s users handler filters to
    `state === 'online'`, so somebody coming home shows up as a *new key*, never a changed one.
    Without this, presence — the most worthwhile bounce on the page — would never fire.
  - **More than 3 at once reports nothing.** A whole list landing is a bulk load (first push,
    reconnect, refetch), not a series of events. Bouncing them together would be noise and would
    break rule 2 ("at most one ring animating per region").
- **`Core.jsx`** — the three orbits now carry `HudRing`s via `Satellite`'s existing `children`
  slot, with `color`/`glowColor` set to `transparent` (the Sun/Moon satellites already did this,
  so no change to `Satellite` itself was needed). Rest states: online/healthy → `idle`;
  offline / 1 error → `fault` amber; ≥2 errors → `fault` magenta. `fault` is not an error state
  of the widget — it is the readable "stalled" frame, which is exactly what an unreachable
  device looks like.
- **Tests**: `useSettleOnChange.test.jsx` (6) and `Core.test.jsx` (4). The container
  warning-vs-critical test was checked against a deliberately broken component to confirm it
  fails. Suite 123/123, lint adds no new warnings, build clean.

### §3 reverted 2026-09-20 (same day), per explicit user feedback

> "its better now. but the cyber buttons look really odd for the 3 rings of circling
> orbs.. put those back the way they were"

The Core's three data orbits (users, devices, containers) are back to plain glowing `<div>`
dots via `Satellite`'s own `color`/`glowColor` props — exactly the pre-§3 markup, colours and
sizes (`Core.jsx`: users size 10, devices size 8, containers size 8/10/12 by error count).
**Only the orbits changed. The launcher ring (§4) keeps its `HudRing`s untouched** — the
distinction the feedback drew is silhouette buttons for a handful of controls versus a shape
for every one of many small orbiting things, and the first reads fine while the second reads
as visual noise.

Removed as dead code: `userRing`/`deviceRing`/`containerRing`/`counterSpin`/`ringState` and the
`HudRing` import's use in the three orbit blocks. **Kept, because the launcher ring still needs
it:** `useSettleOnChange` and the `HudRing` import itself — `orbitSignatures` was trimmed to
carry only launcher entries (renamed `launcherSignatures`) rather than removed outright.

`Core.test.jsx`'s "Core orbit rings" describe block was rewritten to assert the restored plain-
dot behaviour (colour and size per satellite) instead of the HudRing accessible-role assertions
it briefly had; the "Core launcher ring" block was untouched, since nothing there changed.
Suite 153/153, lint at its pre-existing 8 warnings, build clean; re-verified live against the
real dev server (not the stray `serve -s dist` static server that happens to also be listening
on :8000 on this machine — see the gotcha this surfaced, two paragraphs down).

**Gotcha this surfaced, worth keeping:** `curl localhost:8000/api/...` and a browser hitting
`localhost:8000` can silently hit a **different, unrelated process** — a plain `node serve -s
dist -l 8000` static-file server (PID owned by a different user), not this repo's Vite dev
server. It serves `index.html` for every unmatched path (SPA fallback), including `/api/*`, so
every query silently gets HTML back instead of JSON and the app hangs forever on its own boot
loader with no console error. `ps aux | grep node` / checking who actually owns the port is the
first move the next time `localhost:8000` "hangs" — the real dev server may have picked a
different port (`vite` prints "Port 8000 is in use, trying another one..." and falls back to
8001) rather than actually be broken.

### Three things §3 needed that the plan did not anticipate

1. **`HudRing` now lets an explicit `tone` outrank the state default** (`tone` defaults to
   `null`). Previously `state="fault"` hard-forced amber, which made a container with 4 errors
   indistinguishable from one with 1 — and severity is the whole reason that orbit exists.
   Backwards compatible: every existing call site either passes no tone or already passed one
   that was being honoured.
2. **Each ring counter-spins at its orbit's own rate.** A glyph riding a rotating orbit slowly
   tumbles and its ticks drift off the cardinals, which reads as decoration rather than a HUD.
   Implemented with the `rotate-slow` keyframe **already sitting unused in `index.css:251`** —
   so §6's cleanup now only needs to deal with the `.ring-1/.ring-2/.ring-3` classes, not the
   keyframe.
3. **The orbits themselves now stop under `prefers-reduced-motion`.** This is §4 territory, but
   it could not wait: leaving the orbits spinning while the counter-spin stopped would leave
   reduced-motion users with *tumbling* glyphs — worse than the dots they replaced.

### Worth knowing before §4 touches `Core.jsx`

- **`initialUsers`/`initialDevices`/`initialContainers` only seed state once.** `Core` takes
  them into `useState` and thereafter owns its own state from the socket, so changing those
  props later does nothing. A harness that wants to drive Core has to push through
  `socket.listeners.get('devices')`, the way a real message does — worth an hour saved.
- **A backgrounded Chrome tab stops `requestAnimationFrame`**, so animated state reads back as
  `none`. Take a screenshot to wake the tab immediately before reading. (Same trap as §1; it
  bit again here.)

### Not done

- **No README screenshot of the new Core.** The only way to render it without a live backend is
  a synthetic harness, and a screenshot captioned with invented device names does not belong in
  the README. Capture it against real data when the stack is up.

### 4. Orbit launchers + edge-tab removal (build fourth)

**Decided 2026-09-19: the six vertical-text edge tabs are replaced, not kept alongside.**

- [x] Add a **fourth, non-rotating** ring of launcher nodes at r≈200 (between the container
      orbit at r=80…160 and the sun at r=240), one per entry in `Nexus.jsx:138-145` plus
      `favoritesOpen`. Use the five identity shapes + the three primaries, no repeats.
- [x] An open panel's node holds `state="active"` (magenta + corner brackets) — the ring
      doubles as a live taskbar showing what's open.
- [x] **Launcher nodes are static at rest.** Only the orbit drifts. Hover spins; click
      bounce-settles *as the panel slides in*, so settle and panel entrance are one gesture.
- [x] Remove the tab render in `CollapsibleSidePanel.jsx:15-57` and the `onToggle` prop.
      `isOpen`/`onClose` and the panel body (`:59-76`) stay. **Careful:** `tabIndex` also feeds
      the panel's own `top: 80 + tabIndex*180` offset (`:67`) — that needs a replacement positioning
      rule, not a straight deletion.
- [x] **Verify all six panels are still reachable** before this lands. This is a real
      navigation change.


**Done 2026-09-20.**

- **`Core.jsx` takes a `launchers` prop** — `{ id, label, shape, isOpen, onToggle }[]` — and
  renders them on a plain, non-rotating layer at r=200. Not rotating is the point: these are
  controls, and a target that drifts is a target you have to chase.
- **`Nexus.jsx` owns the list**, built with `useMemo` off `openPanels` + `favoritesOpen`, so
  there is still exactly one source of truth for what is open. Shapes: Quick Controls →
  Split-Arc (it reaches out to devices), Time & Date → Sensor, Weather → Scanner, Calendar →
  Reticle, Container Health → **Gear Dial, the same shape its own container satellites wear**,
  Project Tree → Node, Camera → **Iris**. Compass stays reserved for presence.
- **The settle reuses `useSettleOnChange` from §3** — a panel opening is a state change like
  any other, so `launcher-<id>` joins the same signature map and the bounce lands while the
  panel slides in. Opening flares magenta *through* the bounce so the colour arrives before the
  corner brackets snap on, rather than both landing at once.
- **`HudRing` gained a `pressed` prop.** `aria-pressed` was inferred from `state === 'active'`,
  which reports *false* during the ~1s the ring spends in `resolve` — so a screen reader would
  have said "not pressed" about a panel that was open. The caller now states it.
- **`CollapsibleSidePanel` lost its tab and its `onToggle`/`tabClassName` props**, and
  `tabIndex` is renamed **`slot`** — it only ever described the vertical offset, and the old
  name both named a tab that no longer exists and shadowed the DOM attribute (the old code
  really did pass `tabIndex={tabIndex}` onto the tab element).
- **Tests**: `CollapsibleSidePanel.test.jsx` (5) and four more in `Core.test.jsx`.
  Suite 132/132, lint adds no new warnings, build clean.

### The one thing this had to add: panels can now close themselves

The tab *was* the toggle, so deleting it removed the only way to close a panel. "Click the
launcher again" is not sufficient on its own — a panel is `max-w-4xl` and can cover the Core
along with the launcher that opened it. So `CollapsibleSidePanel` now owns closing:

- a close control in the panel's own corner, wired to **`onClose`, which every call site in
  `Nexus.jsx` was already passing and the component was silently ignoring**;
- **Escape**, for when the pointer route is covered.

### Verified end to end, against a running page

jsdom cannot prove a navigation change, so this ran against a throwaway stub of the API (both
stub and dev server since stopped) with the real `Nexus` page:

- all seven launchers present as real buttons, **zero elements with `writing-mode: vertical-rl`
  left in the document** — the edge tabs are genuinely gone, not hidden;
- each of the six panels: opened from its launcher, launcher went `aria-pressed="true"`, closed
  from the panel's own control, launcher returned to `false`;
- Escape closed an open panel;
- clicking a lit launcher a second time closed its panel;
- the open panel's node rendered magenta with its four corner brackets.

**A measurement note that bit twice now:** an exit animation is not evidence in a background
tab. The first pass reported all six panels as "failed to close", because `AnimatePresence`
keeps the node mounted until its exit animation finishes and a throttled tab never runs it.
Assert against state (`aria-pressed`), not against DOM removal.

### Not done

- **No README screenshot.** Same reason as §3: rendering this without a live backend needs stub
  data, and a README image captioned with invented residents and containers would be
  misleading. Capture against the real stack.

### 5. Menu / action buttons (build last — most conventional)

- [x] **Quick Controls.** `FavoritesPanel.jsx`'s `grid grid-cols-3` of `FavoriteDeviceTile` —
      mocked on the canvas as `web-quick-controls.dc.html`.
- [x] **Matrix action bar** — mocked as `web-matrix-actions.dc.html`.
- [x] **Gallery.** Add the ring set to `Matrix.jsx:104-178` alongside the 8 `TacticalPanel`
      variants, so the vocabulary is discoverable.


**Done 2026-09-20**, with one item deliberately not built — see below.

- **Quick Controls** — `FavoriteDeviceTile.jsx` gains a state ring per tile, one shape per
  `device_type` (light → Compass, lock → Gear, climate → Sensor, media_player → Node, cover →
  Iris, switch → Reticle, fan → Scanner), matching the mockup wherever the categories line up.
  **Deviation from the mockup, on purpose:** the mockup puts the ring *in place of* the type
  icon, because its tiles are labelled by category ("Lights", "Climate"). The real tile is
  labelled with `device.name` ("Kitchen Ceiling"), so the lucide icon is the only thing saying
  what kind of device it is — dropping it would lose information. The ring takes the
  **spinner's** slot instead: it replaces a `RefreshCw animate-spin` that only ever showed one
  of four states, and now carries all four (offline → `fault`, command in flight → `working`,
  on/locked → `active`, otherwise `idle`). Icon says *what*, ring says *how it is doing*.
- **Gallery** — a "HUD Rings" section sits beside "Panel Styles" in `Matrix.jsx`'s
  Customizations tab: all eight shapes with their role and where each is used, then the five
  states with captions, then the credit to Goran Spasojevic. `RING_VOCABULARY` /
  `RING_STATES` are kept in sync with the table at the top of this document.
- **Tests**: `FavoriteDeviceTile.test.jsx` (5), `Matrix.test.jsx` (4), `Routines.test.jsx` (3).
  The offline-tone test was checked against a deliberately broken component. Suite 144/144,
  lint back to its pre-existing 8 warnings, build clean.

### The Matrix action bar was NOT built, and should not be

`web-matrix-actions.dc.html` shows a five-item "Trigger Actions" strip — Run Scene, Pause
Automations, Away Mode, Good Night, Emergency. **None of those exist.** There is no such
endpoint, no such concept in `service_api`, and the Matrix page has no action bar; it has six
tabs. Building it would mean inventing five automations and wiring them to nothing, which is
precisely the "decorative widget with no assigned purpose" this whole effort was supposed to
avoid. The board is a good *look* for an action strip that does not exist yet.

What got the rings instead is the **real** action on that page: the per-routine run button in
`Routines.jsx`. The Play triangle stays as the affordance and the ring appears only once there
is something to report — `working` in flight, `resolve` when the routine fires, `fault` when it
does not.

### A real bug the ring uncovered

`handleRun` was `try { await apiFetch(...) } catch { console.error(...) }` — and
**`apiFetch` (`utils/apiClient.js:9-30`) returns the response for any status; it only throws on
a network failure.** A 500 from the server therefore sailed through the `try` as a success, and
the user was told nothing either way. Wiring the ring to the outcome forced the question "what
*is* the outcome?", and the answer was that nothing was checking. `handleRun` now tests
`response.ok`. Worth grepping for the same shape elsewhere: any `await apiFetch(...)` inside a
`try` that treats reaching the `catch` as the only failure mode is making the same mistake.

### What was and was not verified live

Both surfaces §5 touches are behind auth (`App.jsx` gates `/matrix`, and Quick Controls needs a
signed-in user), so these were covered by jsdom tests rather than a running page. Ring
legibility at this size is not a guess, though: the 16px event-stream glyphs from §2 were
confirmed readable on screen, and these are 16-18px. Worth a glance next time the stack is up
with a real session.
### 6. Cleanup while we're in here

- [x] `index.css:251-266` — `@keyframes rotate-slow` + `.ring-1/.ring-2/.ring-3` are unused.
      Either use them for CSS-only decorative orbit layers or delete them. Don't leave a second
      competing ring system in the stylesheet.


**Done 2026-09-20.**

- **`.ring-1` / `.ring-2` / `.ring-3` deleted** from `index.css`. Nothing had ever referenced
  them. `@keyframes rotate-slow` **stays** — §3 gave it a real caller in `Core.jsx`'s
  `counterSpin()` — and now carries a comment naming that caller, so the next person to grep
  for dead CSS does not remove a keyframe that is load-bearing.
- **New: `src/utils/deviceRings.js`** — `DEVICE_RING_SHAPES` + `ringShapeForDevice()`, shared
  by `FavoriteDeviceTile` and `ControlBlade`. The mapping was a module-local const in the tile;
  as soon as the blade needed it too, one copy was the only honest option. A lock now looks
  like a lock on both surfaces.
- **`ControlBlade.jsx`: seven command spinners converted**, `CameraStream.jsx`'s connecting
  overlay converted to `HudLoading`. Both were loaders wearing a lucide icon. `RefreshCw` is
  gone from `ControlBlade`'s imports entirely and survives in `CameraStream` only as the retry
  button it always was.
- **Tests**: `deviceRings.test.js` (3), including the invariant that every device kind with a
  type icon has a ring shape. Suite 147/147, lint at its pre-existing 8 warnings, build clean.

### Where the line got drawn on spinners

Two patterns that look alike and are not:

- **A separate element that exists only to say "waiting"** → house ring or `HudLoading`. All
  converted: `Matrix`'s `LoadingFallback`, five `"Loading..."` strings, `FavoriteDeviceTile`'s
  spinner, `ControlBlade`'s seven, `CameraStream`'s connecting overlay.
- **An affordance icon that spins to show its own action is running** → left alone. The icon
  carries meaning a ring would throw away, and spinning in place is a compact, conventional
  idiom. That is `ControlBlade`'s Fan (spins because the fan is on), `System`'s Power (spins
  while restarting that service), and `Integrations`' Radar and RefreshCw.

### Not touched, and deliberately

- `.grid-nexus` (`index.css`) is a five-column Nexus layout that nothing uses. It predates all
  of this and has nothing to do with the rings, so removing it belongs to whoever is deciding
  the Nexus layout, not to a ring cleanup.
- `Nexus.jsx` passes `health={systemHealth}` to `Core`, which neither declares it in propTypes
  nor reads it — `Core` has its own `health` state from `/api/health`. Pre-existing, harmless,
  and out of scope here, but it will confuse the next reader.

### §7.5 — the drift-tier correction, shipped 2026-09-20

`HudRing.jsx`'s engine was rebuilt so `idle` and `active` loop at slowed-down tempos instead
of sitting still (see the Status note and rule 1 above). Mechanically: each layer's
rotation/scale are no longer Framer `animate` keyframe lists re-triggered per state; they are
plain numbers advanced every `useAnimationFrame` tick (`HudRingLayer`, a component per layer)
and written straight to the SVG `transform` **attribute** rather than handed to a `motion.g`'s
`style` — Framer Motion overwrites `transform-origin` from the element's own measured bbox
when it owns the transform, which is wrong for every off-centre arc/dash layer here (verified
by reproducing it in isolation before switching). The bounce-settle still runs through Framer
`animate()`, offset from the live angle rather than from 0, and hands back to the drift loop
in its `onComplete`.

- **Tests**: `HudRing.test.jsx` gained 5 (drifts at idle, drifts at active, counter-rotates at
  rest, freezes only on fault, — reduced motion moved to its own file,
  `HudRing.reducedMotion.test.jsx`, because `framer-motion` reads `prefers-reduced-motion`
  once globally on first use, so a `window.matchMedia` patch after any earlier render in the
  same file is silently ignored; mocking `useReducedMotion` directly is the only reliable way
  to exercise that branch in isolation). `EventStream.test.jsx`'s existing opacity assertion
  needed no logic change, only a read via `getAttribute('transform')` instead of
  `style.transform` to match the new attribute-based paint. Suite 153/153, lint at its
  pre-existing 8 warnings, build clean.
- **Verified in Chrome**, not just jsdom: all 40 shape×state cells rendered concentric and
  on-geometry at a forced test angle (`hudring` harness route, since reverted); live continuous
  motion is asserted in the jsdom suite instead, since a backgrounded Chrome tab suspends
  `requestAnimationFrame` and cannot demonstrate it directly.

### 7. Not planned

- [ ] SVG Glitch (`#GpYBqY`) channel-split filter — `Nexus.jsx:64-70`'s boot-glitch already
      covers this ground more simply, and there is no `<filter>` element anywhere in `src/`
      today. Revisit only if a concrete need for the literal channel-split look comes up.

---

## Agent prompt

> Copy everything below this line into a fresh agent. It is self-contained.

**Repo:** `/home/athos/Projects/Alfr3d/alfr3d` — ALFR3D backend + web frontend.
**Working dir for this task:** `services/service_frontend`.

**Read first:** this repo's `AGENTS.md` (source of truth for architecture, build/test/lint
commands, code style, git policy), then `CLAUDE.md`, then this whole todo document.

**Stack:** React 19, Vite 8 (dev server port 8000, proxies `/api` → `localhost:5001`), Tailwind
CSS v4 with a v3-style `tailwind.config.js`, `@tanstack/react-query` v5, PropTypes (not
TypeScript), Vitest + RTL. **`framer-motion ^11.18.2` and `lottie-react ^3.1.1` are already
dependencies — do not add an animation library.** No GSAP, no Snap.svg.

**Commands:**
```
cd services/service_frontend
npm run dev      # port 8000
npm test         # Vitest
npm run lint
npm run build
```

**Task:** implement the `## Scope` sections above **in numbered order** (1 → 7). Stop after
each numbered section and report, rather than doing all seven in one pass.

**Files to create:**
- `src/components/HudRing.jsx` — the component, signature in §1.

**Files to edit (in scope order):**
- `src/pages/Nexus.jsx` — `NexusLoader` boot rings (§2); launcher orbit wiring + `openPanels`
  (§4).
- `src/pages/Matrix.jsx` — `LoadingFallback` (§2); gallery entry (§5).
- `src/components/EventStream.jsx` — `getIcon` (§2).
- `src/components/Core.jsx` — `Satellite` children + per-satellite previous-value refs (§3);
  the fourth launcher ring (§4).
- `src/components/CollapsibleSidePanel.jsx` — tab removal + `tabIndex` positioning rule (§4).
- `src/components/FavoritesPanel.jsx`, `src/components/CalendarPanel.jsx`,
  `src/components/Routines.jsx`, `src/components/ProjectTreeViz.jsx`, `src/pages/Profile.jsx` —
  `"Loading..."` replacements (§2).
- `src/index.css` — unused ring CSS (§6).
- `README.md` — design-notes attribution line.

**Reuse, do not re-derive:**
- `Satellite` (`src/components/Core.jsx:14-38`) — polar→cartesian placement, already accepts
  `children`.
- `SVGReticle` (`src/components/Core.jsx:53-313`) — the existing static-reticle patterns, arc
  path syntax (`M50 10 A 40 40 0 0 1 90 50`) and generated tick loops.
- `useTheme().themeColors` (`src/utils/useTheme.js`) — never hardcode hexes.
- `utils/socket.js` — the live WebSocket; events `users`, `devices`, `containers`,
  `iot_devices`, `situational_awareness`.
- Existing CSS utilities in `src/index.css`: `.glow-primary/-alert/-warn/-success`,
  `.text-glow-primary/-alert/-warn`, `.glass`, `.glass-panel`.
- `color-mix(in srgb, var(--theme-primary) N%, transparent)` is used liberally already — safe.

**Non-negotiables:**
1. Independently animated layers per shape — never one wrapper transform on the group.
2. Every rotation keyframe ends on a 360° multiple (prevents the snap-back-to-0° bug).
3. `useReducedMotion()` wired into `HudRing`; reduced motion → **hard stop**, not a slower loop.
4. Real `<button>` / `<a href>` elements; `aria-label` on icon-only buttons.
5. Attribution to Goran Spasojevic (@gorango) + https://codepen.io/gorango/pen/vNXejK in the
   `HudRing.jsx` header comment and in `README.md`.
6. No new theme tokens — `src/utils/themes.js` already has cyan/magenta/amber for all 5 themes.
7. **Never `git commit` or `git push` without an explicit ask in that moment.** A prior approval
   does not carry forward. Leave changes in the working tree.
8. **Never include a `Co-Authored-By` trailer** in any commit message for this repo.

**Verification (run these, report real output):**
1. `npm run dev` → Nexus loads; boot sequence rings step and settle per `BOOT_MESSAGES` line.
2. Core orbits render rings, not dots. Push a `devices` event over the WebSocket (or toggle a
   device offline in the backend) → that one satellite bounce-settles, nothing else moves.
3. Click each launcher node → its `CollapsibleSidePanel` opens, node goes magenta + brackets;
   click again → closes, node returns to idle. **All six panels reachable.**
4. Emit an event → only the newest `EventStream` glyph bounces.
5. DevTools → Rendering → "Emulate prefers-reduced-motion: reduce" → all rings static, colour
   and opacity states still readable.
6. `npm test` and `npm run lint` clean.
7. Screenshot the Nexus page and the boot sequence; add to `README.md` per `CLAUDE.md`'s
   standing rule. Use this session's own screenshots — do not reuse stale ones.

---

## Related

- `alfr3d_deck/todo/todo_cyber_hud_widgets.md` (companion repo) — the parallel Compose port for
  the Socket radial menu and the Deck's loading vocabulary. Same shape table, same state
  machine, same attribution requirement.
