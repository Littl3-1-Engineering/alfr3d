# Plan: Encrypt Integration Secrets at Rest

## Status: ✅ Shipped 2026-08-22

`services/common/secrets_utils.py` implements the design below as scoped, wired into
`ha_utils.py`/`st_utils.py`/`spotify_utils.py`/`esphome_utils.py`. Corrections found during
implementation: the ESPHome PSK lives in `esphome_nodes.psk`, not `smarthome_devices` as this
doc originally said; `config.value` (`VARCHAR(512)`) and `esphome_nodes.psk` (`VARCHAR(255)`)
were widened (to `TEXT` and `VARCHAR(512)` respectively, migration `0022`) since Fernet
ciphertext overhead could push a long HA token close to the old 512-char cap. The generated key
file is 0644, not 0600 -- `service-device` runs as root (needs raw network access for
arp-scan) while `service-api`/`service-daemon` run as uid 1000, and a 0600 file created by
whichever process wins the first-boot race would lock the other uid out; the shared Docker
volume mount is the real access-control boundary here, not the in-container file mode.
`service-api`'s `entrypoint.sh` also chowns the volume to uid 1000 on every boot (same existing
pattern it already used for `/tmp/audio`), which is what actually prevents cross-uid permission
failures in practice. Tests: `tests/test_secrets_utils.py` + `tests/test_secrets_wiring.py`.

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

## Design (scoped 2026-08-22 — open questions resolved, ready for implementation)
- Mechanism: Fernet (symmetric, from `cryptography.fernet`) via a new
  `services/common/secrets_utils.py` with `encrypt(value) -> str` / `decrypt(value) -> str`, called
  from every `save_*_config`/`get_*_config` pair across `ha_utils.py`, `st_utils.py`,
  `spotify_utils.py`, and (once shipped) `esphome_utils.py`.
- **Key provisioning (decided)**: auto-generate `ALFR3D_SECRETS_KEY` on first boot if unset, and
  persist it to a file inside a Docker volume (not `.env` — `.env` stays a human-edited template
  per `AGENTS.md`, and the app itself, not this coding session, owns writing the generated key at
  runtime). Chosen over a fail-fast/manual-setup flow specifically so a non-technical Kit buyer
  gets a working device with zero setup steps. Tradeoff accepted explicitly: losing that volume
  means every stored integration credential becomes permanently unrecoverable and needs
  re-entering from the UI — document this prominently (README + first-boot log line) rather than
  hide it. No rotation story for v1; out of scope until there's a concrete need.
- **Migration path (decided)**: dual-read fallback, not a one-time migration script. The read path
  tries `decrypt()` first and falls back to treating the value as plaintext if that fails; every
  write always encrypts going forward. Zero-downtime, no explicit migration step, and the DB
  self-heals to fully-encrypted as each credential gets naturally rewritten (e.g. next OAuth
  refresh). Accepted tradeoff: some rows may stay plaintext indefinitely if never rewritten — fine
  for v1 given the threat model is "DB dump leak," not "every row must be encrypted by date X."

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
