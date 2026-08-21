# Plan: ESPHome Integration

## Status: 🟡 Phases 0-3 shipped (2026-08-21); Phase 4 (frontend) shipped same day; Phase 5 (push-based state) not started

Backend (discovery, client, sync, API routes) and a frontend discovery/accept panel in
`Integrations.jsx` are implemented and passing lint/tests/build. Not yet exercised against a real
ESPHome device on a live LAN — see "Verified so far" below for exactly what has and hasn't been
tested. Decisions below were made explicitly by the user (2026-08-21), not assumed:
- **PSK storage: plaintext for v1** (Design §3) — see the new companion doc
  `todo/todo_encrypt_secrets_at_rest.md`, created at the same time per the user's explicit request
  to track the broader secrets-at-rest problem separately rather than solve it piecemeal here.
- **ESPHome runs always-on in parallel**, independent of the `iot_provider` HA/ST selector
  (Design §5) — shipped as Phase 0.
- **Manual accept required** for discovered nodes (Design §1) — shipped as designed.

### Verified so far
- Full test suite (167 tests) passes with the new `services/common/esphome_utils.py` and its unit
  tests (`tests/test_esphome_utils.py`) added; `black`/`flake8` clean on every touched file;
  frontend `eslint` clean and `npm run build` succeeds.
- The new migration (`setup/migration_019_esphome.sql` / Alembic `0020_esphome.py`) was applied
  end-to-end against a disposable MySQL 8 container seeded from `createTables.sql` +
  migrations 002-018: schema comes out exactly as designed (`esp_entity_id` column,
  `unique_source_device` correctly extended to
  `COALESCE(ha_entity_id, st_device_id, esp_entity_id)`, `esphome_nodes` table, `esphome_enabled`
  config seed), a simulated second sync cycle for the same entity correctly upserts in place
  rather than duplicating (confirming the extended unique key works), and the `downgrade()` path
  cleanly reverses every change. Torn down after verification — no effect on any real database.
- The `aioesphomeapi`/`zeroconf` API calls in `esphome_utils.py` (constructor args, `connect()`/
  `list_entities_services()`/`subscribe_states()`, per-domain `*_command()` signatures, the
  `_esphomelib._tcp.local.` mDNS service type) were checked against the actual installed library
  source (v45.12.1 / v0.150.0), not written from memory.
- **Not yet verified**: an actual connection to a real ESPHome device (no physical/simulated
  device was available this session), the frontend accept/discover flow driven end-to-end in a
  browser, and the two pre-existing `docker exec`-batch-load quirks hit while constructing the
  test database (a `DELIMITER`-block parsing issue in `createTables.sql` when piped via
  `docker exec -i mysql < file`, and migrations 011/017 erroring as "duplicate" when replayed raw
  against a fresh `createTables.sql` load) — both were worked around for this session's validation
  and are pre-existing repo characteristics unrelated to this change, not something this plan
  introduced, but worth the user's awareness since they weren't previously documented anywhere.

### Implementation deviated from the original sketch in one way (schema, Design §3)
Rather than adding `esp_node_id`/`esp_psk` columns directly to `smarthome_devices` (which is
per-*entity*, one row per exposed entity — a physical node exposes many), the shipped schema uses:
- `smarthome_devices.esp_entity_id VARCHAR(160)` — one column, formatted `"<hostname>:<key>"`,
  filling the same slot as `ha_entity_id`/`st_device_id` in the unique key.
- A new `esphome_nodes` table holding per-node connection info (hostname, IP, port, PSK, accepted
  flag) once, rather than repeating host/port/PSK across every entity row for the same node.

This is a cleaner normalization of the same design intent (per-entity rows mirroring HA, explicit
accept step, plaintext PSK for v1) — not a scope or decision change. See
`services/common/esphome_utils.py`'s module docstring and `setup/migration_019_esphome.sql`'s
comments for the as-shipped schema.

## Goal
Add ESPHome as a first-class, standalone local IoT provider alongside Home Assistant and
SmartThings — not an HA passthrough. ESPHome's native API is local-only (no cloud, no OAuth,
optional Noise-protocol encryption via a per-device pre-shared key), which is a direct fit for
ALFR3D's local-first/privacy posture and lets households run ESPHome nodes without also running
a Home Assistant instance. This scopes what was previously a one-paragraph "Future" stub at the
end of `todo_iot.md` (Phase 17) into a full plan; that stub now points here.

## Current state (verified in code, 2026-08-21)
No ESPHome code exists anywhere in the repo today (`grep -ri esphome` outside this doc and the
`todo_iot.md` stub returns nothing). This is a from-scratch integration that reuses the
established HA/SmartThings pattern:

- **`services/common/ha_utils.py`** (278 lines) and **`services/common/st_utils.py`** — the
  pattern to mirror: `get_*_config()` reads plaintext values from the `config` table,
  `is_*_configured()`, `test_*_connection()`, `get_*_devices()`, `*_control_device()`,
  `sync_*_devices()` (upsert into `smarthome_devices`, MAC-based auto-link to `device`), and
  `save_*_config()`. All functions are **synchronous** — plain `requests` calls + blocking
  `pymysql` via `db_pool.get_connection()`. No async anywhere in this layer.
- **`smarthome_devices` table** (`setup/migration_002_iot.sql:5-21`) — columns include `source`,
  `mac_address`, `ha_entity_id`, `st_device_id`, `device_type`, `capabilities`, `online`,
  `last_state` (JSON), `device_id` (FK to `device`, added in `migration_008_iot_device_link.sql`).
  The unique key is `unique_source_device (source, COALESCE(ha_entity_id, st_device_id))`
  (restored in `migration_017_iot_dedupe.sql:43`) — **there is no third ID column for ESPHome to
  slot into**; adding one needs a migration that also extends this COALESCE.
- **`services/service_api/routes/iot.py`** (426 lines) — thin FastAPI routes per provider
  (`/api/iot/ha/*`, `/api/iot/st/*`) that lazily `from common import ha_utils` and call straight
  through; `save_*_config`/`*_control_device`/sync-trigger endpoints all follow the same shape.
- **Sync scheduling** — `service_daemon/alfr3ddaemon.py`'s `sync_iot_devices()` (~line 899) sends
  `{"action": "iot_ha_sync"}` and `{"action": "iot_st_sync"}` to the Kafka `device` topic every 15
  minutes (comment confirms cadence). `service_device/app.py`'s single-threaded, **blocking**
  `consumer.poll()` loop (~line 480-508) dispatches those actions to `ha_utils.sync_ha_devices()` /
  `st_utils.sync_st_devices()`. `service_device` runs `network_mode: host` (per `AGENTS.md`,
  needed for `arp-scan`) — this matters for ESPHome discovery, see Design §1.
- **⚠️ Found while scoping this: `/api/iot/devices` is single-provider-exclusive today.**
  `fetch_iot_devices_data()` (`routes/iot.py:24-84`) reads the single `iot_provider` config value
  (line 28-30) and filters `WHERE sd.source = %s` (line 46) — so even HA and SmartThings, if both
  were configured simultaneously, would never both show up; only whichever source matches the
  current `iot_provider` selector is returned to the frontend/Blueprint/DeviceRegistry. This is
  the concrete mechanism behind the "open design question" the old `todo_iot.md` stub gestured at
  — it's not just a UX nicety to fix, it's a hard blocker: ESPHome devices will not appear
  anywhere in the UI until this filter changes. See Design §5.
- **`cryptography==50.0.0`** is already a dependency of both `service_api` and `service_device`
  (`requirements.txt`), unused for any encryption-at-rest today — HA's token and SmartThings' PAT
  are both stored as plaintext `config` table values (`ha_utils.save_ha_config`,
  `spotify_utils.py`'s equivalent pattern). Relevant to the PSK storage decision in Design §3.
- **No async runtime exists in any backend service.** `service_api` is FastAPI (uses `asyncio` for
  its own WebSocket broadcast loop, e.g. `routes/iot.py:87-94`), but `service_device` — the
  natural home for LAN discovery, matching `arp-scan` — is a synchronous Flask-style service with
  a blocking Kafka consumer loop. This matters because the ESPHome client library is async-only
  (Design §2).

## Design

### 1. Discovery: mDNS/zeroconf in `service_device`
ESPHome nodes advertise via `_esphomelib._tcp.local.`. `service_device` is the right home for
this scan — it already runs `network_mode: host` (required for `arp-scan`'s raw LAN access, per
`AGENTS.md` Architecture), which mDNS multicast also needs; `service_api` runs on the bridge
network behind nginx and would need extra plumbing to see LAN multicast traffic at all.

Use `zeroconf`'s `ServiceBrowser` (sync API, `python-zeroconf` package — has both sync and asyncio
variants; use the **sync** `Zeroconf`/`ServiceBrowser` here, not `AsyncZeroconf`, to match
`service_device`'s non-async architecture) to populate a candidate list: hostname, IP, port
(default 6053), and any TXT record data (project name/version, `mac` if exposed). This is
discovery only — it does not require the PSK and does not read entity state.

**Privacy/security note distinct from HA/ST**: Home Assistant and SmartThings integrations are
account-scoped — you only ever see devices in *your* HA instance or *your* SmartThings account.
mDNS discovery has no such boundary: in an apartment building or shared-wall home, `service_device`
may discover a neighbor's ESPHome nodes broadcasting on the same LAN segment (if networks aren't
properly isolated) or, more commonly, will surface every ESPHome device on the household's own LAN
including ones nobody intended to onboard yet. Discovered-but-not-yet-linked nodes must **not**
auto-populate `smarthome_devices` the way HA/ST sync does — they need an explicit accept step in
the UI (Design §4) before any connection attempt, let alone a PSK prompt, happens.

### 2. Client: `aioesphomeapi`, and the sync/async mismatch
`aioesphomeapi` (the standard ESPHome native-API client, also what Home Assistant core itself
uses) is **asyncio-only** — there is no sync wrapper. This doesn't fit `service_device`'s blocking
Kafka `consumer.poll()` loop the way `requests`-based `ha_utils`/`st_utils` calls do.

Recommend a two-phase approach rather than solving this all at once:
- **Phase A (poll, matches existing architecture)**: wrap each `aioesphomeapi` call in
  `asyncio.run(...)` inside an otherwise-synchronous `esphome_utils.py`, called from the same
  15-minute Kafka-triggered sync path as HA/ST (`iot_esphome_sync` action). Short-lived event
  loop per sync cycle, connect → fetch entity list/states → disconnect. Simple, consistent with
  the existing pattern, ships fastest.
  - Trade-off worth naming: ESPHome connections use Noise-protocol handshakes per connection, so
    reconnecting every entity fetch (worst case: every device, every 15 min) is more connection
    overhead than a stateless HTTP GET to HA. Acceptable for v1; revisit if node count is large.
- **Phase B (push, stretch goal)**: `aioesphomeapi` supports `subscribe_states()` for real-time
  push updates over the persistent connection — strictly better than HA/ST's 15-minute poll +
  30-second WebSocket-broadcast pattern (`routes/iot.py`'s `broadcast_iot_devices`). This needs an
  actual persistent asyncio event loop running alongside `service_device`'s sync consumer thread
  (e.g. `asyncio.new_event_loop()` on a background thread), which is a real architecture change to
  that service, not a drop-in. Flag as a deliberate follow-up once Phase A is stable and proven
  useful, not part of the initial ship.

### 3. Storage: schema + the PSK-at-rest question
New migration (next in sequence — raw SQL `setup/migration_019_esphome.sql` + Alembic
`setup/migrations/versions/0020_esphome.py`, mirroring `migration_002_iot.sql`'s shape):
- `smarthome_devices.esp_node_id VARCHAR(128) NULL` (ESPHome node's own ID/hostname — the
  equivalent slot to `ha_entity_id`/`st_device_id`).
- Extend the unique key: `DROP INDEX unique_source_device`, re-add as
  `UNIQUE KEY unique_source_device (source, COALESCE(ha_entity_id, st_device_id, esp_node_id))` —
  follow `migration_017_iot_dedupe.sql`'s drop/recreate pattern since this index already needed
  fixing once.
- `smarthome_devices.esp_psk VARCHAR(255) NULL` — per-device pre-shared key for Noise encryption.
- Seed `config` rows: `esphome_enabled` ('true'/'false' — see §5 on why this can't just reuse
  `iot_provider`), `esphome_discovery_interval_minutes` (default e.g. 60 — discovery is cheaper
  and can run more often than full entity sync).

**Open question, needs a decision before Phase 1 ships**: store `esp_psk` plaintext (consistent
with `ha_token`/`st_pat` today — same posture, no new pattern) or encrypt it at rest using the
already-present `cryptography` dependency (Fernet, key from an env var never committed, per
`AGENTS.md`'s "never commit secrets" rule)? Arguments for encrypting: a PSK is a symmetric key to
a device that can (depending on entity types exposed) unlock doors or control climate — arguably
more sensitive than an HA long-lived token, which is itself revocable server-side; a leaked
`ha_token` can be invalidated from the HA UI, a leaked PSK requires physically re-flashing the
device. Arguments against: introduces an inconsistent security posture (this one field encrypted,
every other integration credential in the same `config`/`smarthome_devices` tables plaintext) and
real key-management scope (rotation, what happens on env var loss) that doesn't otherwise exist in
this codebase yet — that's arguably `todo_auth_rbac.md`-sized scope on its own, not something to
bolt onto this integration alone. Recommend punting to plaintext for v1 (consistent with existing
convention) and noting encryption-at-rest for *all* integration secrets as a follow-up scoped
separately, but this is genuinely the user's call.

### 4. API endpoints (mirror existing HA/ST shape)
- `GET /api/iot/esphome/discovered` — candidate nodes found by the last mDNS scan, not yet linked
  (new: HA/ST have no equivalent, since they don't do LAN discovery).
- `POST /api/iot/esphome/discovered/{node_id}/accept` — explicit accept step (per §1); optionally
  takes a PSK in the body.
- `GET /api/iot/esphome/status` — connectivity summary across accepted nodes (HA/ST's `/status` is
  single-connection; ESPHome's is N-node, so this returns a per-node list, not one bool).
- `GET /api/iot/esphome/devices` — accepted nodes' entities, same shape as `get_ha_devices()`'s
  return list.
- `POST /api/iot/esphome/devices/<node_id>/<entity_id>/control` — note the two-level ID (HA uses
  a flat `entity_id`; ESPHome entities are scoped per physical node).
- `POST /api/iot/esphome/sync` — triggers the Kafka `iot_esphome_sync` action, same as
  `POST /api/iot/ha/sync` (`routes/iot.py:159-172`).
- No `PUT /config` equivalent to HA's single-URL/token pair — config is per-node (via the accept
  endpoint), there's no one "ESPHome server" to point at.

### 5. Fix the single-provider filter (blocks ESPHome from ever appearing)
`fetch_iot_devices_data()` (`routes/iot.py:24-84`) needs to stop treating `iot_provider` as an
exclusive filter. Recommend: drop the `WHERE sd.source = %s` provider filter from this query
entirely and return devices from **all** sources with any synced rows — `iot_provider` still
exists as a config value but its meaning narrows to "default provider for [whatever action
actually needs a single default]" rather than "the only source the UI will ever show." Confirm
this doesn't regress anything HA/ST-specific — grep for other reads of `iot_provider` before
changing the query's semantics (`routes/iot.py` and `ha_utils`/`st_utils` were the only hits found
during this scoping pass, but re-check at implementation time). This fix has value independent of
ESPHome (it's what would let HA and SmartThings coexist too) — worth landing as its own small
commit before the ESPHome-specific work, not bundled into it.

### 6. Frontend (`Integrations.jsx`, 349 lines today)
- New ESPHome section alongside the existing HA/SmartThings cards: discovered-node list (name,
  IP, accept button), accepted-node list (status, optional PSK field, unlink), matching the
  visual pattern already used for HA/ST config forms in this file.
- `DeviceRegistry.jsx`'s "SMARTHOME DEVICES" section (added in `todo_iot.md` Phase 10) already
  generalizes over `source` — confirm it renders `esphome` rows without changes needed, or note
  what's ESPHome-specific (e.g. showing per-node connection status rather than a single
  online/offline bool).

## Rollout phasing
- ✅ **Phase 0 — fix `/api/iot/devices` provider-exclusivity** (Design §5). Shipped in
  `routes/iot.py`'s `fetch_iot_devices_data()`.
- ✅ **Phase 1 — schema**: `setup/migration_019_esphome.sql` / Alembic `0020_esphome.py`. Shipped
  as `esp_entity_id` on `smarthome_devices` + a new `esphome_nodes` table (see the "deviated from
  the original sketch" note above) rather than the originally-sketched `esp_node_id`/`esp_psk`
  columns directly on `smarthome_devices`.
- ✅ **Phase 2 — discovery + client (Phase A/poll)**: `services/common/esphome_utils.py`, wired
  into `service_device/app.py`'s consumer dispatch (`iot_esphome_sync`, `iot_esphome_discover`
  actions) and `alfr3ddaemon.py`'s schedule (15-min sync alongside HA/ST, hourly discovery).
- ✅ **Phase 3 — API routes**: `/api/iot/esphome/*` in `routes/iot.py`, plus wiring ESPHome into
  the unified `/api/iot/devices/{id}/control` endpoint alongside the existing HA branch.
- ✅ **Phase 4 — frontend**: `Integrations.jsx` got a dedicated ESPHome panel (wider modal, not the
  shared single-form one HA/ST/OpenWeatherMap/Spotify use) — scan button, discovered-node list with
  per-node optional-PSK accept, accepted-node list with remove. `DeviceRegistry.jsx` was not
  touched — it already generalizes over `source` from earlier IoT work, so ESPHome rows should
  render there without changes, but this has not been visually confirmed in a browser this session.
- ⬜ **Phase 5 — stretch — push-based state (Phase B)**: persistent asyncio loop for
  `subscribe_states()`, replacing the 15-minute poll with real-time push for accepted nodes
  (Design §2). Not started — separate follow-up, not required for v1.

## Decisions (resolved 2026-08-21 — previously open questions)
1. **PSK at rest: plaintext for v1**, consistent with `ha_token`/`st_pat` (Design §3) — broader
   secrets-at-rest encryption tracked separately in `todo/todo_encrypt_secrets_at_rest.md` per the
   user's explicit request, rather than solved piecemeal for just this one field.
2. **`esphome_enabled` is independent of `iot_provider`** — ESPHome runs alongside whichever of
   HA/SmartThings is the selected default provider, with no exclusivity. Shipped as Phase 0.
3. **Manual accept required** for discovered nodes, regardless of whether the node itself has a
   PSK configured — shipped as designed in Design §1.

## Related
- `todo_iot.md` Phase 17 — the original one-paragraph stub this plan replaces; that file now
  points here (see its Phase 17 section).
- `todo_camera_streaming.md` — same pattern of "phase mentioned in `todo_iot.md`, fully scoped in
  its own file" (RTSP camera, Phase 15).
- [[feedback-agents-claude-md-standard]] — git commit/push policy floor applies to this work same
  as everywhere else in this repo.
