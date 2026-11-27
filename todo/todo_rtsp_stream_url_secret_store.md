# Move camera RTSP credentials into the secrets store

## Status: 🟡 Built 2026-11-27 (branch `fix/rtsp-url-encrypt-at-rest`), not yet deployed. Password rotation still owed (see bottom).

## What shipped
`services/service_api/stream_secrets.py`: whole URL stored as a Fernet token; routes/devices.py encrypts on create/update; routes/stream.py decrypts only at ffmpeg start + snapshot and redacts `user:pass@` from ffmpeg stderr before logging; models validator caps URLs at 300 chars so the token fits VARCHAR(512). Existing plaintext rows are converted at API startup (`encrypt_existing_stream_urls`, idempotent) rather than by an alembic migration, because the migrate container has no `secrets_data` volume. Reads use `decrypt_or_plaintext`, so rollout is zero-downtime. Tests: `tests/test_stream_secrets.py`. Note: the backfill runs on first boot, so take a DB backup first (the daily one at 04:00 counts).

## Problem
`device.stream_url` (camera rows, `device_type = 'camera'`) stores the full RTSP URL
**including the camera account's username and password in plaintext**, e.g.
`rtsp://<user>:<password>@<camera-ip>/stream1` (the C200 on the prod NUC). Found 2026-10-16 while
investigating the household-composition card: a plain `SELECT d.*` on `device` printed the
credentials.

Existing mitigations (see `todo_camera_streaming.md`): the API never returns the raw URL
(only `has_stream`), and `sa/lake.py` excludes `device.stream_url` from the data lake. The
column itself, DB backups/dumps, and any ad-hoc query remain exposed. The secrets-at-rest
work (2026-08-23, `common/secrets_utils.py`, key in the `secrets_data` volume) covers other
credentials but not this column.

## Goal
- Store the credential part encrypted at rest with `common/secrets_utils.py`; keep only the
  non-secret part (host/path) readable, or store the whole URL encrypted.
- Decrypt only at the point of use: `routes/stream.py` (ffmpeg HLS start, ~L168 and ~L318)
  and the snapshot endpoint.
- Alembic migration: encrypt existing `stream_url` values in place; idempotent, and
  reversible or at least safe to re-run.
- `models.py` `_validate_stream_url` and the device create/update routes: accept plaintext
  on write, encrypt before persisting, never echo it back.
- Make sure ffmpeg errors and logs never print the URL (check how `stream.py` logs the
  command line).
- Tests: round-trip, migration over a mix of plain and already-encrypted rows, no
  credential in API responses or logs.

## Immediate follow-up (not code)
- Rotate the C200's RTSP account password: it was printed in a Claude Code session
  transcript on 2026-10-16. Update the device row afterwards.
