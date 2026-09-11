# Deck: Periodic Device-Location Reporting (SA data-collection pipeline)

## Status: 🟢 Phases 1–3 SHIPPED to `main` + deployed to the NUC, 2026-09-10.
- **Phase 1 (backend):** `alfr3d` PR #197 merged → **deployed to NUC** (`alfr3d@192.168.2.200`):
  `mysqldump` backup taken (`backup/alfr3d_predeploy_0039_2026-09-10_15-44-48.sql`, 299 MB),
  migration `0038→0039` applied, `service-api` rebuilt, live authed smoke test lands a row.
- **Phase 2 (deck pipeline):** `alfr3d_deck` PR #29 merged to `main`.
- **Phase 3 (consent):** in #29 — Settings toggle, `PRIVACY.md`/`README`, manifest perm.
- **Onboarding opt-in + Play data-safety doc:** `alfr3d_deck` PR #30 (`docs/PLAY_DATA_SAFETY.md`
  answers the form; `LocationReportingOptIn` on the Permissions step).
- **#30 merged; density pass DONE 2026-09-10** — a real ~3h trip away from home was captured
  and reconstructed from the spike CSV: departure caught within ~8 min, return caught on the
  very next foreground touch. Full writeup in "Phase 0 findings — on-device" below.
- **Open:** Phase 4 on-device verification (swap the spike build for the merged `main` build,
  now that the density question is answered); Deck-auth headcount — **done**, see below;
  submit the Play data-safety form for real (human, in the Play Console).

Cross-repo: `alfr3d` + `alfr3d_deck`.

**Goal (this todo):** ALFR3D Deck reports its own device geolocation to the backend once per
existing deck↔backend sync window, and the backend persists it as **per-device** location
history (each track keyed by a stable Deck install id, denormalized with the reporting user
from the JWT, linkable to a `device` row later). That's the whole deliverable — a clean,
express-opt-in, attributed data pipeline. **No SA rule consumes it yet**; the
learning/inference work is explicitly deferred to the follow-ups in the last section. We
collect first so those features have real history to learn from when they're built (same
"collect early, learn later" reasoning as [[todo_attention_telemetry]] →
[[todo_attention_telemetry_history]], and the lead-time problem [[todo_departure_anomaly]]
Phase 0 had to work around).

**Ownership & consent:** the location data is a feature of the *owner's self-hosted ALFR3D
backend*, used only by that backend. It is never sent to, relayed through, or processed by
Littl3.1 Engineering or any third party — same as every other deck↔backend signal (the only
network traffic deck initiates is to the address the user configured themselves). Collection
requires an **express opt-in**: a Settings toggle (default OFF) with a plain-language
explanation of what it's for, plus the OS runtime-permission grant. Nothing is captured,
queued, or transmitted until both are in place.

**Why it matters for SA:** every presence signal ALFR3D has today is LAN-scan-derived — a
device is "home" iff arp-scan sees it on the local network ([[todo_departure_anomaly]] Phase 0
documents how noisy that is: WiFi power-save gaps, per-device reliability swings from 100%
reliable to 100% artifact). A real geofix from the phone gives us: the actual *moment* someone
leaves/arrives (not "last seen on WiFi 25 min ago"), direction/distance of travel, and a true
routing origin for `check_travel()` (today it always originates from the household coordinates —
see [[todo_self_hosted_routing]] / [[todo_leave_by_demo]]).

---

## Design decisions (settled in this plan; revisit only with a reason)

### 1. Precision & collection mode — **coarse, foreground-captured, opt-in, default OFF**

The single biggest cost here is **Android background-location policy**. `ACCESS_BACKGROUND_LOCATION`
on a Play Store app triggers a mandatory Google review: prominent-disclosure screen, a
justification form, and a demo video, with rejection risk. Deck ships on Play
([[todo_play_store_launch_polish]]) so we do **not** want that gate for v1.

**v1 approach — no background-location permission:**
- Request `ACCESS_COARSE_LOCATION` only (city-block granularity ~1–3 km is plenty for
  home/away/travel inference; fine location is a privacy cost with no SA payoff at this stage).
- Capture a fix **only while the app is in the foreground** — `MainActivity.onResume()` reads
  `getLastKnownLocation(FUSED)` and, only if that's stale (age > ~15 min), fires one active
  request (prefer `NETWORK_PROVIDER`, 20–30 s timeout, tolerate `null`). Phase 0 on-device
  showed last-known is reliably 3–6 min fresh and the active request often times out
  indoors/stationary — so last-known-first, not active-first.
- The background **sync worker does not request a fresh fix** — it just uploads whatever
  foreground-captured fix is sitting in the local queue. This is what keeps us out of
  background-location review: we never access location from the background.
- Deck is a *launcher* — it's foregrounded many times a day by definition, so foreground-only
  capture still yields a dense-enough track for departure/arrival timing.
- **Express-opt-in toggle in Settings, default OFF**, with a plain-language explanation of what
  the feature does and that the data only ever goes to the owner's own configured ALFR3D
  backend (never to Littl3.1 Engineering / any third party). Nothing is captured, queued, or
  sent until the user turns it on *and* grants the runtime permission. See §Privacy below —
  this is the first genuinely sensitive personal data deck would send off-device and the
  current PRIVACY.md makes a strong "we don't do this" promise that this feature edits.

**Upgrade path (separate future todo, not now):** true periodic background fixes via
`FusedLocationProviderClient` + `ACCESS_BACKGROUND_LOCATION` + the Play review, if foreground-only
coverage proves too sparse once we have real data to measure it against.

### 2. Location API — **platform `LocationManager`, no new dependency**

Deck has no `play-services-location` today (only `billing-ktx`). For coarse, foreground,
last-known + occasional single-shot fixes, `android.location.LocationManager` is enough and
adds zero dependencies:
- primary: `getLastKnownLocation(FUSED)` (Phase 0: reliably 3–6 min fresh);
- stale fallback: one active request on `NETWORK_PROVIDER` (Phase 0: `getCurrentLocation(FUSED)`
  timed out `null` 2/3 times indoors — don't lean on it).

GMS `FusedLocationProviderClient` is the upgrade-path choice, bundled with the background
upgrade above — it would make the active fallback more reliable but isn't worth a dependency
for v1.

### 3. Grain — **per-device, resolved to a user; NOT pre-aggregated to user**

Store one track per reporting device. The [[todo_departure_anomaly]] "aggregate to the user,
union of their claimed devices" decision does **not** transfer here: that aggregation exists
because *LAN presence is per-device unreliable* (a flaky secondary device reads "away" while
the person is home). A GPS fix is different — a phone-in-pocket track and a
tablet-left-at-home track are each individually accurate, and merging them yields a meaningless
centroid. Per-device keeps each track honest; the daemon decides "where is the person" at read
time, weighting by recency / accuracy / which device is the phone.

Per-device is also what unlocks the cases worth having:
- **Forgotten phone:** user's laptop + tablet on home WiFi, but their phone track is 40 km
  away and moving → "you may have left your phone in the car."
- **Lost phone:** phone stationary at some venue since 2am while the user's other devices came
  home.
Neither is expressible if the phone's track is pre-merged into "the user's location."

**Device identity:** MAC-matching against the arp-scan `device` table is dead on Android 10+
(randomized, app-unreadable WiFi MAC). So Deck generates a **stable install UUID** on first
run and sends it as `client_install_id` with every batch. It lives as a plain
`stringPreferencesKey` in the existing `alfr3d_settings` DataStore — **not** in
`Alfr3dAuthStore`, whose `clear()` wipes on logout and would fork the track (see Phase 0
findings). It's a device identifier, not a secret; regenerates only on reinstall/clear-data.

**User attribution is free and reliable:** the deck authenticates
(`login`/`claim`/`bootstrap` in `HttpAlfr3dClient`) and `get_current_user_optional()` puts
`user.id` (JWT `sub`) on the request. The `context` permission is already
`{"*": _TECHNOKING_AND_RESIDENT}` in `services/service_api/auth/permissions.py`, so a new
`require_permission("context", "device_location")` needs **no matrix change** and is guaranteed
an authenticated owner/resident caller. Store `user_id` denormalized on every row (cheap, and
the only person-level key we have until device-linking lands).

**`device_id` (the bridge to the arp-scan `device` row — blueprint position, camera streams,
the rest of the device model) starts NULL** and is populated later by a separate
device-linking step (see Deferred). Same "collect now, link later" staging as `device_id`
being absent doesn't block anything this todo does.

### 4. Storage — **`device_location_history`, mirroring `attention_telemetry_history`**

New `device_location_history` table (history only — no `config` "latest" singleton for v1; a
`SELECT ... ORDER BY captured_at DESC LIMIT 1` per install id is cheap and nothing needs O(1)
latest yet). Keyed by `client_install_id`; carries `user_id` (always) and `device_id`
(nullable, filled by linking later).

### 5. Offline resilience — **local queue on the deck, batch upload**

The sync worker already retries with backoff when the backend is unreachable
(`Alfr3dBackgroundSync` / `Alfr3dSyncWorker`). Location fixes captured while offline must not be
lost, so deck keeps a small **DataStore-backed bounded queue** (~50 entries, drop-oldest) —
unlike `AttentionTelemetryStore` which is deliberately in-memory, because here each dropped fix
is a real gap in the track, and fixes are captured on the foreground timeline but flushed on
the sync timeline. The endpoint accepts a **batch array** so one sync flushes the whole queue.

### 6. Cadence — **piggyback the 30-min background sync**

Upload happens inside `Alfr3dBackgroundSync.runSync()` (the "same sync window as other data"
the request asks for), after the core fetch. No new timer. Foreground capture is event-driven
(`onResume`, debounced to ~1 fix / 10 min).

---

## Phase 0 — spike (do this before writing code)

Answer against reality, not assumption (the [[todo_departure_anomaly]] / [[todo_transition_learning]]
Phase-0 discipline):

1. **Who actually runs deck signed in as a resident?** If it's only `athos` today, v1's live
   verification covers exactly one track — fine, but say so, and don't tune anything against
   n=1.
2. **Foreground-capture density.** Instrument (log only, no upload) `onResume` location grabs
   for a day on the real device. Is the resulting cadence dense enough to see a departure to
   within ~15 min? This is the go/no-go for "foreground-only" vs. needing the background
   upgrade sooner than planned.
3. **Coarse-fix quality indoors.** `NETWORK_PROVIDER` last-known at home — is accuracy_m
   consistently < ~2 km, and does it move meaningfully when you actually leave? (If network
   location is hopeless on the test device, reconsider fine location for v1.)
4. **Confirm the JWT reaches `routes/context.py`.** The attention-telemetry route uses the
   permission dep but never reads `user.id` — verify `get_current_user_optional` actually
   yields a non-None user on a real deck-authenticated request (it should; confirm). Also
   sanity-check nothing else in deck already persists a stable install id we can reuse instead
   of adding one.
5. **Play Console data-safety form.** Check exactly what declaring "Location — Approximate,
   collected, not shared, optional" requires. Confirm foreground-only coarse does **not** pull
   in the background-location review. Screenshot the form state for the PR.

### Phase 0 findings — code investigation (2026-09-10)

Done from the source; item 5 and the headcount half of 1 still need Play Console / the
production DB. Item 3 (and part of 2) answered on-device — see the on-device section below.

- **JWT → `routes/context.py` (item 4): confirmed.** `require_permission(resource, action)` in
  `services/service_api/auth/dependencies.py` *returns* the `CurrentUser` (`id`, `type`) — the
  existing context routes just bind it to `_perm` and throw it away. The new route binds it to
  `user` and reads `user.id`. No new plumbing.
- **Permission matrix: no change needed, and it does the guest-exclusion for free.**
  `permissions.py` has `"context": {"*": _TECHNOKING_AND_RESIDENT}`, and `is_allowed` resolves
  an unlisted action through the `"*"` wildcard. So `require_permission("context",
  "device_location")` → 200 for technoking/owner/resident, **401 anon, 403 guest**. A
  guest-typed user running Deck simply can't post location — which is exactly the intended
  scope (matches [[todo_departure_anomaly]]'s `ut.type IN ('owner','technoking','resident')`
  filter). Add only a `# device_location: per-device geofix history, per todo_...md` comment.
- **No existing stable install id in Deck (item 4, second half).** Grepped
  `UUID`/`randomUUID`/`ANDROID_ID`/`Settings.Secure`/`clientId` across `app/src/main` — nothing
  persists a device identity. Must add one.
- **Where the install id must NOT live:** `Alfr3dAuthStore` (the `EncryptedSharedPreferences`
  "alfr3d_auth" file) has a `clear()` that wipes everything on logout / forced-logout. An
  install id there would regenerate on every logout→login cycle and **fork the device track**.
  It identifies the *device*, not the session. Correct home: a plain
  `stringPreferencesKey("device_install_id")` in the existing **`alfr3d_settings`** DataStore
  (`Alfr3dSettingsStore`) — not cleared on logout, not cleared by the base-URL RESET path
  (only `clearBaseUrl()` removes a single key), not a secret, and already the pattern for
  every non-credential preference. No new store, no `androidx.security.crypto` needed for it
  (revises design decision #3's "encrypted store" note).
- **Deck can pre-gate client-side.** `Alfr3d.authState` (`StateFlow<Alfr3dAuthState>`) already
  exposes `isAuthenticated` and `role` (decoded from the JWT `type` claim at login). So the
  capture path can skip entirely unless
  `isAuthenticated && role in {"resident","owner","technoking"}` — never queue fixes that the
  backend would 403 anyway (e.g. signed in as a guest).
- **`ttsRelayEnabled` is the exact precedent for the toggle** — `Alfr3dSettingsStore`, default
  `false`, documented as "an opt-in additive channel, not a replacement". `locationReportingEnabled`
  is the same shape.
- **Cadence reality check:** background sync is a `PeriodicWorkRequest` at **30 min**
  (`SYNC_INTERVAL_MINUTES`), network + battery-not-low constrained, `ExistingPeriodicWorkPolicy.UPDATE`.
  `runSync()` is already self-sufficient (reads the persisted address itself, no Activity
  needed) — the location drain/upload slots in after its core-fetch block with no structural
  change.

### Phase 0 findings — on-device (2026-09-10)

Measured on a real device (ASUS Zenfone 9 / AI2202, Android 14) via a throwaway
`LocationSpikeProbe` wired into `MainActivity.onResume()` — branch `spike/device-location-phase0`
in `alfr3d_deck` (**do not merge**; delete after). Deck granted `ACCESS_COARSE_LOCATION` only,
via `adb pm grant`. `dumpsys location` baseline: GPS raw `hAcc≈3.8 m`, network `hAcc≈100 m`,
GPS provider request `OFF` (nothing driving it).

- **Coarse permission hard-clamps every fix to a ~2 km grid.** network, gps, fused, and a fresh
  `getCurrentLocation` all came back `acc=2000 m`, including the GPS last-known that was 3.8 m
  raw. Consecutive reads at one physical spot landed in **different grid cells ~2 km apart**
  (network vs fused: `43.64,-79.60` vs `43.66,-79.60`). → Enough for home/away, travel origin,
  and forgotten/lost-phone ("home" vs "40 km away"); **not** enough for driveway-precision
  "just left". FINE is not needed for any stated SA goal. Any server-side geofence needs a wide
  band (~3 km) + require N consecutive reads to flip home↔away, or the 2 km jitter will flap it.
- **`getLastKnownLocation(FUSED)` is the reliable capture path.** Returned a **3–6 min old**
  fix on every one of 5 probes, with zero active request from us — other apps (weather widget,
  GMS) keep fused location warm. `NETWORK_PROVIDER` last-known was 8–11 min old; GPS last-known
  4.5 h old (only refreshed when a nav app runs).
- **`getCurrentLocation(FUSED)` active request is NOT reliable indoors/stationary.** 3 calls:
  one succeeded in **10.8 s**, two **timed out at 30 s and returned `null`**. With no provider
  actively running and a coarse-only client, GMS often can't produce a fresh fix quickly. →
  Capture logic must be: *use last-known if age < ~15 min; else fire one active request
  (prefer `NETWORK_PROVIDER`, 20–30 s timeout) and tolerate `null` — skip this capture, get the
  next one.* Never block on it; it's already async in the probe.
- **Revised design:** decision #1's "capture a fix ... `getLastKnownLocation` / a single
  `getCurrentLocation`" → last-known-first, active request only as a stale fallback. The
  DeviceLocationQueue enqueues whatever comes back (including nothing).

### Phase 0 findings — real-trip density pass (2026-09-10, item 2 resolved)

The spike (with the CSV-logging enhancement, `spike/device-location-phase0` in `alfr3d_deck`)
was left running through a normal day, then a genuine ~3-hour trip away from home. Pulled
`loc_spike.csv` afterward and reconstructed the trip from 22 foreground-triggered probe cycles
over 7h40m (13:36–21:16):

- **Both transitions were caught within one phone-use cycle.** Home through 17:39 (6 straight
  cycles at home coords); first non-home fix at **17:47** (~2 km out) — departure caught within
  ~8 min of the last home reading. Return: a **fresh (age=0) home fix at 20:47**, the very next
  time the phone was opened after walking back in.
- **The coarse grid traced the shape of a real trip**, not just binary home/away: 17:47/17:52
  ≈2 km out → 18:07 ≈4 km out → 19:45 ≈6–7 km out (the farthest reading, held steady at 20:28
  and 20:40 with `age` 4–6 min — genuinely still away, not a stale holdover) → home by 20:47.
  Away window **~17:43 → ~20:45, ≈3 hours** — matched the real trip almost exactly.
- **New finding, reverses part of the "not reliable" note above:** away from home, the active
  `getCurrentLocation` fallback succeeded *instantly* (age=0, no timeout) at both the 17:47 and
  19:45 cycles — opposite of the stationary-at-home behavior (10.8 s / null / null) from the
  first pass. A moving/traveling radio locks faster than a stationary indoor one.
- **Verdict: foreground-only, no-background-permission capture is dense enough for the stated
  SA goals** (departure timing, rough travel distance, confirming a return) — no design change
  needed, no case for the `ACCESS_BACKGROUND_LOCATION` upgrade path.

### Deck-auth headcount (2026-09-10, item 1 resolved)

Queried the production NUC DB directly: **exactly 1 user has an active refresh token** (type
`owner`). 2 non-guest users have passwords set (1 owner + 1 resident) and could sign in; 3
resident + 1 owner + 10 guest users exist total. → v1's real-world data is effectively **n=1**
until other residents sign into Deck — don't tune any downstream SA threshold against it yet.

### Still open
- **Play data-safety:** the form is drafted (`alfr3d_deck/docs/PLAY_DATA_SAFETY.md`, confirms
  approximate-foreground does **not** trigger the background-location review) but still needs a
  human to actually submit it in the Play Console and screenshot the result.
- **Phase 4 on-device verification** (below) — next.

---

## Phase 1 — backend (`alfr3d`) — ✅ BUILT 2026-09-10 (staged on branch, not deployed)

Migration verified end-to-end on the real dev DB (`alfr3d-mysql-1`): `0038 → 0039` applies
clean, `0039 → 0038` downgrade drops the table + event clean, re-upgrade works. 8 new route
tests pass (auth 401/403, bad-UUID 400, empty-batch 400, batch insert with user-from-JWT,
out-of-range/future/ancient drop, absurd-accuracy nulled-but-kept, all-bad-no-DB-call); full
`test_api_service.py` (53) green; `service_api` lint clean. Live HTTP smoke test against a
rebuilt `service-api` container: **pending** (route + migration are otherwise proven).

### Schema — done
- **No `createTables.sql` change** — recent SA tables (`attention_telemetry_history`,
  `household_events`, `card_interactions`, `geocode_cache`) all live only in the migration
  chain, not the legacy base schema. Followed that.
- `setup/migration_036_device_location_history.sql` — `CREATE TABLE IF NOT EXISTS` + the
  `cleanup_device_location_history_event` (180-day, `DELIMITER` block, same shape as
  `migration_002`'s `cleanup_device_command_history_event`).
- `setup/migrations/versions/0039_device_location_history.py` — `table_exists` guard on
  upgrade (like `0030`), `DROP EVENT` + `DROP TABLE` on downgrade. `down_revision = "0038"`,
  single head.

_Original schema sketch, as-built (DECIMAL(9,6), 3 indexes):_

```sql
CREATE TABLE `device_location_history` (
    `id`               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `client_install_id` CHAR(36) NOT NULL,            -- stable per-install UUID the deck generates; the device key
    `user_id`          INTEGER NOT NULL,              -- reporting user from the JWT (no hard FK, matches device_history)
    `device_id`        INTEGER NULL DEFAULT NULL,     -- arp-scan `device` row, once device-linking lands (see Deferred)
    `latitude`         DECIMAL(9,6) NOT NULL,
    `longitude`        DECIMAL(9,6) NOT NULL,
    `accuracy_m`       FLOAT NULL,                    -- reported horizontal accuracy, metres
    `provider`         VARCHAR(16) NULL,              -- 'network' | 'gps' | 'fused' | 'last_known'
    `source`           VARCHAR(16) NOT NULL DEFAULT 'deck',
    `captured_at`      DATETIME NOT NULL,             -- device clock at fix time
    `reported_at`      DATETIME NOT NULL,             -- server clock at ingest
    INDEX `idx_dev_loc_hist_install_captured` (`client_install_id`, `captured_at`),
    INDEX `idx_dev_loc_hist_user_captured` (`user_id`, `captured_at`),
    INDEX `idx_dev_loc_hist_reported_at` (`reported_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Retention: add a `cleanup_device_location_history_event` (or extend the existing
history-cleanup job) — `DELETE ... INTERVAL 180 DAY`, matching `device_history` retention so
downstream SA baselines see a consistent window. Note this in `PRIVACY.md` (server-side
retention is user-visible policy).

### Endpoint — done
`POST /api/context/device-location` in `services/service_api/routes/context.py`,
`user=Depends(require_permission("context", "device_location"))` (the `"context"` wildcard
covers it; **`user.id` comes from the JWT, never the body** — unlike `card-interaction`).

Payload — batch, with the device identity:
```json
{ "client_install_id": "a1b2c3d4-....",
  "fixes": [
    { "latitude": 43.6532, "longitude": -79.3832, "accuracy_m": 850.0,
      "provider": "network", "captured_at_ms": 1757500000000 }
  ] }
```
As built:
- `client_install_id` must parse as a UUID (`uuid.UUID`) → 400 otherwise; `fixes` must be a
  non-empty list → 400 otherwise.
- Per fix: `latitude`/`longitude`/`captured_at_ms` required and numeric (else that fix is
  rejected, not fatal); lat ∈ [-90,90] ∧ lon ∈ [-180,180]; `captured_at_ms` no more than 60 s
  future and not older than the 180-day retention window; `accuracy_m` outside [0, 20 000] is
  **nulled but the fix is kept**; `provider` truncated to 16 chars.
- `cursor.executemany` INSERT of the survivors (`source='deck'`, `device_id` NULL). If every
  fix was rejected, **no DB connection is opened**. Returns `{"accepted": n, "rejected": m}`.
- No `config` upsert (unlike attention-telemetry) — history-only by design decision #4.

### Tests — done
8 tests in `tests/test_api_service.py` (`_fix()` helper + `_INSTALL_ID`), following the
attention-telemetry / card-interaction layout: 401 anon, 403 guest, 400 bad-UUID, 400
empty-list, batch insert asserting `user_id` from token not body, mixed-validity batch
(1 accepted / 3 rejected), all-bad → no `db_connection` call, absurd-accuracy nulled but stored.

### Docs — done
- `AGENTS.md` `service_api` line now lists `context` + names this endpoint.
- Table list in `AGENTS.md` left alone — consistent with the other SA tables (documented in
  their todos, not there).
- `permissions.py` `"context"` entry got an explanatory comment (no functional change).
- `README.md` — not touched; it doesn't enumerate context endpoints. **Deck `PRIVACY.md` is
  the user-facing doc that still needs the retention line — Phase 3.**

---

## Phase 2 — deck (`alfr3d_deck`), core pipeline — ✅ BUILT 2026-09-10

As built (branch `feat/device-location-reporting`):
- `alfr3d/model/LocationFix.kt` — wire model (lat/lon/accuracyM/provider/capturedAtMillis).
- `contextawareness/device/LocationContextProvider.kt` — `capture()`: fresh last-known
  (FUSED/NETWORK/GPS, age < 15 min) first; else one active `NETWORK_PROVIDER`/`GPS` request via
  `requestLocationUpdates` + `suspendCancellableCoroutine`, 25 s cap, tolerates null. Plain
  `LocationManager` (no `LocationManagerCompat` — its `getCurrentLocation` overload collides).
- `alfr3d/sync/DeviceLocationQueue.kt` — DataStore (`alfr3d_location`), JSON-encoded, bounded
  50 drop-oldest, atomic `drain()`, `restore()`, `lastCaptureAtMillis`/`markCaptured` debounce.
- `contextawareness/DeviceLocationCapture.kt` — `onForeground()` from `MainActivity.onResume`;
  gates: toggle on → permission → `authState` role in {resident,owner,technoking} → 10-min
  debounce (advanced *before* the capture so failing fixes don't retry every resume).
- `alfr3d/sync/Alfr3dBackgroundSync.runSync()` — `flushDeviceLocationQueue()` after the core
  fetch (Synced branch only): drain → `Alfr3d.ensureAuthLoaded()` → `reportDeviceLocation` →
  `restore()` on failure.
- `Alfr3d.ensureAuthLoaded(context)` — new; loads persisted bearer tokens + wires
  refresh/expiry persistence without `init`'s probe loop, so the worker's POST is authed on a
  cold process. Extracted the token-attach block of `init` into `attachPersistedAuth`.
- `Alfr3dClient.reportDeviceLocation(clientInstallId, fixes)` + `HttpAlfr3dClient` impl
  (`requestWithBody`, JSONArray of fixes; empty list → no-op success).
- `Alfr3dSettingsStore` — `locationReportingEnabled` (default false, `ttsRelayEnabled` shape) +
  `deviceInstallId()` (generate-on-first-read UUID in `alfr3d_settings`).

_Original plan sketch:_

- `AndroidManifest.xml`: `<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />`
  only. Add `<uses-feature android:name="android.hardware.location.network" android:required="false" />`.
- `contextawareness/device/LocationContextProvider.kt` (new, sibling of `DeviceContextProvider.kt`):
  - `lastKnownCoarse(context): Fix?` — `LocationManager.getLastKnownLocation(NETWORK_PROVIDER)`,
    permission-checked, returns null silently when denied (same "degrade, don't crash" rule the
    rest of `contextawareness/device/` follows).
  - `requestSingleFix(context): Fix?` — `getCurrentLocation` (API 30+) / one-shot
    `requestSingleUpdate` fallback, short timeout.
  - `data class Fix(lat, lon, accuracyM, provider, capturedAtMs)`.
- **Install id:** `Alfr3dSettingsStore.deviceInstallId` — a `stringPreferencesKey` in the
  `alfr3d_settings` DataStore; generate + persist a UUID on first read. Sent as
  `client_install_id` on every batch. Survives app updates and logout, regenerates only on
  reinstall/clear-data (acceptable — a reinstall is a new track). NOT in `Alfr3dAuthStore`
  (its `clear()` wipes on logout → forked track).
- **Client-side pre-gate:** capture only when `Alfr3d.authState` has
  `isAuthenticated && role in {"resident","owner","technoking"}` — a guest-signed-in Deck would
  just get 403s.
- `alfr3d/sync/DeviceLocationQueue.kt` (new, DataStore-backed, bounded ~50, drop-oldest).
  `enqueue(Fix)`, `drain(): List<Fix>`, `restore(List<Fix>)` on upload failure.
- `MainActivity.onResume()`: if the toggle is on and permission granted, debounced (~10 min via
  a timestamp in the queue store) capture → `DeviceLocationQueue.enqueue`. Reuses the existing
  `onResume` override added for attention-telemetry unlock counting.
- `Alfr3dBackgroundSync.runSync()`: after the core fetch block, if the toggle is on, drain the
  queue and `client.reportDeviceLocation(fixes)`; on failure `restore()` the drained fixes so
  the next tick retries (mirrors the worker's own retry semantics). Gate entirely on the
  setting — zero overhead when off.
- `alfr3d/Alfr3dClient.kt` + `HttpAlfr3dClient.kt`:
  `reportDeviceLocation(clientInstallId: String, fixes: List<Fix>)`
  → `requestWithBody("/api/context/device-location", "POST", body)`, same pattern as
  `reportAttentionTelemetry`.
- `alfr3d/Alfr3dSettingsStore.kt`: `locationReportingEnabled` flow, default `false`.

---

## Phase 3 — deck, consent surface & privacy — ✅ SHIPPED 2026-09-10 (#29); onboarding + data-safety in #30

As built:
- `settings/ui/SettingsWindowContent.kt` — new `LocationReportingSection` (a `SettingsCard`
  after `BackgroundSyncSection`): off-by-default toggle; flipping on with permission ungranted
  fires the `ACCESS_COARSE_LOCATION` prompt via `rememberLauncherForActivityResult` and only
  persists `true` on grant; description states "only to the ALFR3D backend you configured —
  never to Littl3.1 Engineering". Status line covers not-configured / permission-off / on / off.
- `PRIVACY.md` — summary reworked (sell/share/developer carve-out kept tight), new "Location
  reporting" subsection, permission-table row, retention (180 d, backend-controlled), queue
  behaviour in Data retention, "Last updated" → 2026-09-10.
- `README.md` — new Location reporting bullet + Settings-tabs line.
- Manifest — `ACCESS_COARSE_LOCATION` + `location.network` uses-feature (foreground use only).
- **Onboarding opt-in (PR #30):** `OnboardingSteps.LocationReportingOptIn` — its own card on the
  Permissions step, below the special-access rows, *not* in `runtimeBundle()`. Same three-point
  copy; `ENABLE` requests the permission + sets the toggle. `README` onboarding line updated.
- **Play data-safety (PR #30):** `docs/PLAY_DATA_SAFETY.md` drafts the whole form (Location =
  approximate/collected/not-shared/optional/app-functionality; **background-location review NOT
  triggered** — `ACCESS_BACKGROUND_LOCATION` isn't declared and the sync only uploads
  foreground fixes; encrypted-in-transit = No, cleartext-to-LAN is common). `docs/PLAY_STORE_PERMISSIONS.md`
  gets an `ACCESS_COARSE_LOCATION` section. **Still needs a human to submit it in the console.**
- **Deferred:** confirm-on-enable dialog (the OS permission prompt + explicit copy is the v1 gate).
- `agents.md` §7 — gitignored in this repo; a local status note was added.

_Original plan:_

- **Settings UI** (`settings/ui/SettingsSections.kt`): a toggle **"Report my location to
  ALFR3D"**, OFF by default, with an explainer that states all of:
  - *what it does* — sends an approximate location every ~30 min so ALFR3D can learn your
    comings and goings (departures, arrivals, travel time);
  - *where it goes* — **only to the ALFR3D backend you configured**; it is never sent to
    Littl3.1 Engineering or any third party, and never used for anything but your own backend;
  - *that it's off by default and stops the moment you turn it off* — no location is collected,
    queued, or sent while off.

  Flipping it on triggers the runtime permission request; denial flips it back off. Consider a
  confirm dialog on enable that repeats the "only your backend" point (express consent, not a
  buried switch).
- **Onboarding** (`onboarding/OnboardingPermissions.kt` / `OnboardingSteps.kt`): add as an
  explicitly-optional card, *not* in `runtimeBundle()` (that batch is for
  degrade-gracefully-anyway permissions; this one is a deliberate opt-in). Copy must be a
  prominent disclosure carrying the same three points.
- **`PRIVACY.md` rewrite** — currently: *"the launcher does not collect, transmit, sell, or
  share your personal data"* and *"Everything described below is processed locally"*. This
  feature is the exception and the policy must say so plainly:
  - what's collected (approximate location) and when (only while you've enabled it, ~every
    30 min, foreground-captured);
  - where it goes — **only the self-hosted ALFR3D backend the user configured; Littl3.1
    Engineering never receives, relays, or processes it** (consistent with the existing
    "only network traffic is to the ALFR3D server address you provide" line);
  - that it's off by default and how to turn it off;
  - server-side retention (180 days, then auto-deleted) and that the owner controls their own
    backend's data.

  Add a row to the permission table (`ACCESS_COARSE_LOCATION` → "Optional location reporting to
  your ALFR3D backend, if you enable it in Settings" → "Only to the ALFR3D server address you
  provide"). Bump "Last updated".
- **`agents.md` §7 Current Status** + `README.md`: note the new capability.
- Companion **Notion page** ("Alfr3d — Overview, Monetization & Roadmap"): only if this becomes
  a publicly-stated feature/roadmap item; internal-only until then.

---

## Phase 4 — on-device verification — 🟡 IN PROGRESS

Item 5 below (does the track catch a real departure) is **already answered** by the spike-based
density pass above — a real ~3h trip was caught within ~8 min on departure and on the very next
touch on return. What's left is verifying the *real* pipeline (queue → background upload →
`device_location_history` on the NUC), not the spike's logcat/CSV stand-in. Needs the Zenfone
swapped from `spike/device-location-phase0` to the merged `main` build first.

Real device, real backend (the NUC, already running #197):
1. Toggle on, grant coarse permission — confirm a fix is captured on next `onResume`
   (adb logcat), queued in DataStore.
2. Wait out / force a background sync — confirm `device_location_history` rows land,
   `client_install_id` + `user_id` correct, `device_id` NULL, `captured_at` vs `reported_at`
   sane.
3. Airplane-mode the backend path, capture 2–3 fixes, restore connectivity — confirm the whole
   queue flushes in one batch and the queue empties.
4. Toggle off — confirm capture and upload both stop, no rows.
5. ~~Leave home for a real trip~~ — done via the spike pass above; re-confirm once the real
   pipeline is installed if a convenient trip comes up, but not required to close this phase.

Record results in this doc (the [[todo_departure_anomaly]] / [[todo_leave_by_demo]] pattern:
"built" and "live-verified" are separate checkboxes).

---

## Deferred — SA consumers (each its own follow-up, NOT this todo)

Do not build these here. Listed so the pipeline is designed to feed them:

- **Device linking** (prerequisite for several below): a step that maps `client_install_id` →
  a `device` row (`device.user_id` from the JWT already; `device_type` = resident/phone). Most
  naturally a small addition to the household-admin UI ("this Deck install → which device?") or
  an auto-create on first report. Backfills `device_location_history.device_id`. Until this
  lands, consumers key on `client_install_id` + `user_id`, which is enough for everything
  except joining to blueprint position / camera streams.
- **Forgotten / lost phone** (the case that motivated per-device): compare a user's
  per-install location tracks against each other and against LAN presence —
  phone track far from home + moving while the user's other devices are home on WiFi →
  "left phone in the car"; phone stationary at a venue overnight while other devices came home
  → "possibly lost". Needs per-device grain (this todo's design decision #3) and probably its
  own todo once there's real multi-device data.
- **[[todo_departure_anomaly]] (SA-3) enhancement:** replace / cross-check the
  `device_history` gap heuristic with a real geofence-exit time (distance from
  `environment.latitude/longitude` crossing a threshold). Aggregate per-install tracks up to
  the user the same way SA-3 already unions claimed devices — but now from accurate GPS, not
  flaky LAN presence. Much lower false-departure rate than WiFi power-save gaps.
- **[[todo_self_hosted_routing]] / `check_travel()`:** use the resident's latest fix as the
  routing **origin** instead of always originating from home — real ETA when someone's already
  out. Feeds [[todo_leave_by_demo]].
- **[[todo_transition_learning]] (SA-12):** geofence enter/exit as structured `household_events`
  (`subject_type=user`, `verb=left_area`/`entered_area`) — gives SA-12 the presence→X
  transition pairs its Phase 0b found were completely absent.
- **[[todo_generalize_entity_baselines]]:** per-user location-rhythm baselines (typical
  location by time-of-day bucket) alongside the existing device/entity baselines.
- **[[todo_context_frame]] (SA-4):** add "resident is ~Nkm from home, heading away/back" to the
  context frame the daemon and LLM prompt read.
- **[[todo_esphome_situational_awareness]]:** geofence-based arrival could pre-warm the house
  (lights/climate) — but that's actuation, explicitly out of scope until the data's proven.

## Related / precedent
- Pattern analog: [[todo_attention_telemetry]] (deck→backend periodic telemetry, `routes/context.py`,
  `requestWithBody`, own reporter) and [[todo_attention_telemetry_history]] (collect-then-learn
  with a history table).
- [[todo_departure_anomaly]] Phase 0 — the definitive writeup of why LAN presence is a poor
  departure signal; this feature exists largely to fix that.
- `services/service_daemon/utils/routing_utils.py` `fetch_home_coordinates()` — the household
  origin this data would give an alternative to.
