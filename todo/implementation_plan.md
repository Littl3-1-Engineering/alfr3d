# Implementation Plan — Ambient Experience Gaps

Priority tiers: **P0** (blocking/foundation), **P1** (high visibility), **P2** (medium), **P3** (polish)

---

## Phase 0: Design Language Foundation (P0)

These touch every component and should be done first.

### 0.1 `[DONE]` Re-theme: neural cyan primary, magenta secondary, yellow for env

> **Prerequisite:** theme management is now centralized per `todo/todo_theme_centralization.md` (COMPLETE). `src/utils/themes.js` is the single source of truth; `src/utils/themes.css` is auto-generated via `npm run generate:theme` (wired into `predev`/`prebuild`); Tailwind imports tokens from `themes.js`; the `magenta` tokens are already reserved and unused. To re-theme, edit only `themes.js` and regenerate.

Files to touch:
- `services/service_frontend/src/utils/themes.js` — redefine color palette (cyan `#06b6d4`, magenta `#ec4899`, yellow `#eab308`); then `npm run generate:theme`
- `services/service_frontend/src/utils/themes.css` — regenerated from themes.js, do not hand-edit
- `services/service_frontend/tailwind.config.js` — swap `fui-accent` from amber to cyan, add `fui-magenta`, `fui-env` tokens
- `services/service_frontend/src/index.css` — update glow/emphasis classes to use cyan (these now reference `var(--theme-*)` / `color-mix()`, so they follow the tokens automatically)

### 0.2 `[DONE]` Fix background color (deep navy/charcoal, not pure black)

- `tailwind.config.js`: `fui-bg` → `#0d1117` (GitHub-dark navy) or `#0f1923`
- Audit all `bg-fui-bg` and `bg-fui-panel` usages for contrast

---

## Phase 1: Nexus — Core Orb (P1)

### 1.1 `[DONE]` Add 24-hour clock ring with sun position marker

File: `src/components/Core.jsx`, `src/utils/timeUtils.js`

- Add a new outer SVG ring with 24 tick marks (like a watch face)
- Render a glowing dot at the current hour position (computed from `getTimeRatio()`)
- Keep the existing Sun satellite orbit as a separate visual layer
- Animate the marker smoothly via framer-motion
- **Extended:** Sun satellite now uses real Meeus solar ephemeris (`getSunAngle(date, lat, lon)` from lat/lon + timezone), and a **Moon satellite** (magenta `Moon` icon, radius 220) uses Meeus lunar ephemeris (`getMoonAngle(date, lat, lon)`). Clock ring labels `00 06 12 18`, glowing hour dot sweeping clockwise, updated every 60s.

### 1.2 `[DONE]` Core hover tooltip (uptime / version)

File: `src/components/Core.jsx`, `services/service_api/routes/health.py` (NEW)

- Add `onMouseEnter`/`onMouseLeave` state on the central Lottie container
- Fetch `GET /api/health` on hover (and on mount) — new backend endpoint returning `{ status, version, uptime_seconds, started_at, services }`; uptime parsed from `docker ps` (`alfr3d*` services, system = min), version from `VERSION` file / `ALFR3D_VERSION` env
- Show a framer-motion tooltip overlay with `SYSTEM UPTIME: XXd XXh XXm \n VERSION: x.y.z`

---

### 1.3 RTSP Camera Stream

#### 1.3.1 `[DONE]` Camera panel & backend proxy

File: `services/service_api/routes/stream.py`, `src/components/CameraStream.jsx`

- Backend: FastAPI streaming endpoint `/api/stream/camera` proxies RTSP → MJPEG via ffmpeg subprocess
- Frontend: Collapsible side panel on Nexus page with `<img>` MJPEG display
- Status indicator (connecting/connected/error), show/hide toggle, snapshot capture, reconnect button
- URL: configured via `STREAM_CAMERA_URL` env var (see `.env.example`)

#### 1.3.2 `[DONE]` Camera already in DB as device ID 79 ("C200", type "HW", IP `192.168.2.226`)

- No `/etc/hosts` needed — the device is already registered via LAN scan
- `CAMERA_URL` stays on raw IP (`192.168.2.226`) — no hostname resolution required
- Stream config displays the IP directly

---

## Phase 2: Nexus — Weather Panel (P1)

### 2.1 `[DONE]` Animated weather icon

File: `src/components/WeatherPanel.jsx` or new `WeatherIcon.jsx`

- Map `weatherData.description` (or icon code) to a Lottie animation
- Self-host Lottie JSON files for: clear-day, clear-night, partly-cloudy, cloudy, rain, snow, thunderstorm, fog
- Render via `lottie-react` next to the temperature

### 2.2 `[DONE]` Large temperature + wind speed + pressure trend arrow

File: `src/components/WeatherPanel.jsx`

- Move temperature to a large bold font (`text-5xl font-exo2`) at the top
- Add wind speed row: `WIND: 12 km/h NW`
- Add pressure trend arrow: `PRESSURE: 1013 hPa ↑` (compute arrow from recent history or API field)
- Use layout: temp+icon row → condition desc → grid of (low/high/humidity/pressure/wind/sunrise/sunset)

### 2.3 `[DONE]` Residents summary header

File: `src/pages/Nexus.jsx` (or a new `ResidentsSummary` component)

- Pass both residents and guests counts into a single header component
- Render: `RESIDENTS: 3 | GUESTS: 1` in monospace above the OnlineUsers and GuestRoster panels

---

## Phase 3: Nexus — Service Integrity (P1)

### 3.1 `[DONE]` Horizontal bar graphs for microservice health

File: `src/components/ContainerHealth.jsx`

- Replace the current dot/table layout with horizontal bars
- Each service gets a full-width bar; bar fill-width = health % (100% cyan, shrinks toward yellow/red)
- Hover tooltip shows CPU, memory, uptime
- Fetch from `GET /api/containers` (already exists)

---

## Phase 4: Domain — Blueprint & Map (P2)

### 4.1 `[DONE]` Floorplan editor (uploadable image)

File: `src/components/Blueprint.jsx`

- Add an "Upload Floorplan" button at the top of the Blueprint view
- Store the uploaded image in IndexedDB or localStorage (or POST to the API for persistence)
- If no user image exists, fall back to the current SVG
- Allow replacing/resetting image

### 4.2 `[DONE]` User location avatars on blueprint

File: `src/components/Blueprint.jsx`

- Subscribe to the `situational_awareness` or `users` WebSocket for `room` field
- If a user has a room assigned, render their avatar/initials + name on the blueprint in that room
- Show a subtle cyan glow ring around the avatar when they're home

### 4.3 `[DONE]` True List/Blueprint view toggle

File: `src/pages/Domain.jsx`

- Add a toggle button: `[ BLUEPRINT | LIST ]` using a `view` state
- List view renders a flat, searchable, room-grouped list of devices
- Blueprint view remains the current SVG + drag-drop

---

## Phase 5: Matrix — Routines (P2)

### 5.1 `[DONE]` Recipe model: WHEN → IF → THEN

File: `src/components/Routines.jsx`

- Redesign the form layout into three sections:

  **WHEN (Trigger):**
  - `time` (HH:MM) — current
  - `sunrise` / `sunset` (auto-computed from env data)
  - `person_arrives` (select user)
  - `device_turns_on` / `device_turns_off` (select device)
  - Allow OR-combination: "at 7am OR sunrise"

  **IF (Condition — optional):**
  - `person_is_home` (select user)
  - `device_state` (select device + state)
  - `temperature_above` / `temperature_below` (value)
  - `mode` (day/night/away)

  **THEN (Action):**
  - Existing: speak, device on/off, email
  - Add: `thermostat_set` (temp + mode heat/cool)
  - Add: `lock`, `cover_open`, `cover_close`

### 5.2 `[DONE]` Trigger backend support

Files: `services/service_daemon/utils/util_routines.py`, `services/service_api/routes/routines.py`

- Add sunrise/sunset computation in environment service → expose via API
- Add person-arrival event detection (user goes from offline → online)
- Add device-state-change event → match against routine conditions
- Extend routine schema in MySQL (`setup/migration_009_routines_v2.sql`) for triggers/conditions
- Extend Pydantic models in `services/service_api/models.py` with trigger/condition fields

### 5.3 `[DONE]` Thermostat action

File: `src/components/Routines.jsx` (action builder)
File: `services/service_daemon/utils/util_routines.py` (execution)

- Add "Thermostat" action button with target temp and mode
- Wire to the IoT device command API

---

## Phase 6: Matrix — Personality (P2)

### 6.1 `[DONE]` Quip categories

File: `src/components/Personality.jsx`, `src/hooks/useApi.js`

- Add a category dropdown/selector when creating/editing a quip
- Categories: `greeting`, `weather_joke`, `sarcasm`, `wisdom`, `goodbye`, `custom`
- Filter quip list by category
- Backend: add `category` column to `quips` table (migration `setup/migration_011_quip_categories.sql`)
- Expose category filter in `GET /api/quips` route

---

## Phase 7: Matrix — Integrations Logo Grid (P2)

### 7.1 `[DONE]` Logo grid with status checkmarks

File: `src/components/Integrations.jsx`

- Replace text-based list with a 3-4 column grid of cards
- Each card: service logo (SVG), service name, status badge
- Status badge: green checkmark (active), gray (not configured), red (error)
- Clicking a card opens a config modal (API key form, OAuth link)
- Services: Google, Home Assistant, SmartThings, OpenWeatherMap, Spotify

Assets needed: service logos in `public/assets/logos/`

---

## Phase 8: Matrix — System Tab (P3)

### 8.1 `[DONE]` Network / DB settings + config editor

File: `src/components/System.jsx`

- Sections with expandable cards:
  - **Network**: hostname, IP, DNS, gateway (read-only)
  - **Database**: connection status, table counts, backup button
  - **Config Editor**: embedded `<textarea>` or Monaco editor showing `/etc/alfr3d/config.json`
  - **Service Control**: restart buttons per service (POST to API)

---

## Summary by file impact

### Frontend files to create:
- `src/components/WeatherIcon.jsx` — animated weather icon `[DONE]`
- `src/components/ResidentsSummary.jsx` — residents/guests count header `[DONE]`
- `public/assets/logos/*.svg` — service logo assets for Integrations grid `[DONE]`

### Frontend files to modify:
| File | Phases |
|---|---|
| `src/utils/themes.js` | 0.1 `[DONE]` |
| `src/utils/themes.css` | 0.1 `[DONE]` (generated) |
| `tailwind.config.js` | 0.1, 0.2 `[DONE]` |
| `src/index.css` | 0.1 `[DONE]` |
| `src/components/Core.jsx` | 1.1, 1.2 `[DONE]` |
| `src/components/WeatherPanel.jsx` | 2.1, 2.2 `[DONE]` |
| `src/pages/Nexus.jsx` | 2.3 `[DONE]` |
| `src/components/ContainerHealth.jsx` | 3.1 `[DONE]` |
| `src/components/Blueprint.jsx` | 4.1, 4.2 `[DONE]` |
| `src/pages/Domain.jsx` | 4.3 `[DONE]` |
| `src/components/Routines.jsx` | 5.1, 5.3 `[DONE]` |
| `src/components/Personality.jsx` | 6.1 `[DONE]` |
| `src/components/Integrations.jsx` | 7.1 `[DONE]` |
| `src/components/System.jsx` | 8.1 `[DONE]` |

### Backend files to modify:
| File | Phases |
|---|---|
| `services/service_api/routes/routines.py` | 5.2 `[DONE]` |
| `services/service_api/models.py` | 5.2, 6.1 `[DONE]` |
| `services/service_daemon/utils/util_routines.py` | 5.2, 5.3 `[DONE]` |
| `services/service_api/routes/environment.py` | 5.2 (sunrise/sunset) `[DONE]` |
| `services/service_api/routes/quips.py` | 6.1 (category filter) `[DONE]` |
| `services/service_api/routes/integrations.py` | 7.1 (OWM config + status) `[DONE]` |
| `services/service_api/routes/system.py` | 8.1 (NEW: network/db/config/services) `[DONE]` |

### Database migrations to create:
- `setup/migration_009_routines_v2.sql` — triggers, conditions columns `[DONE]`
- `setup/migration_011_quip_categories.sql` — category column `[DONE]`
- `setup/migrations/versions/0012_quip_categories.py` — Alembic wrapper `[DONE]`
