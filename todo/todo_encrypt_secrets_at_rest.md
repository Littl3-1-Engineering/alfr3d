# Plan: Encrypt Integration Secrets at Rest

## Status: 🔲 TODO (not started — planning only)

## Goal
Every integration credential ALFR3D stores today (`ha_token`, `st_pat`, Spotify client secret,
and — once `todo_esphome.md` ships — the ESPHome per-device PSK) is plaintext in the `config` or
`smarthome_devices` tables. Encrypt these at rest so a database dump/backup leak doesn't hand out
live credentials directly.

**Why this doc exists**: raised while scoping `todo_esphome.md`'s ESPHome PSK storage (its Design
§3) — the user chose plaintext-for-v1 for the ESPHome PSK specifically (consistent with the
existing `ha_token`/`st_pat` convention, ships faster) but asked for this broader problem to be
tracked as its own scoped item rather than solved piecemeal one field at a time.

## Current state (verified in code, 2026-08-21)
- `services/common/ha_utils.py:267-277` (`save_ha_config`) — `ha_token` written plaintext via
  `UPDATE config SET value = %s WHERE name = 'ha_token'`.
- `services/common/st_utils.py` (`save_st_config`) — `st_pat` written plaintext, same pattern.
- `services/common/spotify_utils.py:64-79` (`save_spotify_credentials`) — `spotify_client_secret`
  written plaintext to the same `config` table.
- `cryptography==50.0.0` is already a dependency in `service_api` and `service_device`
  `requirements.txt` (used today only for whatever TLS/other needs pulled it in — not for any
  application-level encryption), so the primitive is already available with no new dependency.
- No env-var-backed secret-key infrastructure exists anywhere in the codebase today — this would
  be new.

## Design (sketch — needs real scoping before implementation)
- Likely mechanism: Fernet (symmetric, from `cryptography.fernet`) with a key loaded from an env
  var (e.g. `ALFR3D_SECRETS_KEY`), never committed — consistent with `AGENTS.md`'s "never modify
  `.env`, never commit secrets" rules and `.env.example`'s role as the template.
- Needs a `services/common/secrets_utils.py` (or similar) with `encrypt(value) -> str` /
  `decrypt(value) -> str`, called from every `save_*_config`/`get_*_config` pair across
  `ha_utils.py`, `st_utils.py`, `spotify_utils.py`, and (once shipped) `esphome_utils.py`.
- **Migration problem, not just a new-write problem**: existing live databases already have
  plaintext `ha_token`/`st_pat`/`spotify_client_secret` values in `config`. A schema/data migration
  needs to either encrypt existing rows in place (needs the key available at migration time) or
  the read path needs to tolerate both plaintext and encrypted values during a transition window
  (e.g. try-decrypt-else-treat-as-plaintext) — this is real design work, not a one-line change.
- **Key management is the actual hard part**: what generates `ALFR3D_SECRETS_KEY` initially, what
  happens if it's lost (every stored credential becomes permanently unrecoverable — needs
  re-entering every integration's token from the UI), whether it's per-deployment or has a rotation
  story at all for v1. None of this is decided yet.

## Explicitly out of scope for `todo_esphome.md`
The ESPHome integration ships with `esp_psk` plaintext in `smarthome_devices`, matching the
existing convention, specifically so it isn't blocked on this larger project. Once this lands,
`esp_psk` should be migrated to use it like every other credential column — not treated as a
special case.

## Related
- `todo_esphome.md` Design §3 — where this was first raised, and where the "plaintext for now"
  decision was recorded as the user's explicit call, not an oversight.
- `todo_auth_rbac.md` — a separate but adjacent security-hardening project (authn/authz rather than
  data-at-rest); worth checking whether the two ever want to land in the same session's scope, but
  they're independent problems and don't block each other.
