# Layer 3 and context learning: leftover steps (2026-11-20)

State at the end of the 2026-11-19/20 work: phases 1-6 of the Notion prompt "context-agnostic learning and
layer 3" are merged, and #459-#461 plus the dev-dependency bump are deployed (NUC at 4296ec2b, Alembic 0065).
Nothing in layer 3 can act on a device. This file lists what is still open, who owns it, and what gates it.

## Owner actions

- [ ] `! gh auth refresh -s workflow`, then merge the four Dependabot PRs that change workflow files:
      alfr3d_deck #43 and #63, littl31 #36 and #57. After #36 and #57 (checkout and setup-node 4 to 7),
      watch the first littl31 CI run.
- [ ] Decide whether the visible level-0 proposal card is worth starting before the replay shows any
      proposals (see "Gated" below). Default: wait.
- [ ] Decide whether to delete `/tmp/build-host-net.yml` on the NUC. It is no longer needed.

## Scheduled and recurring checks (read-only)

- [ ] **Weekly:** `docker compose exec sa-learner python -m sa.proposal_shadow --lake /lake --days 14`.
      Look for proposals acted on well above their base rate. Today: 0 proposals in 14 days.
- [ ] **Weekly for the first month:** discovery screen. Read `effect_nights` out of `nights` from
      `GET /api/context/findings`; a one-night effect is not a finding. Today: 2 nights (the first,
      2026-11-19, had no data; the second, 2026-11-20, had all 23 candidates with data), 0 effects.
- [ ] **2026-11-23:** stay-parity re-run (needs at least 14 person-days after 2026-11-19).
- [ ] Re-test the 7 candidates under the 20-event floor (`guests_home` at 2 events, `house_empty` at 18)
      as the weather overlap grows (about 5 weeks today).
- [ ] The nightly learner log line "context ledger written" was not confirmed on 2026-11-20 (container
      logs were wiped by the redeploy). Confirm it on the next night's log.

## Gated on evidence or owner approval (not started)

- [ ] **Visible level-0 proposal card.** Needs Deck Kotlin (one parser per card type), web JSX (an icon
      per type), a Play release, `MAX_DISPLAYS` 26 to 27 and the engine safety-net update
      (`tests/test_sa_engine_structure.py`, `tests/data/sa_engine_surface.json`). Worth it only when
      the replay shows proposals that beat their base rate.
- [ ] **Level 1 confirm flow**, through the existing `POST /api/iot/devices/{id}/control` (an ordinary
      user command, `origin = "user"`). Needs no executor.
- [ ] **Gated executor for levels 2 and 3**, last, after weeks of real outcome labels, behind a flag that
      ships off. Still open from `todo_l3_executor_spec.md` review items 1, 3 and 6:
      - one narrow switch/light wrapper over `common.ha_utils.ha_control_device`, refusing any other
        domain; never `util_routines.control_iot_device` (it can unlock a door);
      - check the entity exists before acting and confirm the state changed after (HA answers 200 for
        entities that no longer exist);
      - quiet hours from `DayContext`, not a hard-coded window.
- [ ] Person and presence scope (only household scope exists).

## Infrastructure notes

- Done 2026-11-20: `/etc/docker/daemon.json` on the NUC sets `dns` to 8.8.8.8 and 1.1.1.1. The cause was
  that build containers inherited the host's IPv6-only upstream resolvers and have no IPv6 route.
  Builds now work without the host-network override.
- **A Docker restart on the NUC takes the whole stack down for about five minutes.** `alfr3d.service`
  requires `docker.service`; its stop is `compose down`, and its start is `compose build` then
  `compose up -d`. Plan a restart for a quiet moment; volumes are not touched. Home Assistant restarts
  with it.
- Container logs are lost on every recreate. Capture anything needed from a night's run before a deploy.
- The littl31 tailwind 2 to 3 bump (#76) was merged on the build check only; the rendered site has not
  been inspected.
