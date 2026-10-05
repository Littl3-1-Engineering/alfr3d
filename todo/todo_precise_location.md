# Precise (fine) device location -- opt-in tier on top of coarse reporting

## Status: not started (added 2026-10-04); cross-repo, mirrored in `alfr3d_deck/todo/`

Follow-up to [[todo_device_location_reporting]], which shipped coarse-only,
foreground-captured, opt-in reporting and explicitly parked fine location as "a privacy cost
with no SA payoff at this stage". Real data now shows the payoff -- and the cost of not having it.

## Why (evidence, production `device_location_history`, 2026-09-11 -> 10-04)

608 fixes / 24 days / 3 installs. Android's coarse permission clamps `accuracy_m` to ~2000 m on
**every** fix (provider `network`, `gps` and `fused` alike), so the fixes collapse onto **22
distinct coordinates**, and three adjacent cells within ~1.7 km of home hold 567 of them.
Consequences observed:

- Everything within ~2 km of home is one "home" blob. The owner's regular weekday-evening outdoor
  window (~17:30-19:30) is invisible unless the trip exceeds ~3 km (4 of ~10 weekday evenings
  showed it); a local walk never does.
- "Home 09-17" cannot be told apart from "somewhere within 2 km" -- weekend daytime looks
  home-bound on 4 of 6 weekends, which does not match the owner's own account of being out.
- The `user/left_area`/`entered_area` geofence had to ship with a 3,000 m radius
  (`_HOME_GEOFENCE_RADIUS_M`) purely to survive the 2 km clamp. Only 9 events in 3+ weeks.
- No dwell/route/place inference is possible below ~2 km, which is where most daily movement is.

What coarse **did** deliver: real trips >=4 km (e.g. 2026-09-20 ~75 km, 2026-10-03 ~19 km with a
1 h dwell) and a rough sleep/wake estimate from fix density. Keep it as the default tier.

## Design

### 1. A second, separate opt-in tier -- default OFF

- New Settings toggle **"Precise location"**, independent of the existing coarse-reporting toggle
  and only enable-able while that one is on. Plain-language text: what changes (street-level
  instead of ~2 km), that it is still foreground-only, and that it only ever goes to the owner's
  own backend. No capture of precise fixes before both the toggle and the runtime grant.
- Manifest: add `ACCESS_FINE_LOCATION` next to the existing `ACCESS_COARSE_LOCATION`. **Still no
  `ACCESS_BACKGROUND_LOCATION`** -- the Play-review gate stays out of scope here.
- Android 12+ lets the user downgrade the grant to "Approximate" in the system dialog. Handle it:
  detect the downgrade (fix `accuracy_m` stays ~2000 / permission check) and show the toggle as
  "granted approximate only" rather than silently reporting coarse data as precise.

### 2. Capture -- same foreground model, finer provider order

Keep `MainActivity.onResume()` last-known-first (coarse Phase 0 found it reliably 3-6 min fresh).
For precise tier prefer `GPS_PROVIDER`/`FUSED` fine fix, fall back to `NETWORK`. Foreground-only
means **density does not improve** (~25 fixes/day today) -- precise fixes sharpen *where*, not
*when*. Whether that is enough is a Phase 0 question below, not an assumption.

### 3. Backend -- stop hard-coding the coarse assumption

- `accuracy_m` is already stored per fix; add nothing to the schema unless Phase 0 needs a tier
  marker (derive tier from `accuracy_m` first -- a fix with `accuracy_m` <= ~100 *is* precise).
- `_HOME_GEOFENCE_RADIUS_M = 3000` exists only because of the clamp. Make the radius
  accuracy-aware per fix (e.g. `max(150-300 m, k * accuracy_m)`) so a precise client gets a tight
  home/away boundary while a coarse client keeps today's behaviour. Existing
  `distance +/- accuracy_m` classification already supports this; the constant is the blocker.
  Re-run against the real 608-fix history for the coarse case (must not regress) -- the
  2026-09-11 radius bug shipped precisely by not doing this.
- Multi-device households: tiers are per `client_install_id`, as the geofence state already is.

### 4. Privacy & consent surfaces (the real cost)

- `PRIVACY.md` / `README` / onboarding opt-in copy: precise location is a materially more
  sensitive claim than the current "approximate" wording. Rewrite, don't append.
- `docs/PLAY_DATA_SAFETY.md`: Play distinguishes **precise** from **approximate** location in the
  data-safety form -- the human submission (still owed for coarse) must declare both.
- **Retention decision (open):** coarse history keeps 730 d with the other SA tables
  ([[todo_sa_data_retention_3yr]]). Street-level history for 2 years is a different risk. Options:
  shorter raw retention (e.g. 90 d), or downsample old precise rows to a ~2 km grid server-side and
  keep that. Decide before any precise row is stored in production.

## Phase 0 -- before writing code

1. On-device: does a fine fix come back reliably in the foreground, how stale is last-known when
   only fine-capable, and what is real `accuracy_m` indoors vs outdoors? (Coarse Phase 0 found
   `getCurrentLocation` timing out indoors; do not assume fine is better there.)
2. Density: a week of precise fixes -- is foreground-only coverage enough to see an evening walk
   (the 17:30-19:30 window) as a distinct dwell/route, or only its endpoints?
3. Battery/permission-dialog behaviour on Android 12+ approximate-downgrade.
4. Decide the retention question above with the owner.

Go/no-go on Phase 0 evidence: if precise-but-sparse still can't resolve the evening window, the
real fix is the background-location upgrade (own todo, Play review), not more foreground tuning.

## Downstream SA consumers (deferred, each its own follow-up)

Not part of this todo -- listed because they are *why*, and because one constraint must be
designed in from the start:

- Dwell clustering -> "known places"; walk/outing detection; true routing origin for
  `check_travel()`; tighter `entered_area`/`left_area`.
- **Learned places must expire.** Concrete case from this very dataset: four weekday mornings
  (09-11, 09-15, 09-24, 09-25, ~07:50-08:12, always the same cell 13.6 km WSW of home) looked like
  a solid recurring destination -- it was a kindergarten drop-off that has since ended. A place
  with no visits for N weeks must retire (and any card/anomaly built on it must stop firing), and
  places must never be hard-coded with a meaning the system inferred on its own.

## Related

[[todo_device_location_reporting]], [[todo_departure_anomaly]], [[todo_leave_by_demo]],
[[todo_sa_data_retention_3yr]], [[todo_play_store_launch_polish]].
