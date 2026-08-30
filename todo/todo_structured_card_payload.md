# SA-5: Structured card payload

## Status: 🟢 Backend built and live-verified 2026-08-29 (a real Decimal-serialization bug caught and fixed on first deploy), deployed to production 2026-08-30; Kotlin side compiles clean but unverified on a real device, still uncommitted in `alfr3d_deck`

**Backend deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to
`main`). A real `mysqldump` backup was taken first; migrations applied cleanly through 0035;
`service-daemon` rebuilt and redeployed; verified live with a clean cycle and a real
authenticated API response. **The `alfr3d_deck` launcher side was NOT part of this deploy** --
that change lives only in `alfr3d_deck`'s own working tree (uncommitted), separate from this
repo's git history entirely. See that repo's `agents.md` 2026-08-30 entry.

Wave 2 of the situational-awareness expansion, following [[todo_context_frame]] (SA-4). Gives
every situational-awareness card an additive `data` dict alongside its existing prose `content`,
so consumers that need a real value (a number, a boolean, a specific name) stop having to regex
it back out of a sentence meant for a human/TTS to read.

## Phase 0 findings

- Every one of the 16 `DISPLAY_RULES` rules in `alfr3ddaemon.py` already computes its underlying
  facts before formatting them into `content` — the facts were never missing, just discarded once
  folded into prose. No new backend computation was needed anywhere; this phase is pure
  plumbing/exposure, like SA-4.
- The Android launcher (`alfr3d_deck`) already has exactly this problem, live, in
  `MusicEnergy.parseAlfr3dSignal()`: it regexes `card.content` for `energy=([0-9.]+)` and a
  `(genre, energy` group to recover the two numbers `check_gatherings()` had computed all along.
  This is the concrete motivating case for the whole feature, not a hypothetical.
- `SituationalInsights.kt`'s other seven mode-specific parsers (`mood`, `focus_needed`,
  `weather_advisory`, `household_composition`, `rhythm_break_anomaly`, `cross_surface_continuity`,
  `attention_focus`, `wind_down_signal`) mostly display `content` verbatim by design — their own
  doc comments say so explicitly ("no fixed shape to regex-parse... degrades to showing it
  verbatim"). Migrating them to consume `data` is real future value but out of scope for this
  pass, which targets the one launcher consumer that actually extracts a number today
  ([[todo_structured_card_payload]] Phase 2 below); flagged, not built.

## Phase 1 — backend `data`/`data.because` fields

Every `check_*` rule's return dict gains an optional `data` key: a per-mode dict of facts that
were previously only visible inside `content`'s prose. Design rule, held to for all 16 rules:
**pre-existing top-level fields are never retroactively moved into `data`** — `playlist_*`,
`confidence`, `conference_uri`, `entity_name`, `resume_type`/`resume_target`, `switch_count`,
`unlock_count`, `known_count`/`unknown_count`/`urgent`, `device_count`, `track_title`/
`track_artist`/`is_playing` all stay exactly where they already were. `data` only ever adds new
facts a consumer couldn't get any other way; zero behavior change for any existing consumer,
verified empirically — only 1 of ~195 daemon tests needed updating (an exact-dict-equality
assertion) after touching all 16 rules.

`data.because` — an optional evidence list (e.g. `["3 guest(s) online", "evening time of day"]`)
— was added to most rules alongside their other `data` facts, cheap to add while touching every
rule anyway. Doubles as human-readable justification for [[todo_card_feedback_loop]]'s (SA-1)
suppression data, making a suppressed card's reasoning inspectable rather than opaque.

A new module-comment block directly above `DISPLAY_RULES` in `alfr3ddaemon.py` documents the
convention and a per-mode schema table for all 16 modes (noting `time`, `music`'s
`check_now_playing` card, `email`, and `cross_surface_continuity`'s terminal-routine candidates
carry no `data` — nothing new to expose beyond their existing top-level fields).

## Phase 2 — Kotlin launcher migration (`alfr3d_deck`)

Threaded `data` through the one real Android consumer identified in Phase 0:

- `SituationalAwarenessCard` (`alfr3d/model/Alfr3dModels.kt`) and `SituationalSignal`
  (`contextawareness/ContextAwareness.kt`) each gain a nullable `data: org.json.JSONObject?` —
  kept as a raw pass-through rather than flattened into typed fields, since its shape is
  heterogeneous by mode and only one mode (`music`) has a real consumer today.
- `HttpAlfr3dClient.getSituationalAwareness()` parses it with `o.optJSONObject("data")`,
  matching the existing manual-JSON-parsing style (no Moshi/Gson in this codebase).
- `ContextSnapshotProvider`'s `situational` mapping threads `card.data` through unchanged.
- `MusicEnergy.parseAlfr3dSignal()` now prefers `data.energy`/`data.genre` over the regex
  extraction, falling back to the regex only when `data` is absent or missing those keys (an
  older backend, or some future card that stops sending them) — per the task's own instruction,
  **the regex was not deleted**, since a live device/emulator to confirm the structured path end-
  to-end isn't available in this environment (see "Not yet done").

## Phase 3 — `data.because` evidence field

Implemented concurrently with Phase 1 (see above) rather than as a separate pass — cheap to add
while touching every rule's return dict anyway. Present on every rule that has a genuine "why did
this fire" story (`music`/gatherings, `weather_advisory`, `mood`, `household_composition`,
`rhythm_break_anomaly`, `cross_surface_continuity`, `attention_focus`, `wind_down_signal`,
`empty_house_still_on`); absent where a rule's firing condition is a single obvious fact already
restated in `content` (`weather`, `event`, `focus_needed`).

## Testing

Every existing `TestCheckXXX` daemon test updated with `data`-field assertions where a rule
gained new facts (11 tests, listed in the SA-5 session's own edits); one new test class
(`TestCheckPartyAdvisory`, 5 tests) closed a pre-existing coverage gap (no dedicated class existed
before this pass touched that rule). Full suite: **406 passed, 9 skipped** (skips are
MySQL-integration tests unavailable without a live test DB, unrelated to this change),
`./lint.sh` clean across all services.

`alfr3d_deck` has no unit test directory at all (`app/src` only has `main`) — verification is
`./gradlew :app:assembleDebug`, which compiles clean with no warnings.

## Live verification (2026-08-29, real docker-compose stack)

- Rebuilt and recreated `service-daemon` with Phase 1's code. **First redeploy caught a real
  bug within one cycle**: `Situational awareness check failed: Type is not JSON serializable:
  decimal.Decimal`. Root cause: `check_gatherings()`'s guest-count query uses
  `SUM(CASE WHEN ut.type IN ('guest') THEN 1 ELSE 0 END)` — MySQL's `SUM()` returns
  `DECIMAL`/`decimal.Decimal` via pymysql, unlike `COUNT(*)` which returns a plain int. Before
  SA-5 this was harmless (`guest_count` only ever got interpolated into an f-string, and
  `str(Decimal(...))` formats fine); once SA-5 started placing `guest_count` directly into the
  card's `data` dict for `orjson.dumps()`-based Kafka publishing, the unconverted `Decimal`
  broke serialization on the very first live cycle with a real gathering (a Saturday-evening
  gathering was genuinely in progress in the household at verification time — not a synthetic
  test). Fixed by casting `guest_count`/`total_count` to `int()` at the query-result site
  (`alfr3ddaemon.py`, `check_gatherings()`); grepped the rest of the file and `context_frame.py`
  for other `SUM()`/`AVG()` aggregates feeding a `data` dict (none found — this was the only
  spot). Added a regression test (`test_guest_and_total_count_are_plain_ints_not_decimal`)
  asserting `type(...) is int` on both fields, using a `Decimal` in the mocked row so this can't
  silently regress — the pre-existing tests all mocked plain ints and didn't catch it.
- Redeployed with the fix: a full cycle logged every `Collecting displays: checking <rule>` line
  with no errors, and `Published situational awareness: [...]` showed real, correctly-shaped
  `data` dicts for every currently-firing card — including the same real gathering:
  `{'mode': 'music', ..., 'data': {'mood': 'warm indie', 'genre': 'indie / soft pop / jazz',
  'energy': 0.53, 'tempo_hint': 'medium', 'guest_count': 2, 'total_count': 3, 'time_of_day':
  'evening', 'because': [...]}, ...}`, plus `household_composition` (`data.known_names`),
  `weather` (`data.city`/`subjective_feel`/`description`/`low`/`high`), and `mood`
  (`data.day_of_week`/`time_of_day`/`energy`/`energy_label`) all present and correctly typed.
- `alfr3d_deck`: no physical device or emulator available in this environment (same constraint
  noted in [[todo_context_frame]] and earlier SA items) — compiled clean
  (`./gradlew :app:assembleDebug`), but the structured `data.energy`/`data.genre` path in
  `MusicEnergy.parseAlfr3dSignal()` has not been exercised against a real backend response
  on-device.
- Confirmed end-to-end via a JWT-authenticated `curl` through the real nginx/`service-api` path
  (`GET /api/situational-awareness`), not just the daemon's own publish log: valid JSON, every
  card intact, `data` present and correctly shaped on `household_composition`/`music`/`weather`/
  `mood` — same real gathering as above, now confirmed from the actual read path a client would
  hit, not just the Kafka publish side.

## Not yet done

- **On-device confirmation of the structured path.** Per the task's own instruction ("delete the
  regex only once the structured path is confirmed working against a live backend"), the regex
  fallback in `MusicEnergy.parseAlfr3dSignal()` stays in place — it hasn't been proven redundant
  yet, only compiled.
- **The other seven `SituationalInsights.kt` parsers** (`mood`, `focus_needed`,
  `weather_advisory`, `household_composition`, `rhythm_break_anomaly`, `cross_surface_continuity`,
  `attention_focus`, `wind_down_signal`) still parse/display `content` only — `data` is available
  to them (threaded through generically, not per-mode), but migrating each one is separate,
  unscoped work, flagged in Phase 0.
- A live end-to-end `GET /api/situational-awareness` check against the real stack for this phase
  specifically (see Live verification above).

## Out of scope (per the task doc, unchanged)

- Any change to a rule's firing logic, priority, or `content` text — this phase is additive
  exposure only.
- Flattening `data` into per-mode typed Kotlin classes — deferred until a second real consumer
  beyond `music` exists.
