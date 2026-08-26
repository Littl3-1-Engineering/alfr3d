# ALFR3D Self-Awareness: Pronounce Its Own Name + Don't Greet Itself

## Status: 🔴 Not started

## Overview

Two small, related bugs around ALFR3D's own identity:

1. **Pronunciation**: when ALFR3D says its own name in a TTS message (e.g. "ALFR3D just
   started", any personality/LLM-generated line that includes the literal string), the TTS
   engine reads the leetspeak `alfr3d` literally instead of pronouncing it "Alfred."
2. **Self-greeting**: `alfr3d` also exists as a row in the `user`/`user_types` tables (used for
   device/system attribution), and when that "user" transitions offline→online it currently
   triggers the same welcome-greeting flow as a real household member — ALFR3D ends up
   announcing itself coming online, like it's a guest.

## Current State (confirmed 2026-08-26)

### 1. TTS pronunciation
- Entry point: `services/service_speak/app.py:329` `process_speak_message()` receives the raw
  text from the Kafka `speak` topic, optionally rewrites it via personality/LLM (lines 366-398),
  then calls `generate_tts(text, engine, model, speaker, speaker_wav)` at `app.py:401` — the last
  point before text reaches the TTS engine, and the natural insertion point for a phonetic
  substitution pass.
- `generate_tts()` (`app.py:253-326`) passes `text` straight into either Coqui TTS
  (`tts_instance.tts_to_file(text=...)`, lines 277-300, XTTS v2, lazy-imported) or gTTS
  (`gTTS(text=text, lang="en", tld="co.uk", slow=False)`, line 317) with **zero normalization** —
  no phonetic dictionary, no SSML anywhere in the file or repo.
- `personality.py:242` `track_speak_text()` does a `.strip().lower()`, but only for repeat-message
  dedup detection — unrelated to pronunciation, not reusable for this.

### 2. Self-greeting
- `services/service_user/app.py:445` `refresh_all()` runs `SELECT * FROM user;` (line 458, no
  exclusion filter) and calls `update_user_state()` for every row (lines 486-488).
- `update_user_state()` (`app.py:320-360+`): on offline→online transition (`user[5] ==
  stat["offline"]`, line 336) it sends a Kafka `speak` event ("just came online", line 339) *and*
  calls `speak_welcome(producer, user[1], usr_type[1], user[6])` (line 355), which builds a
  personalized welcome message and publishes it to the `speak` topic (`speak_welcome`,
  `app.py:393-441`).
- `setup/createTables.sql:321,323`: `user_types` seeds an `'alfr3d'` type (id 5) and
  `device_types` seeds an `'alfr3d'` type (id 1) — the schema anticipates ALFR3D itself having a
  `user` row (for device/system attribution), distinct from the `unknown` (id 2) placeholder.
- **Existing exclusion precedent already in the codebase**, just not applied here:
  `services/service_api/routes/devices.py:49` and `services/service_api/dependencies.py:282`
  both filter `WHERE u.username NOT IN ('unknown', 'alfr3d')` when listing device-owning users.
  `update_user_state()`/`refresh_all()` in `service_user/app.py` has no equivalent filter today.

## Design (sketch — needs scoping pass before implementation)

1. **Pronunciation fix** (`service_speak/app.py`): add a small phonetic-substitution step right
   before `generate_tts()` is called in `process_speak_message()` (~line 401) — word-boundary-safe,
   case-insensitive replace of `alfr3d` → `Alfred` (regex `\balfr3d\b`, re.IGNORECASE, preserving
   surrounding punctuation). Keep it a single small helper (e.g. `normalize_pronunciation(text)`)
   rather than a general text-normalization framework — no other pronunciation issues are known
   today, don't build a phonetic-dictionary system for one word.
2. **Self-greeting fix** (`service_user/app.py`): skip the greeting path for the `alfr3d` user,
   reusing the `NOT IN ('unknown', 'alfr3d')` precedent from `devices.py:49`. Two possible
   insertion points — decide during implementation:
   - Filter it out of the `SELECT * FROM user` in `refresh_all()` (line 458) — simplest, but would
     also stop tracking/updating the `alfr3d` user's own online/offline `state` column, which
     other code may depend on (needs check before choosing this).
   - Or keep state tracking as-is but guard the `speak`/`speak_welcome` calls inside
     `update_user_state()` (lines 339, 355) with `if user[1] != "alfr3d":` — narrower, only
     suppresses the announcement, not the state row update. Likely the safer default.

## Open Questions

- Should the plain `"<name> just came online"` Kafka `speak` send (line 339) also be suppressed
  for `alfr3d`, or only the personalized `speak_welcome()` call (line 355)? Both currently fire on
  the same transition — probably both should be suppressed together since they're the same event.
- Is `alfr3d`'s `user.state` column (online/offline) read anywhere else (dashboards, situational
  awareness) such that skipping its state update in `refresh_all()` would break something? Needs a
  grep before picking the `refresh_all()`-filter vs `update_user_state()`-guard approach above.
- Are there other places besides `service_speak` that construct TTS text and could also emit the
  literal string `alfr3d` (e.g. `service_daemon` quips, routine names)? If `process_speak_message()`
  is the single funnel point for all TTS output (per Kafka `speak` topic architecture), one fix
  there should cover all callers — confirm this is actually the only path to `generate_tts()`.

## Related

- `todo_auth_rbac.md`, `todo_user_management.md` — own the `user`/`user_types` schema and role
  model this todo's `alfr3d` user row lives inside; not modifying permissions here, just presence
  behavior.
