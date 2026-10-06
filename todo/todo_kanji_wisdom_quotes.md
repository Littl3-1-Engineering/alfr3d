# Kanji wisdom quotes — corner-of-screen visual (Deck + web frontend)

## Status: Deck side built 2026-10-05 (uncommitted, **rendering verified on-device 2026-10-05: vertical column bottom-left, no collision with the event log; midnight rollover, reduced motion and other themes not checked); web frontend not started. Added 2026-10-03; cross-repo, mirrored in `alfr3d_deck/todo/`

**Deck decisions (2026-10-05, revised same day):** curated 30-entry list in `kanji/KanjiWisdom.kt`; vertical (tategaki) 18sp column at 70% alpha with reading + meaning set beside it (replaces tap-to-reveal, impossible under the gesture layer); kanji column on the bottom-left edge (lifted above the Socket if it's bottom-left), reading + meaning in two left-aligned rows along the very bottom edge (layout confirmed on-device 2026-10-05); daily rotation at local midnight; top-to-bottom glitch-decode on appear/rollover; theme primary colour; system CJK fallback font; reduced motion = plain text. **Enable/disable toggle** in Settings (classic Appearance tab "KANJI WISDOM" card + Compact Windows card ring, default on). Compact spare-ring floor lowered 8 → 7 in `CompactSettingTest` to fit the new ring. Toggle itself, midnight rollover, reduced motion, other themes not yet checked on-device. List still needs a Japanese reader's vetting; web frontend to reuse it.

Ask: add visuals to **Alfr3d Deck** and the **Alfr3d web frontend** that show wise quotes in
**kanji script** in some corner of the screen.

## Notes / decisions to make

- Corner placement and rotation cadence (per-launch, hourly, daily?). Must not collide with the
  HUD rings / Socket / orbit nodes (see `todo_cyber_hud_buttons_frontend.md`).
- Entries may be proverbs **or single words/concepts** (e.g. 独り占め) — the layout must handle both a one-word and a full-sentence entry.
- Quote source: curated local list (kanji + reading + translation) vs LLM-generated. Recommendation:
  curated list, since a misrendered or wrong kanji is worse than a repeated quote.
- Vertical (tategaki) vs horizontal layout; needs a CJK-capable font on both surfaces (Noto Serif/Sans JP)
  — check bundle size on Android and the web build.
- Style: cyan, low-opacity, subtle glitch/scramble reveal consistent with the HUD vocabulary. Respect reduced-motion.
- Optional: tap/click reveals reading + translation.

## Notion source of truth (created 2026-10-05) — superseded same day

Notion is **reference only, no integration** (decided 2026-10-05). Database **Alfr3d Kanji Wisdom**: https://app.notion.com/p/92fdfbe8fe204dd29fd8173923640592 (`collection://7c0ac920-a916-4784-9ba7-475bf846b78c`; `Kanji`, `Reading`, `Meaning`, `Enabled`, `Vetted`, `Notes`; same 30 entries as `KanjiWisdom.kt`, none vetted). Nothing reads from it.

**Decided architecture (not built yet):**
- **Backend owns the list.** Quotes live in alfr3d's own database (new table via alembic, seeded with the 30 entries), editable through the API/admin surface, not Notion.
- **Backend pushes to the Deck daily** (today's quote, or the full enabled list), over the existing backend→Deck context-exchange path (see `todo_context_exchange_protocol.md`) — no Notion token anywhere, Deck never talks to Notion.
- **Deck without an ALFR3D connection** rotates over its own built-in 30-entry list (`KanjiWisdom.kt`), which may change with app version updates. Last pushed quote is cached so a brief disconnect doesn't flip it.
- **Web frontend** reads the same backend endpoint.

## Resume here (updated 2026-10-06)

**Built 2026-10-06, uncommitted; backend DEPLOYED to the NUC 2026-10-06** (DB backed up first to `~/db_backups/alfr3d_backup_20261006_144824_pre_kanji_wisdom.sql`; files rsynced into the NUC's working tree, so it is dirty vs `cec2f7bd` until this is committed/pushed — `git checkout`/remove those 7 files on the NUC before pulling the real commit; alembic 0046 applied, 30 rows, `/api/kanji/today` live over HTTP and via nginx):
- **Backend (`alfr3d`):** `setup/migration_042_kanji_wisdom.sql` + alembic `0046_kanji_wisdom.py` (table `kanji_wisdom`, 30 seeded rows, `enabled` flag); `routes/kanji.py` — public `GET /api/kanji/today` (`{date,id,kanji,reading,meaning}`, household-local date, `ordinal % enabled-count` pick over id-ordered enabled rows, 404 if none) and permission-gated `GET/POST/PUT/DELETE /api/kanji[/{id}]` (new `kanji` resource, technoking+resident); `tests/test_kanji_wisdom.py`. Full suite 671 pass; black/flake8 clean. Verified on the local dev stack and then on the NUC.
- **Deck (`alfr3d_deck`):** `Alfr3dClient.getKanjiToday()`; `KanjiTodayStore` (DataStore) keeps the last pushed quote; `Alfr3dBackgroundSync.runSync` refreshes it every sync (the "daily push" is the 30-min pull); `KanjiWisdom.resolve(pushed, today)` uses the pushed quote when within ±1 day, else the built-in 30-list. `KanjiWisdomTest` added; build/ktlint/detekt/unit tests/lint pass.
- **Not yet verified on-device** (phone dropped off adb; and the Deck points at the NUC, which has no endpoint yet, so the pushed path can only be exercised after the NUC deploy).

**Next:** (1) commit/push (needs explicit ask) and reconcile the NUC tree; (2) install Deck build, confirm the pushed quote shows and survives a disconnect; (3) web frontend reading `/api/kanji/today`; (4) optional admin UI for editing quotes; (5) Japanese-reader vetting; (6) README/AGENTS API list + Notion timeline when shipped. Open design call still: today's-quote push (done) vs full list — went with today's quote.

## Candidate entries

Curated list (kanji + reading + translation). Each entry should be checked by a Japanese reader
before shipping, per the "wrong kanji is worse than a repeated quote" rule above.

| Kanji | Reading | Meaning | Notes |
|---|---|---|---|
| 独り占め | hitorijime | keeping something all to oneself; monopolizing, hogging | Added 2026-10-04 on request. A vocabulary word, not a proverb — fine: the list allows single words/concepts as well as proverbs (decided 2026-10-04). |
