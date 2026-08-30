# SA-9: ESPHome sensors as a situational-awareness signal

## Status: 🔴 Stopped at Phase 0 — no real ESPHome node available to validate against

Second item of Wave 3, following SA-6 (self-hosted routing, in progress). Builds on
`todo/todo_esphome.md` (Phases 0-4 shipped 2026-08-21) — the integration itself (discovery,
`services/common/esphome_utils.py`, sync, API routes) exists, but the task doc is explicit and
unusually emphatic that Phase 1 (live-hardware validation) is a hard prerequisite, not a nice-to-
have: *"Ship nothing downstream until this passes — building SA rules on an untested integration
repeats exactly the mistake the removed travel code made, where a feature existed in the codebase
and could never fire."*

## Phase 0 — investigate

- **Confirmed, on the real production LAN, not assumed**: SSH'd into the household's actual
  production box (`alfr3d@192.168.2.200`) and ran a real mDNS scan —
  `avahi-browse -rt _esphomelib._tcp` — the exact service type
  `services/common/esphome_utils.py`'s `discover_esphome_nodes()` listens for. **Zero devices
  found.** This household does not currently have a live ESPHome node on its network, so there is
  nothing real to validate the shipped integration against today.
- **Attempted a virtual substitute, genuinely, not skipped outright.** ESPHome supports a `host`
  compile target that runs entirely in software and still speaks the real native API/mDNS
  discovery protocol `esphome_utils.py` implements — a legitimate way to exercise this integration
  without physical hardware, the same spirit as SA-6's real-but-cleaned-up test on the NUC. Tried
  to set this up in this session's own environment: both `pip install esphome` and
  `docker pull esphome/esphome` stalled at a small fraction of normal transfer speed (a handful of
  MB over several minutes) — this environment's network path to those specific endpoints is
  unusually slow today, the same symptom SA-6 hit with `download.bbbike.org` (unrelated services,
  same environment — likely a local network/egress condition, not a coincidence about ESPHome
  specifically). Not pursued further within this pass's time budget once it became clear this
  wasn't a quick setup.
- **Checked one related fact while on the real box anyway**: the NUC has a real, working
  Bluetooth adapter (`hci0`, USB, `UP RUNNING`, confirmed via `hciconfig -a`/`rfkill list`) — not
  needed for this item, but directly relevant to SA-8 (BLE presence sensing), next on the list.

**Verdict: stop here, per the task doc's own explicit rule.** No real (or virtually substituted)
ESPHome node was reachable this pass to validate the shipped integration against. Building
Phase 2's context-frame sensor fields or Phase 3's `climate_advisory`/`ambient_occupancy` rules
on top of an integration that has *never* talked to a real device would be exactly the
speculative-feature mistake both this task doc and the removed travel code (SA-6's own
motivating history) warn against repeating.

## Not yet done

- **Live-hardware validation itself** — needs either a real ESPHome node on the household's LAN
  (none exists today) or a working `esphome` host-mode virtual device (blocked this pass by slow
  package/image downloads in this environment, not a fundamental blocker — worth retrying when
  network conditions differ, or when a real ESP32/ESP8266 node exists to test against directly).
- Everything downstream of that: Phase 2 (sensor state into the context frame), Phase 3
  (`climate_advisory`/`ambient_occupancy` rules) — correctly not started.

## Out of scope (per the task doc, unchanged)

- Autonomous actuation — not applicable regardless, no rule in `alfr3ddaemon.py` controls a
  device.
- ESPHome Phase 5 (push-based state), unless Phase 0 finds it's a hard prerequisite — moot until
  Phase 0 itself completes.
- Room-level presence trilateration (SA-8 Phase 3).
