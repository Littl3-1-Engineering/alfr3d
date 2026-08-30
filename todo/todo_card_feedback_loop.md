# SA-1: Card feedback loop & suppression

## Status: 🟢 Backend + React dashboard built and live-verified 2026-08-29; Android launcher reporting not started; deployed to production 2026-08-30

**Deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to `main`). A real
`mysqldump` backup was taken first; migrations applied cleanly through 0035; affected services
rebuilt and redeployed; verified live with a clean cycle and a real authenticated API response.

Wave 1 of the situational-awareness expansion, following [[todo_household_event_log]] (SA-11)
and [[todo_attention_telemetry_history]] (SA-2). The only item on the list that improves the 16
rules already shipped rather than adding a new one.

## Phase 0 findings

- Cards flow `alfr3ddaemon.publish_sa()` → Kafka `situational-awareness` topic →
  `service_api`'s `consume_sa()` → `recent_sa` (cleared before every publish, not accumulated) →
  WebSocket broadcast → React's `SituationalAwareness.jsx` (`MAX_DISPLAY_CARDS = 9` client-side
  truncation) and the Nexus Launcher (not touched this session — see below). Neither surface had
  any prior notion of card identity across cycles.
- **Identity key is `(rule_id, subject_key)`, not `(mode, content_hash)`.** Two findings drove
  this:
  1. The card's own `"mode"` field collides across rules: `check_gatherings` (rule id `"music"`)
     and `check_now_playing` (rule id `"now_playing"`) both stamp `"mode": "music"` on their
     card. `DISPLAY_RULES`' own id is the thing that's actually unique per check.
  2. A pure content hash fragments identity for content that legitimately changes every cycle
     without being a "new" thing worth separate suppression state — `now_playing`'s content
     changes every track; dismissing "now playing" should mean "stop telling me what's playing
     for a while," not "I've seen this exact track's card before." So most rules are
     **singleton** — `subject_key = ""`, one suppressible slot per rule regardless of content.
     Only `rhythm_break_anomaly` (a specific device is overdue → `entity_name`) and
     `cross_surface_continuity` (a specific session to resume → `resume_type:resume_target`) get
     a real per-entity `subject_key`, via `CARD_SUBJECT_KEY_EXTRACTORS` — dismissing one device's
     card must not suppress a different device's.
- `check_party_advisory`'s existing cooldown (`PARTY_ADVISORY_COOLDOWN_MINUTES`,
  `PARTY_ADVISORY_LAST_NUDGE_TIME`) is **not a reusable pattern** — confirmed by reading it: it's
  an in-memory (not persisted, resets on restart), TTS-nudge-only gate that never suppresses the
  *card* itself (the card "refreshes every cycle like any other display" per its own docstring).
  SA-1 needed a persistent, per-card-identity, interaction-driven mechanism — a different shape
  entirely — so a new one was built rather than generalizing this one-off.
- Next-free migration number confirmed as **0031** at write time (the task doc's own "0027" was
  stale — SA-11/SA-2 had already taken 0028-0030 this session).
- `"context": {"*": _TECHNOKING_AND_RESIDENT}` in `auth/permissions.py` already wildcard-covers
  any action name under the `context` resource, so the new endpoint needed no new permissions
  entry.

## Phase 1 — Interaction capture

`card_interactions` (migration 0031): `rule_id`, `subject_key` (`NOT NULL DEFAULT ''`), `action`
(`ENUM('shown','tapped','dismissed','expired')`), `user_id` (nullable), `occurred_at`. Index on
`(rule_id, subject_key, occurred_at)`.

`POST /api/context/card-interaction` (`routes/context.py`) — plain INSERT, `require_permission
("context", "card_interaction")`. `shown` must be reported by the consumer only after actually
rendering the card (i.e. after `MAX_DISPLAY_CARDS` truncation) — never assumed by the daemon,
which has no way to know a truncated-away card's fate.

`decide_displays()` now stamps `rule_id`/`subject_key` onto every card it returns (new,
required) so consumers have something reliable to report against — the raw `"mode"` field isn't
enough given the collision above.

## Phase 2 — Suppression

Added to `decide_displays()`, after collection, before the sort:
- `card.get("urgent")` short-circuits straight past suppression entirely — no query, no
  cooldown, no repetition check. `household_composition`'s elevated variant (unrecognized
  device on the network) is the only rule using this today, but it's a generic field check, not
  a hardcoded rule-id allowlist, so any future rule can opt in the same way.
- **Cooldown**: if the identity's most recent `card_interactions` row is `dismissed` and inside
  `CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES` (60, per-rule override dict provided but empty for
  now), suppress.
- **Repetition damping**: count the unbroken run of `shown` rows from the most recent row
  backward (a `tapped`/`dismissed` breaks the run) — `>= CARD_SUPPRESSION_DEFAULT_REPETITION_
  CYCLES` (20) suppresses until a real interaction or a state change resets it.
- One query per card (`SELECT ... ORDER BY occurred_at DESC LIMIT 10`), reading only —
  `card_interactions` is never written by the daemon, only by consumers.
- Every suppression logs `logger.info(f"Suppressing {rule_id} card (subject={subject_key!r}):
  {reason}")`.

23 new daemon tests (`TestCardSuppression`, subclasses `TestDecideDisplays` to reuse its stub
helper/CARD constants): subject-key extraction per rule, cooldown/repetition/db-error paths, a
tap resetting the repetition run, the urgent override (including that it never even queries),
the ambient (non-urgent) household_composition variant still suppressing normally, and two
different `rhythm_break_anomaly` entities having independent suppression state.

**Blast-radius note**: every existing `TestDecideDisplays` test needed `pymysql.connect` mocked
once `decide_displays()` started making real DB queries — without it, an unmocked real-network
`pymysql.connect()` call hung the whole test file for the default timeout instead of raising.
Fixed with one class-level `autouse` fixture (`_no_card_interaction_history`, defaults to no
history / never suppress) rather than touching all ten pre-existing tests individually.

## React dashboard (Phase 1's "both surfaces report")

`SituationalAwareness.jsx`: `cardKey(card)` = `${rule_id}:${subject_key}` (falls back to `mode`
alone for a card from a backend that predates this stamping). Reports `shown` once per card per
broadcast (effect keyed on the `saData` array reference — a new fetch/socket push, not a
re-render) for whatever's in the top `MAX_DISPLAY_CARDS`, independent of local dismiss state. A
new "×" dismiss button (hidden for `urgent` cards, matching the backend's own never-suppress
rule) reports `dismissed` and hides the card locally immediately, without waiting for the next
server push. 4 new Vitest tests (shown reporting, `mode`-fallback identity, dismiss hides +
reports, urgent card has no dismiss button) — 15/15 passing, ESLint clean.

## Live verification (2026-08-29, real docker-compose stack)

- Ran `alembic upgrade head` (0030 → 0031) against the live dev MySQL; confirmed schema.
- Rebuilt and recreated `service-api`, `service-daemon`, and `service-frontend` with the new
  code.
- A real published cycle showed every card carrying its `rule_id`/`subject_key` stamp, including
  a live `cross_surface_continuity` card with `subject_key: 'routine:Sunrise'` — confirms the
  per-entity extractor works against real data, not just the mocked unit tests.
- Minted a real JWT, POSTed a real `dismissed` interaction for the `weather` card over HTTP,
  confirmed the row landed in `card_interactions`. Restarted the daemon and confirmed a real
  cycle logged `Suppressing weather card (subject=''): cooldown` and the published card list no
  longer contained a weather card, while `household_composition` (`urgent=True`, present every
  cycle) kept showing throughout. Cleaned up the seed row afterward.
- **Browser session against the live Nexus dashboard** (`http://localhost/`): Chrome network
  inspection showed the frontend firing one `POST /api/context/card-interaction` (`shown`) per
  visible card on each broadcast, exactly as designed. Confirmed visually: the `[TIME]` card
  carried a working "×" dismiss button; clicking it removed the card from the page immediately
  and fired an additional `dismissed` POST. The `[HOUSEHOLD_COMPOSITION]` card (urgent) correctly
  showed **no** dismiss button at all. All these requests correctly 401'd, since the browser
  session had no login token — proof the auth guard is wired, not a bug; the mechanism itself
  (report timing, card identity, dismiss-hides-immediately, urgent-exemption) is what this
  session verified, not a specific authenticated user's write ever landing from that browser.

## Not yet done

- **Android launcher (`alfr3d_deck`) reporting.** The task requires both surfaces to report;
  only the React dashboard was built this session. Same precedent as SA-2's on-device work:
  flagged as a follow-up needing its own session (Kotlin/Gradle build, a connected device). The
  Nexus Launcher's own situational-awareness card consumption path needs the same `cardKey`
  logic and a `POST /api/context/card-interaction` call on shown/dismiss/tap.
- **Phase 3 (earned priority)** — explicitly gated on ≥2 weeks of real interaction data; not
  started, per the task doc's own "do not start speculatively" instruction.
- Tuning `CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES`/`_REPETITION_CYCLES` against real
  interaction data once enough accumulates — conservative starting points today.

## Out of scope (per the task doc, unchanged)

- Any ML ranking model — counters and thresholds only.
- Cross-household aggregation — interaction data stays household-local.
- Changing `MAX_DISPLAY_CARDS` or the frontend layout.
